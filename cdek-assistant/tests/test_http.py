import http.cookiejar
import json
import secrets
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from cdek.server import Handler
from cdek import auth, store


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name)/'test.sqlite'
        db=store.connect(cls.path);cls.password=secrets.token_urlsafe(24)
        for name,role in [('administrator','admin'),('operator','operator')]:
            db.execute('INSERT INTO users VALUES(?,?,?)',(name,auth.password_hash(cls.password),role))
        store.add_source(db,{'id':'1','title':'Private test document','url':'https://base.cdek.ru/page/1','revision':'TEST','hash':'123','status':'not_confirmed','metadata':'{}'},[('L1','Private internal test content')])
        db.execute("INSERT INTO search(search) VALUES('rebuild')")
        db.commit();db.close()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.port=cls.server.server_address[1]
        cls.origin=f'http://127.0.0.1:{cls.port}';cls.server.origin=cls.origin;cls.server.expected_host=f'127.0.0.1:{cls.port}'
        cls.server.db_path=cls.path;cls.server.secure=False;cls.server.attempts={};cls.server.lock=threading.Lock();cls.server.model_slots=threading.BoundedSemaphore(2)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()

    def setUp(self):
        self.cookies=http.cookiejar.CookieJar();self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(self.cookies));self.csrf=''
        with self.server.lock:self.server.attempts.clear()

    def request(self,path,body=None,origin=None,csrf=None,host=None):
        headers={}
        if body is not None:headers={'Content-Type':'application/json','Origin':origin or self.origin,'X-CSRF-Token':self.csrf if csrf is None else csrf}
        if host:headers['Host']=host
        req=urllib.request.Request(self.origin+path,None if body is None else json.dumps(body).encode(),headers)
        try:response=self.opener.open(req)
        except urllib.error.HTTPError as error:response=error
        raw=response.read();return response.status,response.headers,json.loads(raw) if response.headers.get_content_type()=='application/json' else raw

    def login(self,user='operator'):
        code,headers,data=self.request('/api/login',{'username':user,'password':self.password});self.assertEqual(code,200);self.csrf=data['csrf'];return headers

    def test_auth_and_no_public_documents(self):
        self.assertEqual(self.request('/')[0],200)
        for path in ['/api/coverage','/api/source?id=1','/materials/registry.json','/../app.sqlite3','/api/admin/original?id=1']:
            self.assertEqual(self.request(path)[0],401)

    def test_operator_cannot_review(self):
        headers=self.login();self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertEqual(self.request('/api/admin/sources')[0],403)
        self.assertEqual(self.request('/api/search',{'query':'internal','review':True})[0],403)
        self.assertEqual(self.request('/api/source?id=1')[0],404)
        self.assertEqual(self.request('/api/search',{'query':'internal'})[2]['results'],[])

    def test_csrf_and_origin(self):
        self.login()
        self.assertEqual(self.request('/api/answer',{'query':'duhi'},csrf='bad')[0],403)
        self.assertEqual(self.request('/api/answer',{'query':'duhi'},origin='https://attacker.test')[0],403)
        self.assertEqual(self.request('/api/me',host='attacker.test')[0],403)

    def test_admin_inspection_and_queue_permissions(self):
        self.login('administrator')
        self.assertEqual(self.request('/api/admin/sources')[0],200)
        self.assertEqual(len(self.request('/api/search',{'query':'internal','review':True})[2]['results']),1)
        self.assertEqual(self.request('/api/source?id=1')[0],200)

    def test_no_sources_and_logout(self):
        self.login()
        code,_,data=self.request('/api/answer',{'query':'Духи 1000 мл без документов','context':{'transport':'Авиа'}})
        self.assertEqual(code,200);self.assertEqual(data['status'],'no_approved_sources')
        self.assertEqual(self.request('/api/logout',{})[0],200)
        self.assertEqual(self.request('/api/me')[0],401)

    def test_rate_limit(self):
        for _ in range(8):self.assertEqual(self.request('/api/login',{'username':'missing','password':'wrong'})[0],401)
        self.assertEqual(self.request('/api/login',{'username':'missing','password':'wrong'})[0],429)


if __name__=='__main__':unittest.main()
