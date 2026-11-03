"""Transactional installation of private, checksum-verified material bundles."""
import io
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from .materials import verify
from .store import ingest
from .addendum import import_addendum

MAX_UPLOAD = 64 * 1024 * 1024
MAX_EXTRACTED = 256 * 1024 * 1024


def import_zip(db, data_dir, payload, kind):
    if kind not in ('base', 'addendum'):
        raise ValueError('Выберите основной пакет или дополнение по упаковке')
    if len(payload) > MAX_UPLOAD:
        raise ValueError('ZIP слишком велик: максимум 64 МБ')
    data_dir = Path(data_dir).resolve()
    folder = 'materials' if kind == 'base' else 'packaging-addendum'
    with tempfile.TemporaryDirectory(prefix='.import-', dir=data_dir) as temp:
        staging = Path(temp) / 'extracted'
        staging.mkdir()
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                members = archive.infolist()
                if len(members) > 10000 or sum(m.file_size for m in members) > MAX_EXTRACTED:
                    raise ValueError('Слишком большой распакованный архив')
                seen = set()
                for member in members:
                    name = member.filename
                    path = PurePosixPath(name)
                    normalized = name.rstrip('/').casefold()
                    if ('\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or
                            normalized in seen or stat.S_ISLNK(member.external_attr >> 16) or '\x00' in name):
                        raise ValueError('Небезопасное или повторяющееся имя файла в ZIP')
                    seen.add(normalized)
                    target = (staging / name).resolve()
                    if not target.is_relative_to(staging):
                        raise ValueError('Файл ZIP выходит за пределы папки импорта')
                archive.extractall(staging)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise ValueError('Не удалось прочитать ZIP. Выберите исходный незашифрованный архив материалов.') from None
        manifests = list(staging.rglob('checksums.json'))
        if len(manifests) != 1:
            raise ValueError('В ZIP должен быть ровно один checksums.json. Нужен архив материалов СДЭК, а не исходников сайта.')
        package = manifests[0].parent
        required = ('registry.json','coverage.json','backlog.json') if kind == 'base' else ('cargo-packaging.json','source-395.json','source-1037.json')
        if not all((package / name).is_file() for name in required):
            raise ValueError('Этот ZIP не соответствует выбранному типу пакета')
        integrity = verify(package)
        if kind == 'addendum' and not db.execute("SELECT 1 FROM sources WHERE id='395'").fetchone():
            raise ValueError('Сначала импортируйте основной ZIP материалов, затем дополнение')
        destination = data_dir / folder
        backup = Path(temp) / 'previous'
        if destination.is_symlink():
            raise ValueError('Папка материалов не должна быть символической ссылкой')
        had_previous = destination.exists()
        if had_previous:
            os.replace(destination, backup)
        try:
            os.replace(package, destination)
            result = ingest(db, destination) if kind == 'base' else import_addendum(db, destination)
        except Exception:
            # Both importers roll back SQLite on failure; restore the original files.
            if destination.exists():
                shutil.rmtree(destination)
            if had_previous:
                os.replace(backup, destination)
            raise
    return {'kind': kind, 'verified_files': integrity['verified'], 'report': result}
