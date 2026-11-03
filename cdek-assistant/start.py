#!/usr/bin/env python3
"""Dependency-free local launcher. Passwords are chosen in the browser."""
import argparse
import os
from pathlib import Path
import sys
import threading
import webbrowser


def main():
    if sys.version_info < (3, 12):
        print('Нужен Python 3.12 или новее. Установите его с python.org и повторите запуск.', flush=True)
        return 1
    try:
        import sqlite3
        with sqlite3.connect(':memory:') as check:
            check.execute('CREATE VIRTUAL TABLE probe USING fts5(body)')
    except Exception:
        print('Python не поддерживает SQLite FTS5. Переустановите официальный Python 3.12+ с python.org.', flush=True)
        return 1
    from cdek.server import make_server
    parser = argparse.ArgumentParser(description='Локальный запуск помощника СДЭК')
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent / 'data')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--no-browser', action='store_true', help='Не открывать браузер автоматически')
    args = parser.parse_args()
    root = args.data_dir.expanduser().resolve()
    if root.is_relative_to(Path(__file__).resolve().parent / 'web'):
        print('Папка данных не должна находиться внутри web/.', flush=True)
        return 1
    url = f'http://127.0.0.1:{args.port}'
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        server = make_server(root / 'app.sqlite3', port=args.port, dev=True)
        os.chmod(root / 'app.sqlite3', 0o600)
    except OSError as exc:
        if getattr(exc, 'errno', None) in (48, 98, 10048) or getattr(exc, 'winerror', None) == 10048:
            print(f'Порт {args.port} уже занят. Закройте предыдущий сервер и повторите запуск.\nНе открывайте другую копию приложения с другой базой.', flush=True)
        else:
            print(f'Не удалось запустить сервер. Проверьте доступ к папке данных: {root}\n{exc}', flush=True)
        return 1
    except Exception as exc:
        print(f'Не удалось подготовить приложение: {exc}', flush=True)
        return 1
    bootstrap_url = url + ('/#setup=' + server.setup_token if server.setup_token else '/')
    print(f'\nПомощник СДЭК запущен. Адрес: {url}\nПапка данных: {root}', flush=True)
    if server.setup_token:
        print('Первый запуск: создайте локального администратора и задайте свой пароль.\nОткройте одноразовую ссылку (не пересылайте её):\n' + bootstrap_url, flush=True)
    else:
        print('Войдите с ранее созданным локальным аккаунтом. Пароли и документы сохранены.', flush=True)
    print('После входа можно импортировать ZIP материалов или продолжить с пустой базой.\nОставьте это окно открытым. Для остановки нажмите Ctrl+C.\nHTML-файл и Live Server не подходят: используйте адрес Python-сервера выше.', flush=True)
    if not args.no_browser:
        # The socket is already bound; serve_forever starts immediately below.
        threading.Timer(0.3, lambda: webbrowser.open(bootstrap_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nСервер остановлен. Данные сохранены.', flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
