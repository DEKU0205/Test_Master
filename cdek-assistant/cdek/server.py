import hmac
import json
import mimetypes
import os
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from . import auth, store, model

WEB = Path(__file__).resolve().parent.parent / 'web'


class Handler(BaseHTTPRequestHandler):
    server_version = 'CDEKAssistant'

    def log_message(self, *_):
        pass  # Do not log user cargo, query strings, cookies, passwords or provider responses.

    def reply(self, status, data, mime='application/json; charset=utf-8', cookie=None):
        raw = json.dumps(data, ensure_ascii=False).encode() if mime.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)

    def user(self, db):
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookies['cdek_session'].value if 'cdek_session' in cookies else ''
            return auth.session(db, token)
        except Exception:
            return None

    def cookie(self, value, age=28800):
        return f'cdek_session={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}' + ('; Secure' if self.server.secure else '')

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)

    def dispatch(self, post):
        db = store.connect(self.server.db_path)
        try:
            self.route(db, post)
        except (ValueError, TypeError, KeyError) as exc:
            self.reply(400, {'error': str(exc)[:300]})
        except model.ModelFailure as exc:
            self.reply(503, {'error': str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.reply(500, {'error': 'Внутренняя ошибка. Подробности запроса не записываются в журнал.'})
        finally:
            db.close()

    def route(self, db, post):
        host = self.headers.get('Host', '')
        if host != self.server.expected_host:
            return self.reply(403, {'error': 'Недопустимый Host'})
        url = urlparse(self.path)
        path = url.path
        body = {}
        if post:
            if self.headers.get('Origin') != self.server.origin:
                return self.reply(403, {'error': 'Недопустимый Origin'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415, {'error': 'Требуется JSON'})
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 32000:
                return self.reply(413, {'error': 'Недопустимый размер запроса'})
            self.connection.settimeout(15)
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError('Ожидался JSON-объект')
        if not post and path in ('/', '/app.js', '/style.css'):
            file = WEB / {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[path]
            return self.reply(200, file.read_bytes(), mimetypes.guess_type(file)[0] + '; charset=utf-8')
        if not post and path == '/health':
            return self.reply(200, {'status': 'ok'})
        if post and path == '/api/login':
            # Per-account and per-address rolling windows, synchronized across threads.
            identity = str(body.get('username', ''))[:100]
            with self.server.lock:
                keys = ('ip:' + self.client_address[0], 'user:' + identity)
                for key in keys:
                    self.server.attempts[key] = [t for t in self.server.attempts.get(key, []) if t > time.time() - 300]
                if any(len(self.server.attempts[k]) >= 8 for k in keys):
                    return self.reply(429, {'error': 'Слишком много попыток. Повторите через 5 минут'})
                for key in keys:
                    self.server.attempts[key].append(time.time())
            password = body.get('password', '')
            if not isinstance(password, str) or len(password) > 1024:
                raise ValueError('Некорректный пароль')
            result = auth.login(db, identity, password)
            if not result:
                return self.reply(401, {'error': 'Неверное имя или пароль'})
            token, csrf, role = result
            return self.reply(200, {'user': identity, 'role': role, 'csrf': csrf}, cookie=self.cookie(token))
        user = self.user(db)
        if not user:
            return self.reply(401, {'error': 'Требуется вход'})
        if post and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), user['csrf']):
            return self.reply(403, {'error': 'Недействительный CSRF-токен'})
        admin = user['role'] == 'admin'
        if not post and path == '/api/me':
            return self.reply(200, user | {'model_configured': model.configured()})
        if post and path == '/api/logout':
            with db:
                db.execute('DELETE FROM sessions WHERE user=? AND csrf=?', (user['name'], user['csrf']))
            return self.reply(200, {'ok': True}, cookie=self.cookie('', 0))
        if not post and path == '/api/coverage':
            return self.reply(200, store.coverage(db))
        if post and path == '/api/search':
            review = body.get('review') is True
            if review and not admin:
                return self.reply(403, {'error': 'Проверка материалов доступна администратору'})
            query = str(body.get('query', ''))[:4000]
            return self.reply(200, {'results': store.search(db, query, review=review), 'review': review})
        if post and path == '/api/answer':
            query = body.get('query', '')
            if not isinstance(query, str) or not query.strip() or len(query) > 4000:
                raise ValueError('Опишите груз или ситуацию, до 4000 символов')
            if not isinstance(body.get('context', {}), dict):
                raise ValueError('Некорректный контекст')
            # Bound concurrent paid calls. Questions and answers are not retained.
            if not self.server.model_slots.acquire(blocking=False):
                return self.reply(429, {'error': 'Помощник занят. Повторите запрос позже'})
            try:
                result = model.answer(db, query, body.get('context', {}))
                with db:
                    store.audit(db, user['name'], 'answer_attempt', details={'status': result['status']})
                return self.reply(200, result)
            finally:
                self.server.model_slots.release()
        if path.startswith('/api/admin/') and not admin:
            return self.reply(403, {'error': 'Требуются права администратора'})
        if not post and path == '/api/admin/sources':
            return self.reply(200, {'sources': [dict(r) for r in db.execute('SELECT * FROM sources ORDER BY approved DESC, id')]})
        if not post and path == '/api/admin/queue':
            return self.reply(200, {'queue': [dict(r) for r in db.execute('SELECT * FROM queue ORDER BY priority DESC,id')]})
        if post and path == '/api/admin/queue':
            status = body.get('status')
            note = body.get('note', '')
            if status not in ('requires_review','in_scope','out_of_scope','blocked','reviewed') or not isinstance(note, str) or len(note.strip()) < 12:
                raise ValueError('Укажите статус очереди и обоснование')
            with db:
                if not db.execute('UPDATE queue SET status=?,details=? WHERE id=?', (status, json.dumps({'note': note, 'actor': user['name'], 'at': store.now()}, ensure_ascii=False), str(body.get('id')))).rowcount:
                    raise ValueError('Пункт очереди не найден')
                store.audit(db, user['name'], 'queue_triage', str(body.get('id')), {'status': status, 'note': note})
            return self.reply(200, {'ok': True})
        if not post and path == '/api/admin/audit':
            return self.reply(200, {'events': [dict(r) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]})
        if not post and path == '/api/admin/versions':
            sid = parse_qs(url.query).get('id', [''])[0]
            return self.reply(200, {'versions': [dict(r) for r in db.execute('SELECT * FROM source_versions WHERE source_id=? ORDER BY id DESC', (sid,))]})
        if not post and path == '/api/admin/original':
            sid = parse_qs(url.query).get('id', [''])[0]
            row = db.execute('SELECT metadata,hash FROM sources WHERE id=?', (sid,)).fetchone()
            if not row:
                return self.reply(404, {'error': 'Источник не найден'})
            metadata = json.loads(row['metadata'])
            folder = metadata.get('storage_root','materials')
            if folder not in ('materials','packaging-addendum'):
                raise ValueError('Unknown private storage root')
            root = (Path(self.server.db_path).parent / folder).resolve()
            original = (root / metadata['file']).resolve()
            if not original.is_relative_to(root) or not original.is_file():
                return self.reply(404, {'error': 'Оригинал отсутствует'})
            raw = original.read_bytes()
            from .materials import digest
            if digest(raw) != row['hash']:
                return self.reply(409, {'error': 'Оригинал изменён. Повторите импорт и проверку'})
            # Force download of internal content. Never render bundled HTML.
            return self.reply(200, raw, 'application/octet-stream')
        if post and path == '/api/admin/decision':
            store.decision(db, str(body.get('source_id')), body, user['name'])
            return self.reply(200, {'ok': True})
        if not post and path == '/api/source':
            sid = parse_qs(url.query).get('id', [''])[0]
            row = db.execute('SELECT * FROM sources WHERE id=?', (sid,)).fetchone()
            if not row or (not admin and not db.execute('SELECT 1 FROM sources s WHERE s.id=? AND ' + store.active_clause(), (sid, store.now())).fetchone()):
                return self.reply(404, {'error': 'Источник недоступен'})
            return self.reply(200, {'source': dict(row), 'chunks': [dict(r) for r in db.execute('SELECT * FROM chunks WHERE source_id=?', (sid,))]})
        return self.reply(404, {'error': 'Не найдено'})


def serve(db_path, port=8080, dev=False, origin=None):
    origin = origin or f'http://127.0.0.1:{port}'
    parsed = urlparse(origin)
    if parsed.scheme != 'https' and not (dev and parsed.hostname in ('127.0.0.1','localhost')):
        raise ValueError('Для закрытого доступа нужен HTTPS origin; локально используйте --dev')
    if parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Origin должен содержать только схему и хост')
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.db_path, server.secure = str(db_path), not dev
    server.origin, server.expected_host = origin.rstrip('/'), parsed.netloc
    server.attempts, server.lock, server.model_slots = {}, threading.Lock(), threading.BoundedSemaphore(2)
    print(f'Assistant started on port {port}; authentication required; model configured: {model.configured()}', flush=True)
    server.serve_forever()
