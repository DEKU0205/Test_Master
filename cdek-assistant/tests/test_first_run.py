import io
import json
import hashlib
import http.cookiejar
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from cdek import store
from cdek.zip_import import import_zip
from cdek.server import make_server


def bundle(broken_registry=False):
    text=b'Private synthetic test material'
    entries={'documents/1.md':text,
             'registry.json':json.dumps([{'page_id':'1','title':'Test document','source_url':'https://base.cdek.ru/page/1', 'source_dates':[], 'currency_status':'not_confirmed','file':'documents/1.md', 'sha256':'invalid' if broken_registry else hashlib.sha256(text).hexdigest()}]).encode(),
             'coverage.json':b'{}','backlog.json':b'[]','asset-review-queue.json':b'[]'}
    entries['checksums.json']=json.dumps({n:hashlib.sha256(data).hexdigest() for n,data in entries.items()}).encode()
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w') as z:
        for n,data in entries.items():z.writestr('wrapped/'+n,data)
    return result.getvalue()


class ZipTests(unittest.TestCase):
    def test_import_wrapped_zip_and_rollback(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);db=store.connect(root/'test.sqlite')
            self.assertEqual(import_zip(db,root,bundle(),'base')['verified_files'],5)
            self.assertEqual(store.coverage(db)['total_sources'],1)
            self.assertEqual(store.coverage(db)['approved_sources'],0)
            original=(root/'materials/registry.json').read_bytes()
            with self.assertRaises(ValueError):import_zip(db,root,bundle(True),'base')
            self.assertEqual((root/'materials/registry.json').read_bytes(),original)
            self.assertEqual(store.coverage(db)['total_sources'],1)
            db.close()

    def test_archive_traversal_and_windows_paths_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);db=store.connect(root/'test.sqlite')
            for name in ['../escape.txt','/absolute.txt','C:/windows.txt','..\\escape.txt','test:stream.txt']:
                result=io.BytesIO()
                with zipfile.ZipFile(result,'w') as z:z.writestr(name,b'bad')
                with self.subTest(name=name),self.assertRaises(ValueError):import_zip(db,root,result.getvalue(),'base')
            self.assertFalse((root/'materials').exists());db.close()


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.server=make_server(self.root/'app.sqlite3',0,dev=True)
        self.port=self.server.server_address[1];self.url=f'http://127.0.0.1:{self.port}'
        self.server.origin=self.url;self.server.expected_host=f'127.0.0.1:{self.port}'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path,body=None,headers=None):
        common={'Origin':self.url,'Content-Type':'application/json'};common.update(headers or {})
        req=urllib.request.Request(self.url+path,None if body is None else json.dumps(body).encode(),common)
        try:r=self.opener.open(req)
        except urllib.error.HTTPError as e:r=e
        raw=r.read();return r.status,r.headers,json.loads(raw) if r.headers.get_content_type()=='application/json' else raw

    def test_token_required_first_user_only_and_local_login(self):
        self.assertTrue(self.request('/health')[2]['setup_required'])
        body={'username':'local-admin','password':'test-user-chosen-password','confirmation':'test-user-chosen-password'}
        token=self.server.setup_token
        self.assertEqual(self.request('/api/setup',body)[0],403)
        self.assertEqual(self.request('/api/setup',body,{'X-Setup-Token':token})[0],201)
        self.assertFalse(self.request('/health')[2]['setup_required'])
        self.assertEqual(self.request('/api/setup',body,{'X-Setup-Token':token})[0],403)
        code,_,login=self.request('/api/login',{'username':body['username'],'password':body['password']})
        self.assertEqual(code,200);self.assertEqual(login['role'],'admin')
        self.assertEqual(self.request('/api/me')[0],200)
        db=store.connect(self.root/'app.sqlite3')
        self.assertNotEqual(db.execute('SELECT password FROM users').fetchone()[0],body['password']);db.close()

    def test_script_mime_independent_of_windows_registry(self):
        from unittest.mock import patch
        with patch('mimetypes.guess_type',return_value=('text/plain',None)):
            code,headers,_=self.request('/app.js')
        self.assertEqual(code,200);self.assertEqual(headers.get_content_type(),'application/javascript')

    def test_busy_port_reports_actionable_error(self):
        result=subprocess.run([sys.executable,'start.py','--data-dir',str(self.root/'other'),'--port',str(self.port),'--no-browser'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,1);self.assertIn('уже занят',result.stdout)


if __name__=='__main__':unittest.main()
