"""Read untrusted bundles without executing their HTML or spreadsheet formulas."""
import hashlib
import json
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'checksums.json').read_text(encoding='utf-8-sig'))
    failures = []
    for name, expected in manifest.items():
        p = (root / name).resolve()
        if not p.is_relative_to(root) or not p.is_file() or digest(p.read_bytes()) != expected:
            failures.append(name)
    if failures:
        raise ValueError('SHA256 mismatch or missing file: ' + ', '.join(failures))
    return {'verified': len(manifest), 'failures': [], 'manifest_sha256': digest((root / 'checksums.json').read_bytes())}


def workbook(path):
    """Preserve every nonempty cell, cached formula, merged range and drawing count."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS):
                shared.append(''.join(si.itertext()))
        rels = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        sheets = []
        for sheet in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet', NS):
            rid = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target = rels[rid]
            name = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            xml = ET.fromstring(z.read(name))
            cells = []
            for c in xml.findall('.//s:sheetData/s:row/s:c', NS):
                value = c.find('s:v', NS)
                value = value.text if value is not None else None
                if c.get('t') == 's' and value is not None:
                    value = shared[int(value)]
                if c.get('t') == 'inlineStr':
                    value = ''.join(c.find('s:is', NS).itertext())
                formula = c.find('s:f', NS)
                if value is not None or formula is not None:
                    cells.append({'cell': c.attrib['r'], 'type': c.get('t'), 'value': value,
                                  'formula': formula.text if formula is not None else None})
            sheets.append({'name': sheet.attrib['name'], 'state': sheet.get('state', 'visible'),
                           'cells': cells, 'merged_ranges': [m.attrib['ref'] for m in xml.findall('s:mergeCells/s:mergeCell', NS)]})
        return {'sheets': sheets, 'images': len([n for n in z.namelist() if n.startswith('xl/media/')])}


def compare_workbooks(root):
    reports = []
    for p in sorted((Path(root) / 'attachments').glob('*.xlsx')):
        actual = workbook(p)
        supplied = json.loads(Path(str(p) + '.json').read_text(encoding='utf-8-sig'))
        differences = []
        for a, b in zip(actual['sheets'], supplied['sheets']):
            aa = {c['cell']: (c['value'], c['formula']) for c in a['cells']}
            bb = {c['cell']: (c['value'], c['formula']) for c in b['cells'] if c['value'] is not None or c['formula'] is not None}
            if a['name'] != b['name'] or aa != bb:
                differences.append(a['name'] + ': cells or sheet name differ')
            expected_merges = b.get('merged_ranges', b.get('merges', []))
            if a['merged_ranges'] != expected_merges:
                differences.append(a['name'] + ': merged ranges differ')
        if len(actual['sheets']) != len(supplied['sheets']):
            differences.append('sheet count differs')
        reports.append({'file': p.name, 'sheets': len(actual['sheets']), 'cells': sum(len(s['cells']) for s in actual['sheets']),
                        'images_unreviewed': actual['images'], 'differences': differences,
                        'scope': 'Cell values, cached formulas and merged ranges only; no visual or currency approval.'})
    return reports


def text_chunks(text):
    """Stable line citations, including headings; never render source HTML."""
    lines = text.splitlines()
    for start in range(0, len(lines), 14):
        body = '\n'.join(lines[start:start + 14]).strip()
        if body:
            yield f'L{start + 1}-L{min(start + 14, len(lines))}', body


def table_chunks(sheet):
    rows = {}
    for c in sheet['cells']:
        row = int(re.search(r'\d+', c['cell'])[0])
        rows.setdefault(row, []).append(c)
    # Include column-header context and all merges; do not interpret Да/+.
    header = '\n'.join(f"{c['cell']}: {c['value']}" for c in sheet['cells'] if int(re.search(r'\d+', c['cell'])[0]) <= 6)
    for row, cells in rows.items():
        body = '\n'.join(f"{c['cell']}: {c['value']}" + (f" [formula: {c['formula']}; cached]" if c['formula'] else '') for c in cells)
        relevant = [m for m in sheet['merged_ranges'] if min(map(int, re.findall(r'\d+', m))) <= row <= max(map(int, re.findall(r'\d+', m)))]
        yield f"{sheet['name']}!{cells[0]['cell']}:{cells[-1]['cell']}", f"Лист: {sheet['name']}\nКонтекст заголовков:\n{header}\nСтрока:\n{body}\nОбъединения строки: {', '.join(relevant)}"
