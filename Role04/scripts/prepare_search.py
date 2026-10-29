"""Prepare an unmodified, pinned Role01 engine and its data from local Git objects."""
import csv
import io
import subprocess
import unicodedata
from search_api import original_path
from pathlib import Path

REVISION = '97a4cc8e6ac5889ede16ff21ec48eaf48a3d1cf6'
ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'Role04' / 'runtime' / 'search'


def main():
    names = ['search_engine.py', 'extracted_text.csv', 'metadata.csv',
             'embedding_cache/embeddings_73579b9955af12ca.npy']
    try:
        subprocess.run(['git', 'cat-file', '-e', f'{REVISION}:Role01/search_engine.py'], cwd=ROOT, check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise SystemExit('Git 이력이 필요합니다. Git 설치 후 저장소를 clone하고 git fetch origin main을 실행하세요.')
    contents = [(name, subprocess.check_output(['git', 'show', f'{REVISION}:Role01/{name}'], cwd=ROOT)) for name in names]
    for name, content in contents:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    tree = subprocess.check_output(['git', 'ls-tree', '-r', '-z', '--name-only', REVISION, 'Role01/dataset/files'], cwd=ROOT).decode().split('\0')
    source_paths = {unicodedata.normalize('NFC', name): name for name in tree if name}
    rows = list(csv.DictReader(io.StringIO(dict(contents)['metadata.csv'].decode('utf-8-sig'))))
    for row in rows:
        source = unicodedata.normalize('NFC', 'Role01/' + row['path'].replace('\\', '/'))
        if source not in source_paths:
            raise SystemExit(f'원본이 Git에 없습니다: {source}')
        destination = original_path(TARGET, row['file_id'], row['filename'])
        content = subprocess.check_output(['git', 'show', f'{REVISION}:{source_paths[source]}'], cwd=ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    print(f'원본 파일 준비 완료: {len(rows)}개')
    (TARGET / 'SOURCE_COMMIT').write_text(REVISION + '\n')
    print(f'검색 엔진 준비 완료: {TARGET}')


if __name__ == '__main__':
    main()
