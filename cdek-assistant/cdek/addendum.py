"""Versioned packaging addendum import, never a production approval."""
import json
import re
from pathlib import Path
from .materials import verify, digest, text_chunks
from .store import add_source, audit


def anchored_chunks(markdown, headings):
    lines = markdown.splitlines()
    lookup = {h['text'].strip(): h['id'] for h in headings if h['id']}
    anchor = ''
    for start in range(0, len(lines), 14):
        for line in lines[start:start+14]:
            if line.strip() in lookup:
                anchor = lookup[line.strip()]
        body = '\n'.join(lines[start:start+14]).strip()
        if body:
            yield f'L{start+1}-L{min(start+14,len(lines))}' + (' #' + anchor if anchor else ''), body


def import_addendum(db, root):
    root = Path(root).resolve()
    verified = verify(root)
    cargo = json.loads((root/'cargo-packaging.json').read_text())
    checks = json.loads((root/'extraction-checks.json').read_text())
    image_gaps = json.loads((root/'image-text-gaps.json').read_text())
    prepared = []
    for sid in ('395','1037'):
        old = db.execute('SELECT * FROM sources WHERE id=?', (sid,)).fetchone()
        if not old:
            raise ValueError('Import the base registry before its packaging addendum')
        source = json.loads((root/f'source-{sid}.json').read_text())
        tables = json.loads((root/f'tables-{sid}.json').read_text())
        rows = [c for c in cargo if c['page_id'] == sid]
        check = checks[sid]
        if len(tables) != check['tables'] or sum(len(t['rows']) for t in tables) != check['source_rows'] or len(rows) != check['cargo_rows'] or len(source['regions']) != check['regions']:
            raise ValueError('Addendum structure count mismatch: '+sid)
        mapped_cells = 0
        def normalized(text):
            # DOM textContent omits visual line breaks. Added image warnings are
            # annotations, not image interpretation or source requirements.
            return re.sub(r'\s+', '', re.sub(r'\[Изображение:[^\]]*\]', '', text))
        for table in tables:
            original = source['tables'][table['table']]
            for row in table['rows']:
                for cell in row['cells']:
                    raw = original['rows'][cell['source_row']]['cells'][cell['source_cell']]
                    if normalized(raw['text']) != normalized(cell['text']) or raw['rowspan'] != cell['rowspan'] or raw['colspan'] != cell['colspan']:
                        raise ValueError('Expanded cell differs from source DOM: '+sid)
                    mapped_cells += 1
        for item in rows:
            row = next(r for r in tables[0]['rows'] if r['row'] == item['source_row_zero_based'])
            if len(row['cells']) != 4 or [c['text'] for c in row['cells']] != [item[k] for k in ('cargo_category','cargo_example','characteristics','packaging')]:
                raise ValueError('Cargo row / expanded table mismatch: '+item['id'])
        md = (root/f'packaging-{sid}.md').read_text()
        meta = json.loads(old['metadata'])
        base_hash = meta.get('supersedes_base_hash', old['hash'])
        metadata = {'package':'packaging-addendum','file':f'packaging-{sid}.md', 'storage_root':'packaging-addendum',
                    'supersedes_base_hash':base_hash,'manifest_sha256':verified['manifest_sha256'],
                    'checked_at':source['checked_at'],'extraction_checks':check,
                    'mapped_cells_verified':mapped_cells,
                    'limitations':['No production approval. Mandatory packaging diagrams in appendices A–Г not fully reviewed.',
                                   'Empty image-text-gaps is not proof of complete image interpretation.',
                                   '395 and 1037 must not be merged; first establish section 1 applicability.'],
                    'image_gap_records':len(image_gaps),'parser_version':1}
        entry = {'id':sid,'title':old['title'],'url':source['source_url'],'revision':old['revision'].split(' · Дополнение')[0] + ' · Дополнение ' + source['checked_at'],
                 'hash':digest((root/f'packaging-{sid}.md').read_bytes()),'status':'latest_explicit','metadata':json.dumps(metadata,ensure_ascii=False)}
        chunks = list(anchored_chunks(md, source['headings']))
        heading = next(h['id'] for h in source['headings'] if h['text'].strip().startswith(('5 Типы' if sid=='395' else '6 Типы')))
        for item in rows:
            table_row = next(r for r in tables[0]['rows'] if r['row'] == item['source_row_zero_based'])
            coords = '; '.join(f"source_row={c['source_row']}, source_cell={c['source_cell']}, rowspan={c['rowspan']}, colspan={c['colspan']}" for c in table_row['cells'])
            body = '\n'.join([f"Документ {sid}. Раздел {item['section']}. Таблица 0, строка {item['source_row_zero_based']} (технические индексы с нуля, не номер пункта).",
                               'Применимость определяется разделом 1 этого документа. Таблица упаковки не является разрешением на приём груза.',
                               'Категория: '+item['cargo_category'],'Пример груза: '+item['cargo_example'],
                               'Характеристики: '+item['characteristics'],'Способ упаковки: '+item['packaging'],
                               'Исходные ячейки: '+coords,'DOM regions: '+', '.join(item['region_ids'])])
            chunks.append((f"{item['id']} #{heading}",body))
        prepared.append((entry,chunks))
    with db:
        for entry,chunks in prepared:
            add_source(db,entry,chunks)
        for key, note in [('395:appendices-A-G','Verify mandatory packaging diagrams in appendices А–Г; text extraction is not visual review.'),
                          ('395:scope-vs-1037','Establish section 1 applicability and cross-document precedence; do not merge domestic/international packaging methods.')]:
            db.execute('INSERT OR IGNORE INTO queue VALUES(?,?,?,?)',(key,110,'requires_review',json.dumps({'reason':note})))
        db.execute("INSERT INTO search(search) VALUES('rebuild')")
        report={'integrity':verified,'cargo_rows':len(cargo),'source_checks':checks,'production_approved':False}
        db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('packaging_addendum',json.dumps(report)))
        audit(db,'import','packaging_addendum_verified',details=report)
    return report
