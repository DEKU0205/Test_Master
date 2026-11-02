import hashlib
import hmac
import secrets
import time


def password_hash(password):
    if len(password) < 12:
        raise ValueError('Пароль должен содержать не менее 12 символов')
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + key


def check_password(password, stored):
    try:
        salt, expected = stored.split(':')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def login(db, name, password):
    row = db.execute('SELECT * FROM users WHERE name=?', (name,)).fetchone()
    # Fixed scrypt work also for unknown usernames.
    stored = row['password'] if row else ('00' * 16 + ':' + '00' * 64)
    valid = check_password(password, stored)
    if not valid or not row:
        return None
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db:
        db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token_hash(token), name, csrf, time.time() + 8 * 3600))
    return token, csrf, row['role']


def session(db, token):
    row = db.execute('''SELECT u.name,u.role,s.csrf FROM sessions s JOIN users u ON u.name=s.user
                        WHERE s.token=? AND s.expires>?''', (token_hash(token), time.time())).fetchone()
    return dict(row) if row else None
