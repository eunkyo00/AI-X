"""Role03: read existing CSVs, store metadata and static reference evidence.
No source files are executed or modified. Python standard library only.
"""
from pathlib import Path
import argparse
import ast
import csv
import hashlib
from itertools import islice
import json
import posixpath
import re
import sqlite3

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def normalize(path):
    return posixpath.normpath(str(path).replace('\\', '/'))


def local_path(path):
    value = normalize(path)
    marker = 'dataset/files/'
    if marker not in value:
        return None
    candidate = (ROOT / 'Role01' / marker / value.split(marker, 1)[1]).resolve()
    folder = (ROOT / 'Role01' / marker).resolve()
    return candidate if candidate.is_relative_to(folder) else None


def validate(metadata, texts):
    for name, rows in [('metadata', metadata), ('extracted_text', texts)]:
        ids = [row.get('file_id', '') for row in rows]
        if not all(ids) or len(ids) != len(set(ids)):
            raise ValueError(f'{name}: empty or duplicate file_id')
    if {r['file_id'] for r in metadata} != {r['file_id'] for r in texts}:
        raise ValueError('CSV file_id sets differ')
    by_id = {r['file_id']: r for r in texts}
    for row in metadata:
        text = by_id[row['file_id']]
        if row['filename'] != text['filename'] or normalize(row['path']) != normalize(text['path']):
            raise ValueError(f"CSV identity mismatch: {row['file_id']}")


def recover_tsv(text, local):
    """Recover unsupported TSV text locally without changing the input CSV."""
    if (not local or local.suffix.lower() != '.tsv'
            or text['extraction_status'] not in {'unsupported_extension', 'empty_text'}):
        return text
    try:
        with local.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(islice(csv.reader(stream, delimiter='\t'), 101))
        content = '\n'.join(' | '.join(row) for row in rows[:100])
        if len(rows) > 100:
            content += '\n[행 제한으로 일부 생략]'
        return dict(text, extracted_text=content[:100_000],
                    extraction_status='success' if content.strip() else 'empty_text')
    except (OSError, UnicodeError, csv.Error) as error:
        return dict(text, extraction_status=f'error: {type(error).__name__}: {error}')


def code_references(text, extension):
    """Only literal paths in supported static calls; never infer execution."""
    if extension in {'.py', '.ipynb'}:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return
        read = {'read_csv', 'read_table', 'read_excel', 'read_json', 'read_parquet', 'loadtxt', 'genfromtxt', 'imread'}
        write = {'to_csv', 'to_excel', 'to_json', 'to_parquet', 'savefig', 'savetxt', 'imwrite'}
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ''
            values = list(node.args[:1]) or [kw.value for kw in node.keywords if kw.arg in {'filepath_or_buffer', 'path_or_buf', 'path', 'fname', 'file', 'io'}]
            if not values or not isinstance(values[0], ast.Constant) or not isinstance(values[0].value, str):
                continue
            kind = 'reads' if name in read else 'writes' if name in write else None
            if name == 'open':
                mode = node.args[1] if len(node.args) > 1 else next((kw.value for kw in node.keywords if kw.arg == 'mode'), ast.Constant(value='r'))
                if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str):
                    continue
                kind = 'writes' if any(c in mode.value for c in 'wax+') else 'reads'
            if kind:
                yield values[0].value, kind, node.lineno, '\n'.join(lines[node.lineno - 1:node.end_lineno]).strip()
    elif extension == '.r':
        # A supported call must be on one line; # comments outside quotes are removed.
        pattern = re.compile(r'''(?<![\w.])(?P<call>read\.csv2?|read\.table|readRDS|fread|scan|load|write\.csv2?|write\.table|saveRDS|fwrite)\s*\(\s*(?:(?:file|input)\s*=\s*)?(?P<quote>["'])(?P<path>.*?)(?P=quote)''')
        writes = re.compile(r'''(?<![\w.])(?P<call>write\.csv2?|write\.table|saveRDS|fwrite)\s*\(.*?(?:,\s*(?:file\s*=\s*)?|file\s*=\s*)(?P<quote>["'])(?P<path>.*?)(?P=quote)''')
        for number, line in enumerate(text.splitlines(), 1):
            quote = None
            end = len(line)
            for i, char in enumerate(line):
                if char in "\"'" and (i == 0 or line[i-1] != '\\'):
                    quote = None if quote == char else char if quote is None else quote
                if char == '#' and quote is None:
                    end = i
                    break
            code = line[:end]
            for match in pattern.finditer(code):
                if match['call'].startswith(('write', 'save', 'fwrite')):
                    continue
                yield match['path'], 'reads', number, line.strip()
            for match in writes.finditer(code):
                yield match['path'], 'writes', number, line.strip()


