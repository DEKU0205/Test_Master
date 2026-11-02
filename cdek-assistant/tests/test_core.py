import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from cdek import store, auth, model
from cdek.materials import verify, compare_workbooks, workbook


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.db = store.connect(':memory:')
        self.evidence = {k: 'Проверено ответственным сотрудником по оригиналу, запись проверки 123.' for k in ('currency','completeness','attachments','scope','conflicts','reference')}

    def tearDown(self):
        self.db.close()

    def source(self, sid='1', text='ТЕСТОВЫЙ ИСТОЧНИК: Условия авиа и авто различаются. Уточните объём ёмкости.', status='not_confirmed'):
        store.add_source(self.db, {'id':sid,'title':'Synthetic test fixture','url':'https://base.cdek.ru/page/'+sid,'revision':'TEST ONLY', 'hash':'hash-'+sid,'status':status,'metadata':'{}'}, [('L1-L1',text)])
        self.db.execute("INSERT INTO search(search) VALUES('rebuild')")
        self.db.commit()

    def approve(self, sid='1'):
        store.decision(self.db, sid, {'approve':True,'hash':'hash-'+sid,'evidence':self.evidence,'expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}, 'test-reviewer')

    def response(self, chunks, status='answer'):
        result = {'status':status, 'questions':[], 'sections':{s:[] for s in model.SECTIONS}}
        result['sections']['summary'] = [{'text':'Синтетический проверяемый вывод', 'citations':[{'chunk_id':chunks[0]['id'],'quote':'Условия авиа и авто различаются.'}]}]
        return result

    def test_unapproved_and_retired_not_searchable(self):
        self.source(); self.source('2', status='retired_explicit')
        self.assertEqual(store.search(self.db, 'авиа'), [])
        self.assertEqual(len(store.search(self.db, 'авиа', review=True)), 2)
        with self.assertRaises(ValueError): self.approve('2')

    def test_explicit_evidence_and_version_required(self):
        self.source()
        with self.assertRaises(ValueError): store.decision(self.db,'1',{'approve':True,'hash':'hash-1','evidence':{}},'test')
        with self.assertRaises(ValueError): store.decision(self.db,'1',{'approve':False,'hash':'wrong'},'test')
        self.assertEqual(store.coverage(self.db)['approved_sources'], 0)

    def test_approval_search_revoke_audit(self):
        self.source(); self.approve(); self.assertEqual(len(store.search(self.db,'авиа')),1)
        store.decision(self.db,'1',{'approve':False,'hash':'hash-1'},'test')
        self.assertEqual(store.search(self.db,'авиа'),[])
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit WHERE action IN ('approved','revoked')").fetchone()[0],2)

    def test_expiry(self):
        self.source();self.approve()
        self.db.execute("UPDATE sources SET expires_at='2000-01-01T00:00:00+00:00'")
        self.assertEqual(store.search(self.db,'авиа'),[])

    def test_expiry_offsets_normalized_to_utc(self):
        self.source()
        expires=(datetime.now(timezone.utc)+timedelta(hours=1)).astimezone(timezone(timedelta(hours=5)))
        store.decision(self.db,'1',{'approve':True,'hash':'hash-1','evidence':self.evidence,'expires_at':expires.isoformat()},'test')
        saved=self.db.execute('SELECT expires_at FROM sources').fetchone()[0]
        self.assertTrue(saved.endswith('+00:00'));self.assertEqual(len(store.search(self.db,'авиа')),1)

    def test_metadata_change_revokes_approval(self):
        self.source();self.approve()
        entry=dict(self.db.execute('SELECT * FROM sources').fetchone());entry['metadata']='{"currency_changed":true}';entry['status']='retired_explicit'
        store.add_source(self.db,entry,[('L1','Изменённая метаинформация')])
        self.assertEqual(store.coverage(self.db)['approved_sources'],0)

    def test_password_hash_sessions(self):
        hashed=auth.password_hash('Long test password!')
        self.assertNotIn('Long test password!',hashed)
        with self.db: self.db.execute('INSERT INTO users VALUES(?,?,?)',('test',hashed,'operator'))
        self.assertIsNone(auth.login(self.db,'test','wrong'))
        token,csrf,role=auth.login(self.db,'test','Long test password!')
        self.assertEqual(auth.session(self.db,token)['role'],'operator')
        self.assertNotEqual(self.db.execute('SELECT token FROM sessions').fetchone()[0], token)

    def test_no_source_no_model_call(self):
        def forbidden(_): raise AssertionError('Model must not be called without sources')
        for query in ['Неоднозначный груз','Духи 10 мл','Духи 1000 мл','Авиа в Анапу','Авто в Анапу','Нет сопроводительных документов','Шины отменённая редакция','Отсутствующий источник']:
            with self.subTest(query=query):
                result=model.answer(self.db,query,{},caller=forbidden)
                self.assertEqual(result['status'],'no_approved_sources')
                self.assertFalse(any(result['sections'].values()))

    def test_missing_model_not_fake_answer(self):
        self.source();self.approve()
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(model.ModelFailure):model.answer(self.db,'авиа',{})

    def test_citations_strict(self):
        self.source();self.approve();chunks=store.search(self.db,'авиа')
        good=self.response(chunks);self.assertEqual(model.validate_response(good,chunks)['status'],'answer')
        for citation in [[],[{'chunk_id':999,'quote':'Выдуманная цитата'}],[{'chunk_id':chunks[0]['id'],'quote':'Выдуманная цитата'}]]:
            bad=self.response(chunks);bad['sections']['summary'][0]['citations']=citation
            with self.assertRaises(model.ModelFailure):model.validate_response(bad,chunks)

    def test_revoked_during_generation(self):
        self.source();self.approve()
        def caller(messages):
            chunks=json.loads(messages[1]['content'])['approved_source_data']
            store.decision(self.db,'1',{'approve':False,'hash':'hash-1'},'test')
            return self.response(chunks)
        with self.assertRaises(model.ModelFailure):model.answer(self.db,'авиа',{},caller)

    def test_contexts_and_clarification_are_forwarded(self):
        self.source();self.approve()
        for transport,volume in [('Авиа','10 мл'),('Авиа','1000 мл'),('Авто','1000 мл')]:
            context={'transport':transport,'volume':volume,'documents':'нет','origin':'Москва','destination':'Анапа','cargo':'духи','transit':'неизвестен','tariff':'не уточнён','sender':'Физическое лицо','packaging':'заводская'}
            def caller(messages):
                data=json.loads(messages[1]['content']);self.assertEqual(data['route_and_cargo'],context)
                self.assertIn('Не выводи класс опасности',messages[0]['content'])
                result=self.response(data['approved_source_data'],'needs_details');result['questions']=['Каков состав и объём каждой ёмкости?','Есть ли документы?'];return result
            answer=model.answer(self.db,'авиа духи',context,caller)
            self.assertEqual(answer['status'],'needs_details');self.assertEqual(len(answer['questions']),2)

    def test_conflicting_materials_both_cited(self):
        self.source();self.source('2','ТЕСТОВЫЙ ИСТОЧНИК: Авиа требует дополнительной проверки.');self.approve();self.approve('2')
        def caller(messages):
            chunks=json.loads(messages[1]['content'])['approved_source_data'];result=self.response([next(c for c in chunks if c['source_id']=='1')],'needs_review')
            second=next(c for c in chunks if c['source_id']=='2')
            result['sections']['restrictions']=[{'text':'Другой тестовый источник требует проверки','citations':[{'chunk_id':second['id'],'quote':'Авиа требует дополнительной проверки.'}]}];return result
        self.assertEqual(model.answer(self.db,'авиа',{},caller)['status'],'needs_review')


class BundleTests(unittest.TestCase):
    root=Path('/workspace/cdek-private/materials')

    @unittest.skipUnless(root.exists(),'Original bundle not present')
    def test_manifest_and_spreadsheet_discrepancies(self):
        self.assertEqual(verify(self.root)['verified'],315)
        reports=compare_workbooks(self.root)
        self.assertTrue(all(r['differences'] for r in reports))
        self.assertEqual(sum(r['images_unreviewed'] for r in reports),137)
        cargo=workbook(self.root/'attachments/cargo-identification.xlsx')
        first=cargo['sheets'][0];cells={c['cell']:c['value'] for c in first['cells']}
        self.assertEqual(cells['A146'],'Духи');self.assertFalse((cells['B146'] or '').strip())
        self.assertIn('Косметика',cells['F146'])

    @unittest.skipUnless(root.exists(),'Original bundle not present')
    def test_import_repeatable_and_no_automatic_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            db=store.connect(Path(temp)/'test.sqlite')
            store.ingest(db,self.root)
            before=db.execute('SELECT count(*) FROM chunks').fetchone()[0]
            store.ingest(db,self.root)
            self.assertEqual(db.execute('SELECT count(*) FROM chunks').fetchone()[0],before)
            self.assertEqual(store.coverage(db)['total_sources'],206)
            self.assertEqual(store.coverage(db)['approved_sources'],0)
            self.assertFalse(store.search(db,'духи'))
            self.assertTrue(store.search(db,'духи',review=True))
            self.assertFalse(db.execute("SELECT 1 FROM chunks WHERE locator LIKE '%Идентификация ОГ (2)%'").fetchone())
            self.assertEqual(db.execute("SELECT status FROM sources WHERE id='2139'").fetchone()[0],'retired_explicit')
            db.close()


if __name__=='__main__':unittest.main()
