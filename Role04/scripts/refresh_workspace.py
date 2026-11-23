"""Compatibility runner for the team's transactional update pipeline.

The team updater stages prior texts under .previous_extracted_text.csv, while
its extractor reads extracted_text.csv. Restore that input and verify hashes
against the prior audit before allowing cached OCR/text reuse.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unicodedata


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def seed_verified_texts(one, cache_source=None):
    previous = one / '.previous_extracted_text.csv'
    audit_path = one / '.previous_audit.csv'
    if not previous.is_file():
        return
    rows = read_csv(previous)
    audits = {row['file_id']: row for row in read_csv(audit_path)} if audit_path.is_file() else {}
    prior_cache = json.loads(cache_source.read_text(encoding='utf-8')) if cache_source and cache_source.is_file() else {}
    metadata = {row['file_id']: row for row in read_csv(one / 'metadata.csv')}
    folder = (one / 'dataset' / 'files').resolve()
    paths = {unicodedata.normalize('NFC', p.relative_to(folder).as_posix()): p for p in folder.rglob('*') if p.is_file()}
    cache = {}
    for row in rows:
        meta, audit = metadata.get(row['file_id']), audits.get(row['file_id'])
        if not meta or row.get('extraction_status') != 'success' or row['filename'] != meta['filename']:
            continue
        relative = meta['path'].replace('\\', '/').split('dataset/files/', 1)[-1]
        source = paths.get(unicodedata.normalize('NFC', relative))
        if not source or not source.resolve().is_relative_to(folder):
            continue
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        cached = prior_cache.get(row['file_id'], {})
        cache_matches = (unicodedata.normalize('NFC', cached.get('path', '').replace('\\', '/')) ==
                         unicodedata.normalize('NFC', meta['path'].replace('\\', '/')) and cached.get('sha256') == digest)
        audit_matches = bool(audit and audit.get('filename') == meta['filename'] and digest == audit.get('source_sha256'))
        if not (cache_matches or audit_matches):
            continue
        row['path'] = meta['path'].replace('\\', '/')
        cache[row['file_id']] = {'path': row['path'], 'sha256': digest}
    with (one / 'extracted_text.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (one / '.extraction_cache.json').write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')


def main(root):
    root = Path(root).resolve()
    spec = importlib.util.spec_from_file_location('team_update', root / 'update_data.py')
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    def runner(script, *args):
        if script.name == 'extract_content.py':
            seed_verified_texts(script.parent, root / 'Role01' / '.extraction_cache.json')
        subprocess.run([sys.executable, '-u', str(script), *map(str, args)], check=True)
        if script.name == 'extract_content.py':
            shutil.copy2(script.parent / '.extraction_cache.json', root / 'Role01' / '.extraction_cache.json')
    updater.update(root=root, runner=runner, snapshot=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    main(parser.parse_args().root)
