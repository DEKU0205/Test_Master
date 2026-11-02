"""Ephemeral browser-test accounts; never create credentials in the real database."""
import json
import os
import secrets
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cdek import store,auth
from cdek.server import serve

root=Path(sys.argv[1]);port=int(sys.argv[2]);source=Path(sys.argv[3])
origin=sqlite3.connect(source);target=sqlite3.connect(root/'app.sqlite3');origin.backup(target);target.close();origin.close()
db=store.connect(root/'app.sqlite3');password=secrets.token_urlsafe(30)
db.execute('DELETE FROM sessions');db.execute('DELETE FROM users')
for name,role in [('browser-admin','admin'),('browser-operator','operator')]:
    db.execute('INSERT INTO users VALUES(?,?,?)',(name,auth.password_hash(password),role))
db.commit();db.close()
for folder in ('materials','packaging-addendum'):
    original=source.parent/folder
    if original.exists():(root/folder).symlink_to(original,target_is_directory=True)
credentials=root/'credentials.json';credentials.write_text(json.dumps({'password':password}));os.chmod(credentials,0o600)
serve(root/'app.sqlite3',port,dev=True)
