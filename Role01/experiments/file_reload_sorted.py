from pathlib import Path
from datetime import datetime
import argparse
import csv
import os
import re
import shutil
import tempfile

# Role01/file_reload_code.py 에 저장하여 실행하세요.
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'dataset' / 'files'
METADATA_CSV = BASE_DIR / 'metadata.csv'

EXCLUDED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.mp4', '.avi', '.mov'}
EXCLUDED_FILENAMES = {'.DS_Store', '.Rhistory', 'SOURCE.json', 'LICENSE'}
COLUMNS = ['file_id', 'filename', 'extension', 'path', 'size_bytes',
           'created_at', 'modified_at', 'project', 'role', 'description']


def normalize_path(value):
    """절대/상대 경로와 슬래시 방향을 통일해 비교한다."""
    value = str(value or '').strip().strip('"').replace('\\', '/')
    if not value:
        return ''
    value = re.sub(r'/+', '/', value)
    # 과거 CSV에 절대경로가 기록된 경우에도 dataset/files 이후를 기준으로 비교
    marker = 'dataset/files/'
    lowered = value.casefold()
    idx = lowered.find(marker)
    if idx >= 0:
        value = value[idx:]
    else:
        value = value.removeprefix('./')
    return value.casefold()


def id_number(value):
    match = re.fullmatch(r'F(\d+)', str(value or '').strip(), re.I)
    return int(match.group(1)) if match else None


def sort_key(row):
    number = id_number(row.get('file_id'))
    return (number is None, number if number is not None else float('inf'))


def timestamp(seconds):
    return datetime.fromtimestamp(seconds).strftime('%Y-%m-%d %H:%M:%S')


def read_existing():
    if not METADATA_CSV.exists():
        return [], COLUMNS.copy()
    with METADATA_CSV.open('r', newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError('metadata.csv에 헤더가 없습니다.')
        fields = list(reader.fieldnames)
        if len(fields) != len(set(fields)):
            raise ValueError('metadata.csv에 중복된 열 이름이 있습니다.')
        rows = list(reader)
    for name in COLUMNS:
        if name not in fields:
            fields.append(name)
    for row in rows:
        if None in row:
            raise ValueError('CSV 행에 헤더보다 많은 값이 있습니다. 원본을 확인하세요.')
        for field in fields:
            row.setdefault(field, '')
    return rows, fields


def main():
    parser = argparse.ArgumentParser(description='기존 메타데이터 값은 유지하고 신규 파일만 추가, file_id 순 정렬')
    parser.add_argument('--dry-run', action='store_true', help='변경 예정만 출력하고 저장하지 않음')
    args = parser.parse_args()

    if not DATA_DIR.is_dir():
        raise FileNotFoundError(f'파일 폴더가 없습니다: {DATA_DIR}')

    existing, fields = read_existing()
    known_paths = set()
    used_ids = set()
    numbers = []
    for row in existing:
        file_id = row.get('file_id', '').strip()
        if not file_id or file_id in used_ids:
            raise ValueError(f'빈 ID 또는 중복 ID가 있습니다: {file_id!r}')
        used_ids.add(file_id)
        num = id_number(file_id)
        if num is not None:
            numbers.append(num)
        key = normalize_path(row.get('path'))
        if key:
            if key in known_paths:
                raise ValueError(f'기존 CSV에 중복 경로가 있습니다: {row.get("path")}')
            known_paths.add(key)

    next_number = max(numbers, default=0) + 1
    new_rows = []
    excluded = 0
    scanned = 0
    for file_path in sorted(DATA_DIR.rglob('*'), key=lambda p: p.as_posix().casefold()):
        if not file_path.is_file():
            continue
        scanned += 1
        if (file_path.name in EXCLUDED_FILENAMES or
                file_path.name.startswith('~$') or
                file_path.suffix.lower() in EXCLUDED_EXTENSIONS):
            excluded += 1
            continue
        rel_path = file_path.relative_to(BASE_DIR).as_posix()
        key = normalize_path(rel_path)
        if key in known_paths:
            continue
        while f'F{next_number:03d}' in used_ids:
            next_number += 1
        file_id = f'F{next_number:03d}'
        next_number += 1
        used_ids.add(file_id)
        known_paths.add(key)
        stat = file_path.stat()
        row = {field: '' for field in fields}
        row.update({
            'file_id': file_id,
            'filename': file_path.name,
            'extension': file_path.suffix.lower(),
            'path': rel_path,
            'size_bytes': str(stat.st_size),
            # Windows는 생성 시간, 다른 OS에서는 확인 가능한 birthtime만 사용
            'created_at': timestamp(stat.st_birthtime) if hasattr(stat, 'st_birthtime')
                          else (timestamp(stat.st_ctime) if os.name == 'nt' else ''),
            'modified_at': timestamp(stat.st_mtime),
        })
        new_rows.append(row)
        print(f'[신규] {file_id}: {rel_path}')

    combined = existing + new_rows
    ordered = sorted(combined, key=sort_key)
    needs_sort = combined != ordered
    print(f'기존 CSV 행 수: {len(existing)}')
    print(f'탐색한 파일 수: {scanned} (제외: {excluded})')
    print(f'신규 파일 수: {len(new_rows)}')
    print(f'ID 정렬 필요: {"예" if needs_sort else "아니오"}')
    print(f'최종 CSV 행 수: {len(ordered)}')

    if args.dry_run:
        print('[미리보기] CSV를 변경하지 않았습니다.')
        return
    if not new_rows and not needs_sort:
        print('변경 사항이 없어 metadata.csv를 그대로 유지했습니다.')
        return

    # 기존 파일이 있으면 저장 전 백업. 신규 파일과 정렬 외 기존 행 값은 변경하지 않음.
    if METADATA_CSV.exists():
        backup = BASE_DIR / f'metadata_backup_{datetime.now():%Y%m%d_%H%M%S_%f}.csv'
        shutil.copy2(METADATA_CSV, backup)
        print(f'백업: {backup.name}')

    # 임시 파일에 완성 후 원자적 교체하여 중간 실패 시 원본 손상 방지
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8-sig',
                                         dir=BASE_DIR, prefix='metadata_tmp_', suffix='.csv',
                                         delete=False) as handle:
            temp_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='raise')
            writer.writeheader()
            writer.writerows(ordered)
        os.replace(temp_path, METADATA_CSV)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    print(f'저장 완료: {METADATA_CSV}')


if __name__ == '__main__':
    main()
