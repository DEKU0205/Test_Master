import json
import tempfile
import unittest
from pathlib import Path
from cdek import store
from cdek.addendum import import_addendum
from cdek.materials import verify


class AddendumTests(unittest.TestCase):
    base=Path('/workspace/cdek-private/materials')
    add=Path('/workspace/cdek-private/packaging-addendum')

    @unittest.skipUnless(base.exists() and add.exists(),'Private material bundles not present')
    def test_versions_integrity_repeatability_and_packaging_scenarios(self):
        with tempfile.TemporaryDirectory() as temp:
            db=store.connect(Path(temp)/'test.sqlite');store.ingest(db,self.base)
            old={r['id']:r['hash'] for r in db.execute("SELECT * FROM sources WHERE id IN ('395','1037')")}
            report=import_addendum(db,self.add)
            self.assertEqual(report['integrity']['verified'],11)
            self.assertEqual(report['cargo_rows'],227)
            self.assertEqual(db.execute('SELECT count(*) FROM source_versions').fetchone()[0],2)
            for sid in ('395','1037'):
                row=db.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
                self.assertNotEqual(row['hash'],old[sid]);self.assertFalse(row['approved'])
                snapshot=json.loads(db.execute('SELECT snapshot FROM source_versions WHERE source_id=?',(sid,)).fetchone()[0])
                self.assertEqual(snapshot['hash'],old[sid]);self.assertTrue(snapshot['chunks'])
            count=db.execute('SELECT count(*) FROM chunks').fetchone()[0]
            import_addendum(db,self.add);store.ingest(db,self.base)
            self.assertEqual(db.execute('SELECT count(*) FROM chunks').fetchone()[0],count)
            self.assertEqual(db.execute('SELECT count(*) FROM source_versions').fetchone()[0],2)
            self.assertEqual(store.coverage(db)['approved_sources'],0)
            for query in ['колеса шины диски','кузовные элементы 50 см','жидкость риск протечки','несколько вложений','заводская упаковка','маркировка']:
                with self.subTest(query=query):
                    results=store.search(db,query,review=True,limit=40)
                    self.assertTrue(results);self.assertEqual(store.search(db,query),[])
            cargo=json.loads((self.add/'cargo-packaging.json').read_text())
            variants={sid:next(r for r in cargo if r['page_id']==sid and 'Автостекла' in r['cargo_example'] and 'до 50' in r['characteristics']) for sid in ('395','1037')}
            self.assertNotEqual(variants['395']['packaging'],variants['1037']['packaging'])
            for sid in ('395','1037'):
                key=variants[sid]['id'];chunk=db.execute('SELECT * FROM chunks WHERE source_id=? AND locator LIKE ?',(sid,key+' %')).fetchone()
                self.assertIn('Характеристики: '+variants[sid]['characteristics'],chunk['body'])
                self.assertIn('source_cell=',chunk['body']);self.assertIn('#h-',chunk['locator'])
            db.close()


if __name__=='__main__':unittest.main()
