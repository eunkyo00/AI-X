"""Inspect Role03 results; write evidence tables without changing source files.

Run file_db.py first. Standard library except optional PyMuPDF for PDF checks.
"""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import sqlite3
import unicodedata
import zipfile

from file_db import BASE, ROOT, local_path, normalize, read_csv


def canonical(value):
    return unicodedata.normalize('NFC', normalize(value))


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def inspect_pdf(path):
    try:
        import pymupdf
    except ImportError:
        return 'pdf_inspection_unavailable', 'PyMuPDF is not installed; OCR need is unconfirmed.'
    try:
        with pymupdf.open(path) as document:
            chars = sum(len(page.get_text().strip()) for page in document)
            image_pages = sum(bool(page.get_images()) for page in document)
            detail = f'pages={len(document)}, text_chars={chars}, image_pages={image_pages}'
            if len(document) and chars == 0 and image_pages:
                return 'image_pdf_needs_ocr', detail
            return 'pdf_requires_review', detail
    except Exception as error:
        return 'pdf_inspection_error', f'{type(error).__name__}: {error}'


def classify_reference(row, source, local_names, archive_names):
    reference = normalize(row['reference_path'])
    name = canonical(Path(reference).name)
    if row['status'] == 'ambiguous':
        return 'uncertain_registered_candidate', 'Confirm the directory; do not link by filename alone.'
    if '://' in row['reference_path']:
        return 'external_url', 'External resource; not evidence of a missing local file.'
    if row['relation_type'] == 'writes':
        return 'output_reference', 'A static output path; execution and file creation are unverified.'
    candidates = local_names.get(name, [])
    if candidates:
        return 'local_filename_candidate', 'Local filename candidates: ' + '; '.join(candidates)
    candidates = archive_names.get(name, [])
    if candidates:
        return 'archive_filename_candidate', 'Archive filename candidates: ' + '; '.join(str(z) + ':' + n for z, n in candidates)
    if row['relation_type'] == 'reads':
        return 'code_input_not_in_corpus', 'No filename candidate in the local corpus or supplied ZIPs.'
    if ('microsoft-data-science-for-beginners/' in normalize(source['path'])
            and Path(reference).suffix.lower() in {'.png', '.jpg', '.jpeg', '.svg'}):
        return 'sample_image_not_in_corpus', 'Sample document image reference; absent from the supplied corpus and ZIPs.'
    return 'document_reference_not_in_corpus', 'Explicit document reference; target absent from the supplied corpus and ZIPs.'


def run():
    output = BASE/'output'
    metadata = read_csv(BASE/'input/metadata.csv')
    texts = {r['file_id']: r for r in read_csv(BASE/'input/extracted_text.csv')}
    by_id = {r['file_id']: r for r in metadata}
    with sqlite3.connect(output/'files.sqlite3') as connection:
        connection.row_factory = sqlite3.Row
        effective = {r['file_id']: dict(r) for r in connection.execute('SELECT * FROM files')}
    local_names, archive_names = defaultdict(list), defaultdict(list)
    for path in (ROOT/'Role01/dataset/files').rglob('*'):
        if path.is_file():
            local_names[canonical(path.name)].append(str(path))
    archive_errors = []
    for path in sorted((ROOT/'data').rglob('*.zip')):
        try:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.endswith('/'):
                        archive_names[canonical(Path(normalize(name)).name)].append((path, name))
        except (OSError, zipfile.BadZipFile) as error:
            archive_errors.append({'path': str(path), 'error': str(error)})

    sizes, extraction, references = [], [], []
    for row in metadata:
        path = local_path(row['path'])
        if path is None or not path.is_file():
            continue
        actual = path.stat().st_size
        expected = int(row['size_bytes'])
        if actual != expected:
            data = path.read_bytes()
            category, proof = 'unexplained_size_difference', ''
            for archive_path, member in archive_names.get(canonical(row['filename']), []):
                try:
                    with zipfile.ZipFile(archive_path) as archive:
                        original = archive.read(member)
                    if (len(original) == expected and original != data
                            and original.replace(b'\r\n', b'\n') == data.replace(b'\r\n', b'\n')):
                        category = 'line_endings_only'
                        proof = str(archive_path) + ':' + member
                        break
                except (OSError, KeyError, zipfile.BadZipFile) as error:
                    archive_errors.append({'path': str(archive_path), 'error': str(error)})
            sizes.append(dict(file_id=row['file_id'], filename=row['filename'],
                              metadata_bytes=expected, actual_bytes=actual,
                              category=category, archive_proof=proof))
        imported = texts[row['file_id']]['extraction_status']
        if imported != 'success':
            stored = effective[row['file_id']]
            category, detail = 'requires_review', imported
            if stored['extraction_status'] == 'success':
                category, detail = 'recovered_tsv', 'Recovered into DB; original CSV retained.'
            elif row['filename'] in {'.DS_Store', '.Rhistory'}:
                category, detail = 'system_or_history_file', 'Retained ID; exclude from content search if appropriate.'
            elif actual == 0:
                category, detail = 'empty_source_file', 'Original file contains zero bytes.'
            elif path.suffix.lower() == '.pdf':
                category, detail = inspect_pdf(path)
            extraction.append(dict(file_id=row['file_id'], filename=row['filename'],
                                   imported_status=imported, db_status=stored['extraction_status'],
                                   category=category, detail=detail))
    for row in read_csv(output/'relations.csv'):
        if row['status'] == 'resolved':
            continue
        category, detail = classify_reference(row, by_id[row['source_id']], local_names, archive_names)
        references.append(dict(row, category=category, detail=detail))
    for name, rows in [('size_issues.csv', sizes), ('extraction_issues.csv', extraction),
                       ('reference_issues.csv', references)]:
        write_csv(output/name, rows)
    summary = dict(
        size_categories=dict(Counter(r['category'] for r in sizes)),
        extraction_categories=dict(Counter(r['category'] for r in extraction)),
        reference_categories=dict(Counter(r['category'] for r in references)),
        missing_references=sum(r['status'] == 'missing' for r in references),
        ambiguous_references=sum(r['status'] == 'ambiguous' for r in references),
        archive_errors=archive_errors,
    )
    (output/'quality_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == '__main__':
    run()
