"""Prepare a tested backend snapshot without changing teammates' working files."""
import argparse
import csv
import io
import os
import shutil
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unicodedata
from datetime import datetime

REVISION = 'bf2b9af642e0514c784df543aa2fde34e82172a1'
PREVIOUS_REVISIONS = {'0c8259ada55820dbdd4ec0c2ef8fa09fff896437',
                      '97b6d5fae50b692259204aa4cf285b9510b53caf'}
ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'Role04' / 'runtime' / 'backend'


def prepare(target=TARGET):
    target = Path(target)
    marker = target / 'SOURCE_COMMIT'
    upgrading = marker.is_file() and marker.read_text().strip() in PREVIOUS_REVISIONS
    if marker.is_file() and not upgrading:
        if marker.read_text().strip() != REVISION:
            raise RuntimeError('다른 버전의 사용 데이터가 있습니다. 기존 backend를 백업한 뒤 준비하세요.')
        print('이미 준비되어 있습니다. 등록한 파일과 갱신 데이터를 유지합니다.')
        return target
    if target.exists() and not upgrading:
        raise RuntimeError(f'완료되지 않은 준비 폴더가 있습니다. 내용을 확인하세요: {target}')
    try:
        archive = subprocess.check_output(
            ['git', 'archive', REVISION, 'Role01', 'Role02', 'Role03', 'update_data.py', 'auto_refresh.py', 'update_pipeline_integrated.py', 'requirements.txt'], cwd=ROOT)
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise RuntimeError('Git 설치와 저장소 이력이 필요합니다. git fetch origin main 후 다시 실행하세요.') from error
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=target.parent) as temporary:
        stage = Path(temporary) / 'backend'
        stage.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            for member in source:
                if not member.isfile() or '__pycache__' in member.name.split('/'):
                    continue
                destination = stage / member.name
                if not destination.resolve().is_relative_to(stage.resolve()):
                    raise ValueError('잘못된 저장소 경로입니다.')
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.extractfile(member).read())
        one = stage / 'Role01'
        paths = {unicodedata.normalize('NFC', p.relative_to(one).as_posix()): p
                 for p in (one / 'dataset' / 'files').rglob('*') if p.is_file()}
        with (one / 'metadata.csv').open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            key = row['path'].replace('\\', '/')
            key = key[key.index('dataset/files/'):] if 'dataset/files/' in key else key
            path = paths.get(unicodedata.normalize('NFC', key))
            if path is None:
                raise FileNotFoundError(f"원본이 없습니다: {row['path']}")
            # Keep original dates rather than the time of Git archive extraction.
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y.%m.%d %H:%M'):
                try:
                    stamp = datetime.strptime(row.get('modified_at', ''), fmt).timestamp()
                    os.utime(path, (stamp, stamp))
                    break
                except ValueError:
                    pass
        if upgrading:
            # Retain user files and edited metadata; reject ambiguous ID reuse.
            shutil.copytree(target / 'Role01' / 'dataset', one / 'dataset', dirs_exist_ok=True)
            for name in ('metadata.csv', 'extracted_text.csv'):
                with (one / name).open(encoding='utf-8-sig', newline='') as stream:
                    reader = csv.DictReader(stream)
                    columns, fresh = reader.fieldnames, list(reader)
                with (target / 'Role01' / name).open(encoding='utf-8-sig', newline='') as stream:
                    reader = csv.DictReader(stream)
                    columns = list(dict.fromkeys(columns + reader.fieldnames))
                    prior = list(reader)
                merged = {row['file_id']: row for row in fresh}
                for row in prior:
                    other = merged.get(row['file_id'])
                    if other and unicodedata.normalize('NFC', other['path'].replace('\\', '/')) != unicodedata.normalize('NFC', row['path'].replace('\\', '/')):
                        raise RuntimeError('업데이트 파일 ID 충돌: ' + row['file_id'])
                    merged[row['file_id']] = row
                with (one / name).open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=columns)
                    writer.writeheader(); writer.writerows(merged.values())
            for name in ('embedding_cache', '.extraction_cache.json', '.file_id_state.json'):
                source = target / 'Role01' / name
                if source.is_dir():
                    shutil.copytree(source, one / name, dirs_exist_ok=True)
                elif source.is_file():
                    shutil.copy2(source, one / name)
        (stage / 'SOURCE_COMMIT').write_text(REVISION + '\n')
        if upgrading:
            backup = target.with_name('backend-before-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            target.rename(backup)
            try:
                stage.rename(target)
            except BaseException:
                backup.rename(target)
                raise
            print(f'이전 데이터 백업: {backup}')
        else:
            stage.rename(target)
    print(f'검색·관계·DB 준비 완료: {len(rows)}개 파일 · {target}')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=Path, default=TARGET)
    prepare(parser.parse_args().target)
