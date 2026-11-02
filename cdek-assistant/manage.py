#!/usr/bin/env python3
import argparse
import getpass
import json
import os
import re
from pathlib import Path
from cdek import store, auth
from cdek.server import serve


def main():
    parser = argparse.ArgumentParser(description='Private CDEK assistant')
    parser.add_argument('--data-dir', default=os.getenv('CDEK_DATA_DIR', '/workspace/cdek-private'))
    sub = parser.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import'); imp.add_argument('materials')
    add = sub.add_parser('addendum'); add.add_argument('materials')
    user = sub.add_parser('user'); user.add_argument('name'); user.add_argument('--role', choices=['admin','operator'], default='operator')
    run = sub.add_parser('serve'); run.add_argument('--port', type=int, default=8080); run.add_argument('--dev', action='store_true'); run.add_argument('--origin')
    sub.add_parser('status')
    args = parser.parse_args()
    root = Path(args.data_dir).resolve()
    web = Path(__file__).resolve().parent / 'web'
    if root.is_relative_to(web):
        parser.error('Private data must not be stored inside web/')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    dbpath = root / 'app.sqlite3'
    db = store.connect(dbpath)
    os.chmod(dbpath, 0o600)
    if args.command == 'import':
        print(json.dumps(store.ingest(db, args.materials), ensure_ascii=False, indent=2))
    elif args.command == 'addendum':
        from cdek.addendum import import_addendum
        print(json.dumps(import_addendum(db,args.materials),ensure_ascii=False,indent=2))
    elif args.command == 'status':
        print(json.dumps(store.coverage(db), ensure_ascii=False, indent=2))
    elif args.command == 'user':
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', args.name):
            parser.error('Use 3–64 letters, digits, dots, hyphens or underscores')
        password = getpass.getpass('Password (not echoed): ')
        if password != getpass.getpass('Repeat password: '):
            parser.error('Passwords differ')
        hashed = auth.password_hash(password)
        with db:
            db.execute('INSERT INTO users VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET password=excluded.password,role=excluded.role', (args.name,hashed,args.role))
            db.execute('DELETE FROM sessions WHERE user=?', (args.name,))
            store.audit(db, 'local-cli', 'user_updated', details={'user': args.name, 'role': args.role})
        print('User saved. Previous sessions revoked.')
    elif args.command == 'serve':
        db.close()
        serve(dbpath, args.port, args.dev, args.origin)


if __name__ == '__main__':
    main()
