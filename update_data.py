"""Refresh metadata, extracted content, SQLite and search index as one operation."""
from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ["Role01/metadata.csv", "Role01/extracted_text.csv", "Role01/search_index",
             "Role03/output/files.sqlite3", "Role03/output/audit.csv",
             "Role03/output/relations.csv", "Role03/output/summary.json"]


def run_step(script, *args):
    subprocess.run([sys.executable, str(script), *map(str, args)], check=True,
                   env=dict(os.environ, PYTHONUNBUFFERED="1"))


def update(root=ROOT, runner=run_step):
    root = Path(root).resolve()
    lock = root / '.update-data.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError('다른 데이터 갱신이 진행 중입니다. 강제 종료 후에는 .update-data.lock을 확인하세요.')
    os.close(descriptor)
    try:
        with tempfile.TemporaryDirectory(prefix='.update-', dir=root) as temporary:
            stage = Path(temporary)
            one, three = stage/'Role01', stage/'Role03'
            one.mkdir(); three.mkdir()
            for name in ('paths.py', 'file_reload_code.py', 'extract_content.py', 'refresh_search.py'):
                shutil.copy2(root/'Role01'/name, one/name)
            shutil.copy2(root/'Role03/file_db.py', three/'file_db.py')
            (one/'dataset').symlink_to(root/'Role01/dataset', target_is_directory=True)
            if (root/'Role01/embedding_cache').is_dir():
                (one/'embedding_cache').symlink_to(root/'Role01/embedding_cache', target_is_directory=True)
            if (root/'data').is_dir():
                (stage/'data').symlink_to(root/'data', target_is_directory=True)
            if (root/'Role01/metadata.csv').exists():
                shutil.copy2(root/'Role01/metadata.csv', one/'metadata.csv')
            for source, name in ((root/'Role01/extracted_text.csv', '.previous_extracted_text.csv'),
                                 (root/'Role03/output/audit.csv', '.previous_audit.csv')):
                if source.is_file():
                    shutil.copy2(source, one/name)
            print('[1/4] 파일 목록과 메타데이터 갱신', flush=True)
            runner(one/'file_reload_code.py')
            print('[2/4] 전체 파일 본문 추출', flush=True)
            runner(one/'extract_content.py')
            # Per-file unsupported/empty content is valid; I/O/parser errors are not.
            import csv
            with (one/'extracted_text.csv').open(encoding='utf-8-sig', newline='') as stream:
                failures = [r for r in csv.DictReader(stream)
                            if r['extraction_status'].startswith('error:') or r['extraction_status']=='file_not_found']
            if failures:
                raise RuntimeError(f"본문 추출 실패 {len(failures)}건: {failures[0]['filename']} — {failures[0]['extraction_status']}")
            print('[3/4] DB와 파일 관계 갱신', flush=True)
            runner(three/'file_db.py', '--metadata', one/'metadata.csv', '--texts', one/'extracted_text.csv')
            print('[4/4] 검색 임베딩과 인덱스 갱신', flush=True)
            runner(one/'refresh_search.py', '--build-index')
            publish(root, stage)
            print('갱신 완료. 실행 중인 검색은 다음 검색부터 새 데이터를 사용합니다.', flush=True)
    finally:
        lock.unlink(missing_ok=True)


def publish(root, stage):
    """Keep a persistent backup and restore published files on an ordinary failure."""
    backup = root/'update_backups'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup.mkdir(parents=True)
    published = []
    try:
        for relative in ARTIFACTS:
            source, destination, saved = stage/relative, root/relative, backup/relative
            if not source.exists():
                raise FileNotFoundError(source)
            saved.parent.mkdir(parents=True, exist_ok=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            existed = destination.exists()
            if existed:
                os.replace(destination, saved)
            published.append((destination, saved, existed))
            os.replace(source, destination)
    except BaseException:
        for destination, saved, existed in reversed(published):
            if destination.is_dir():
                shutil.rmtree(destination)
            elif destination.exists():
                destination.unlink()
            if existed:
                os.replace(saved, destination)
        raise
    print(f'기존 데이터 백업: {backup}', flush=True)


if __name__ == '__main__':
    try:
        update()
    except Exception as error:
        print(f'갱신 실패: {error}', file=sys.stderr)
        sys.exit(1)