def document_references(text, files):
    """Extract explicit filenames even when the target is not registered.

    Locations are offsets in extracted text, not original PDF page numbers.
    Quoted names and Markdown destinations can contain spaces.
    """
    extensions = {'csv', 'tsv', 'xlsx', 'xls', 'json', 'parquet', 'txt',
                  'pdf', 'docx', 'pptx', 'md', 'py', 'r', 'ipynb', 'png',
                  'jpg', 'jpeg', 'svg', 'rds', 'rdata', 'zip'}
    extensions.update(f['filename'].rsplit('.', 1)[-1].lower()
                      for f in files if '.' in f['filename'])
    suffix = r'\.(?:' + '|'.join(re.escape(e) for e in sorted(extensions)) + r')'
    patterns = [
        re.compile(r'(?P<quote>[`\"\'])(?P<path>[^\n`\"\']+?' + suffix + r')(?P=quote)', re.I),
        re.compile(r'\]\((?P<path>[^\n)]+?' + suffix + r')(?:#[^\s)]*)?\)', re.I),
        re.compile(r'(?<![\w.])(?P<path>(?:[A-Za-z]:)?[\w./\\-]+?' + suffix + r')(?![\w.])', re.I),
    ]
    matches = []
    external_links = [match.span() for match in re.finditer(
        r'(?<!!)\[[^\[\]\n]*\]\(\s*https?://[^)\n]*\)', text, re.I)]
    for pattern in patterns:
        for match in pattern.finditer(text):
            start, end = match.span('path')
            if not any(start < b and end > a for a, b, _ in matches):
                matches.append((start, end, match['path']))
    # Preserve exact registered names with spaces in unquoted prose, too.
    for name in sorted({f['filename'] for f in files}, key=len, reverse=True):
        for match in re.finditer(r'(?<![\w.])' + re.escape(name) + r'(?![\w.])', text):
            start, end = match.span()
            if not any(start < b and end > a for a, b, _ in matches):
                matches.append((start, end, name))
    for start, end, reference in sorted(matches):
        if any(start < b and end > a for a, b in external_links):
            continue
        prefix = text[:start].rsplit(None, 1)[-1] if text[:start].strip() else ''
        if '://' in prefix + reference:
            continue
        yield reference, start, text[max(0, start-60):end+60]


def resolve_reference(source, reference, files, *, filename_only=False):
    ref = normalize(reference)
    source_path = normalize(source['path'])
    expected = {normalize(posixpath.join(posixpath.dirname(source_path), ref))}
    if posixpath.isabs(ref) or re.match(r'^[A-Za-z]:/', ref):
        expected = {ref}
    exact = [f for f in files if normalize(f['path']) in expected and f['file_id'] != source['file_id']]
    if len(exact) == 1 and not filename_only:
        return exact[0]['file_id'], 'resolved', 'exact_path'
    # A filename alone does not prove the directory, especially with setwd/chdir.
    candidates = [f for f in files if f['filename'] == posixpath.basename(ref) and f['file_id'] != source['file_id']]
    return None, 'ambiguous' if candidates else 'missing', 'filename_candidate' if candidates else 'not_registered'


def connect(db):
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    return connection


def get_file(db, file_id):
    with connect(db) as connection:
        row = connection.execute('SELECT * FROM files WHERE file_id=?', (file_id,)).fetchone()
        return dict(row) if row else None


def get_relations(db, file_id):
    with connect(db) as connection:
        return [dict(r) for r in connection.execute('SELECT * FROM relations WHERE source_id=? OR target_id=? ORDER BY relation_id', (file_id, file_id))]


