import json
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .materials import digest, verify, compare_workbooks, workbook, text_chunks, table_chunks


def now():
    return datetime.now(timezone.utc).isoformat()


def connect(path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, title TEXT, url TEXT, revision TEXT,
      hash TEXT, status TEXT, metadata TEXT, approved INTEGER DEFAULT 0, evidence TEXT,
      reviewed_at TEXT, expires_at TEXT, reviewer TEXT);
    CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, source_id TEXT REFERENCES sources(id), locator TEXT, body TEXT);
    CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(body, content='chunks', content_rowid='id', tokenize='unicode61');
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT, actor TEXT, action TEXT, source_id TEXT, details TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS source_versions(id INTEGER PRIMARY KEY, source_id TEXT, archived_at TEXT, snapshot TEXT);
    CREATE TABLE IF NOT EXISTS queue(id TEXT PRIMARY KEY, priority INTEGER, status TEXT, details TEXT);
    CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY, password TEXT, role TEXT);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user TEXT REFERENCES users(name), csrf TEXT, expires REAL);
    ''')
    return db


def audit(db, actor, action, source_id='', details=None):
    db.execute('INSERT INTO audit(at,actor,action,source_id,details) VALUES(?,?,?,?,?)',
               (now(), actor, action, source_id, json.dumps(details or {}, ensure_ascii=False)))


def add_source(db, entry, chunks):
    old = db.execute('SELECT hash,metadata FROM sources WHERE id=?', (entry['id'],)).fetchone()
    if old and old['hash'] == entry['hash'] and old['metadata'] == entry['metadata']:
        return
    if old:
        snapshot = dict(db.execute('SELECT * FROM sources WHERE id=?', (entry['id'],)).fetchone())
        snapshot['chunks'] = [dict(c) for c in db.execute('SELECT locator,body FROM chunks WHERE source_id=?', (entry['id'],))]
        db.execute('INSERT INTO source_versions(source_id,archived_at,snapshot) VALUES(?,?,?)', (entry['id'], now(), json.dumps(snapshot, ensure_ascii=False)))
        db.execute('DELETE FROM chunks WHERE source_id=?', (entry['id'],))
    db.execute('''INSERT INTO sources(id,title,url,revision,hash,status,metadata) VALUES(:id,:title,:url,:revision,:hash,:status,:metadata)
      ON CONFLICT(id) DO UPDATE SET title=excluded.title,url=excluded.url,revision=excluded.revision,
      hash=excluded.hash,status=excluded.status,metadata=excluded.metadata,approved=0,evidence=NULL,
      reviewed_at=NULL,expires_at=NULL,reviewer=NULL''', entry)
    db.executemany('INSERT INTO chunks(source_id,locator,body) VALUES(?,?,?)', ((entry['id'], loc, body) for loc, body in chunks))
    audit(db, 'import', 'source_imported_approval_reset', entry['id'], {'hash': entry['hash']})


def ingest(db, root):
    root = Path(root).resolve()
    integrity = verify(root)
    tables = compare_workbooks(root)
    registry = json.loads((root / 'registry.json').read_text())
    with db:
        imported_ids = set()
        for row in registry:
            path = (root / row['file']).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Invalid source path')
            data = path.read_bytes()
            imported_ids.add(row['page_id'])
            if digest(data) != row['sha256']:
                raise ValueError('Registry hash mismatch: ' + row['page_id'])
            existing = db.execute('SELECT metadata FROM sources WHERE id=?', (row['page_id'],)).fetchone()
            if existing and json.loads(existing['metadata']).get('supersedes_base_hash') == digest(data):
                continue  # Do not downgrade an installed addendum on repeated base import.
            add_source(db, {'id': row['page_id'], 'title': row['title'], 'url': row['source_url'],
                           'revision': '; '.join(row.get('source_dates', [])) or row.get('document_number') or 'Редакция не подтверждена',
                           'hash': digest(data), 'status': row['currency_status'], 'metadata': json.dumps(row, ensure_ascii=False)},
                       text_chunks(data.decode('utf-8-sig')))
        for p in sorted((root / 'attachments').glob('*.xlsx')):
            w = workbook(p)
            meta = json.loads(Path(str(p) + '.json').read_text())
            entry = {'id': 'xlsx:' + p.stem, 'title': p.name, 'url': meta['source'],
                     'revision': 'Снимок ' + meta['checked_date'] + '; актуальность не подтверждена',
                     'hash': digest(p.read_bytes()), 'status': 'not_confirmed',
                     'metadata': json.dumps({'file': 'attachments/' + p.name, 'images_unreviewed': w['images'],
                                             'parser_version': 1,
                                             'comparison': next(t for t in tables if t['file'] == p.name)}, ensure_ascii=False)}
            imported_ids.add(entry['id'])
            add_source(db, entry, (chunk for sheet in w['sheets'] if sheet['state'] == 'visible' for chunk in table_chunks(sheet)))
        for previous in db.execute('SELECT id FROM sources').fetchall():
            if previous['id'] not in imported_ids:
                db.execute("UPDATE sources SET approved=0,status='unavailable',expires_at=NULL WHERE id=?", (previous['id'],))
                db.execute('DELETE FROM chunks WHERE source_id=?', (previous['id'],))
                audit(db, 'import', 'source_missing_from_new_bundle', previous['id'])
        # Backlog priority means review order, never mandatory applicability.
        for row in json.loads((root / 'backlog.json').read_text()):
            priority = len(row.get('referred_by', []))
            db.execute('INSERT OR IGNORE INTO queue VALUES(?,?,?,?)', (row['page_id'], priority, row['status'], json.dumps(row)))
        for sid in ('104','310','395','1037','569','402','1021','1998','2139','2662'):
            db.execute('INSERT OR IGNORE INTO queue VALUES(?,?,?,?)', (sid, 100, 'requires_review' if sid != '2662' else 'source_unavailable', json.dumps({'reason': 'Core safety, packaging, precedence or known exclusion review'})))
        db.execute("INSERT INTO search(search) VALUES('rebuild')")
        for key, value in [('coverage', json.loads((root / 'coverage.json').read_text())), ('integrity', integrity),
                           ('workbooks', tables), ('asset_queue_count', len(json.loads((root / 'asset-review-queue.json').read_text())))]:
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value)))
        audit(db, 'import', 'bundle_verified', details=integrity)
    return {'integrity': integrity, 'workbooks': tables, 'sources': len(registry) + len(tables)}


def active_clause():
    return "s.approved=1 AND s.status='current_verified' AND s.expires_at>?"


def search(db, query, review=False, limit=12):
    words = re.findall(r'[\w]+', query.lower(), re.UNICODE)[:24]
    if not words:
        return []
    # Prefixes help Russian inflection without changing the original quoted text.
    match = ' OR '.join('"' + (w[:-2] if len(w) > 5 else w) + '"*' for w in words)
    params = [match]
    clause = '1=1' if review else active_clause()
    if not review:
        params.append(now())
    params.append(limit)
    rows = db.execute(f'''SELECT c.id,c.source_id,c.locator,c.body,s.title,s.url,s.revision,s.hash,s.status,
       s.approved,s.expires_at FROM search JOIN chunks c ON c.id=search.rowid JOIN sources s ON s.id=c.source_id
       WHERE search MATCH ? AND {clause} ORDER BY bm25(search) LIMIT ?''', params).fetchall()
    result = [dict(r) for r in rows]
    for row in result:
        if ' #h-' in row['locator']:
            from urllib.parse import quote
            row['url'] += '#' + quote(row['locator'].split(' #', 1)[1].split(' ', 1)[0])
    return result


def decision(db, source_id, payload, actor):
    row = db.execute('SELECT * FROM sources WHERE id=?', (source_id,)).fetchone()
    if not row:
        raise ValueError('Источник не найден')
    if payload.get('hash') != row['hash']:
        raise ValueError('Версия изменилась. Повторите проверку SHA256')
    approve = payload.get('approve') is True
    evidence = payload.get('evidence', {})
    normalized_expiry = None
    if approve:
        if row['status'] in ('retired_explicit', 'superseded', 'unavailable'):
            raise ValueError('Отменённый, заменённый или отсутствующий источник нельзя допустить')
        fields = ['currency', 'completeness', 'attachments', 'scope', 'conflicts', 'reference']
        if any(not isinstance(evidence.get(k), str) or len(evidence[k].strip()) < 12 for k in fields):
            raise ValueError('Нужны отдельные доказательства актуальности, полноты, приложений, области применения, противоречий и ссылка на проверку')
        expires = datetime.fromisoformat(payload.get('expires_at', ''))
        if expires.tzinfo is None or not datetime.now(timezone.utc) < expires <= datetime.now(timezone.utc) + timedelta(days=90):
            raise ValueError('Срок проверки должен быть в будущем, не далее 90 дней, с часовым поясом')
        normalized_expiry = expires.astimezone(timezone.utc).isoformat()
        meta = json.loads(row['metadata'])
        if meta.get('comparison', {}).get('differences'):
            raise ValueError('Сначала устраните расхождения XLSX с JSON и повторно импортируйте пакет')
    with db:
        db.execute('''UPDATE sources SET approved=?,status=?,evidence=?,reviewed_at=?,expires_at=?,reviewer=? WHERE id=?''',
                   (int(approve), 'current_verified' if approve else ('not_confirmed' if row['status']=='current_verified' else row['status']),
                    json.dumps(evidence, ensure_ascii=False), now(), normalized_expiry, actor, source_id))
        audit(db, actor, 'approved' if approve else 'revoked', source_id, {'hash': row['hash'], 'evidence': evidence, 'expires_at': payload.get('expires_at')})


def coverage(db):
    result = {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}
    result['total_sources'] = db.execute('SELECT count(*) FROM sources').fetchone()[0]
    result['approved_sources'] = db.execute('SELECT count(*) FROM sources s WHERE ' + active_clause(), (now(),)).fetchone()[0]
    result['queue_count'] = db.execute('SELECT count(*) FROM queue').fetchone()[0]
    return result