def build(metadata_path, text_path, output):
    metadata, texts = read_csv(metadata_path), read_csv(text_path)
    validate(metadata, texts)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    by_id = {r['file_id']: r for r in texts}
    audit, relations = [], []
    for row in metadata:
        text = by_id[row['file_id']]
        local = local_path(row['path'])
        exists = bool(local and local.is_file())
        if exists:
            text = recover_tsv(text, local)
            by_id[row['file_id']] = text
        audit.append({'file_id': row['file_id'], 'filename': row['filename'], 'extraction_status': text['extraction_status'], 'local_exists': exists, 'local_path': str(local) if local else '', 'text_length': len(text['extracted_text']), 'source_sha256': hashlib.sha256(local.read_bytes()).hexdigest() if exists else '', 'size_matches': local.stat().st_size == int(row['size_bytes']) if exists else False})
        sources = []
        extension = row['extension'].lower()
        if exists and extension in {'.py', '.r'}:
            sources = [(local.read_text(encoding='utf-8', errors='replace'), 'source_line')]
        elif exists and extension == '.ipynb':
            notebook = json.loads(local.read_text(encoding='utf-8'))
            sources = [(''.join(cell.get('source', [])), f'notebook_cell_{index}') for index, cell in enumerate(notebook.get('cells', []), 1) if cell.get('cell_type') == 'code']
        for content, location in sources:
            for reference, kind, line, evidence in code_references(content, extension):
                target, status, method = resolve_reference(row, reference, metadata)
                relations.append({'source_id': row['file_id'], 'target_id': target, 'relation_type': kind, 'reference_path': reference, 'status': status, 'match_method': method, 'evidence_location': f'{location}:{line}', 'evidence': evidence})
        if extension in {'.pdf', '.docx', '.pptx', '.md', '.txt'}:
            for reference, offset, evidence in document_references(text['extracted_text'], metadata):
                target, status, method = resolve_reference(row, reference, metadata, filename_only='/' not in reference and '\\' not in reference)
                relations.append({'source_id': row['file_id'], 'target_id': target, 'relation_type': 'mentions', 'reference_path': reference, 'status': status, 'match_method': method, 'evidence_location': f'extracted_text_char:{offset}', 'evidence': evidence})
    db = output / 'files.sqlite3'
    with connect(db) as connection:
        connection.executescript('''CREATE TABLE IF NOT EXISTS files(file_id TEXT PRIMARY KEY, filename TEXT NOT NULL, path TEXT NOT NULL, local_path TEXT, extension TEXT, size_bytes INTEGER, created_at TEXT, modified_at TEXT, project TEXT, role TEXT, description TEXT, extracted_text TEXT, extraction_status TEXT);
        CREATE TABLE IF NOT EXISTS relations(relation_id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES files(file_id), target_id TEXT REFERENCES files(file_id), relation_type TEXT, reference_path TEXT, status TEXT, match_method TEXT, evidence_location TEXT, evidence TEXT);
        CREATE TABLE IF NOT EXISTS provenance(input_name TEXT PRIMARY KEY, sha256 TEXT);
        ''')
        connection.execute('DELETE FROM relations')
        connection.execute('DELETE FROM files')
        for row, check in zip(metadata, audit):
            text = by_id[row['file_id']]
            connection.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', tuple([row['file_id'], row['filename'], row['path'], check['local_path'], row['extension'], int(row['size_bytes']), row['created_at'], row['modified_at'], row['project'], row['role'], row['description'], text['extracted_text'], text['extraction_status']]))
        for relation in relations:
            connection.execute('INSERT INTO relations(source_id,target_id,relation_type,reference_path,status,match_method,evidence_location,evidence) VALUES(?,?,?,?,?,?,?,?)', tuple(relation.values()))
        for path in [metadata_path, text_path]:
            path = Path(path)
            connection.execute('INSERT OR REPLACE INTO provenance VALUES(?,?)', (path.name, hashlib.sha256(path.read_bytes()).hexdigest()))
    for filename, rows in [('audit.csv', audit), ('relations.csv', relations)]:
        columns = (list(rows[0]) if rows else
                   ['file_id', 'filename', 'extraction_status', 'local_exists', 'local_path', 'text_length', 'source_sha256', 'size_matches']
                   if filename == 'audit.csv' else
                   ['source_id', 'target_id', 'relation_type', 'reference_path', 'status', 'match_method', 'evidence_location', 'evidence'])
        with (output / filename).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    summary = {'files': len(metadata), 'extraction_success': sum(t['extraction_status']=='success' for t in by_id.values()), 'local_files_found': sum(a['local_exists'] for a in audit), 'size_mismatches': sum(a['local_exists'] and not a['size_matches'] for a in audit), 'references': len(relations), 'resolved': sum(r['status']=='resolved' for r in relations), 'ambiguous': sum(r['status']=='ambiguous' for r in relations), 'missing': sum(r['status']=='missing' for r in relations)}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata', type=Path, default=BASE/'input/metadata.csv')
    parser.add_argument('--texts', type=Path, default=BASE/'input/extracted_text.csv')
    parser.add_argument('--output', type=Path, default=BASE/'output')
    args = parser.parse_args()
    print(json.dumps(build(args.metadata, args.texts, args.output), ensure_ascii=False, indent=2))
