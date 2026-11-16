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
             "Role03/output/relations.csv", "Role03/output/summary.json",
             "Role01/.file_id_state.json"]


def run_step(script, *args):
    subprocess.run([sys.executable, str(script), *map(str, args)], check=True,
                   env=dict(os.environ, PYTHONUNBUFFERED="1"))


class UpdateInProgress(RuntimeError):
    pass


class SourceChanged(RuntimeError):
    pass


def update(root=ROOT, runner=run_step, progress=None, snapshot=False, integrated=False):
    root = Path(root).resolve()
    lock = root / '.update-data.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise UpdateInProgress('다른 데이터 갱신이 진행 중입니다. 강제 종료 후에는 .update-data.lock을 확인하세요.')
    os.close(descriptor)
    try:
        with tempfile.TemporaryDirectory(prefix='.update-', dir=root) as temporary:
            stage = Path(temporary)
            one, three = stage/'Role01', stage/'Role03'
            one.mkdir(); three.mkdir()
            for name in ('paths.py', 'file_reload_code.py', 'extract_content.py', 'refresh_search.py'):
                shutil.copy2(root/'Role01'/name, one/name)
            shutil.copy2(root/'Role03/file_db.py', three/'file_db.py')
            if snapshot:
                def copy_stable(source, destination):
                    before = Path(source).stat()
                    shutil.copy2(source, destination)
                    after = Path(source).stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise SourceChanged('복사 중 파일이 변경되었습니다. 다음 자동 갱신에서 재시도합니다.')
                    return destination
                def ignore_source(folder, names):
                    return [name for name in names if name.startswith('.') or name in {'node_modules', '__pycache__'}
                            or (Path(folder)/name).is_symlink()]
                shutil.copytree(root/'Role01/dataset', one/'dataset', copy_function=copy_stable, ignore=ignore_source)
            else:
                (one/'dataset').symlink_to(root/'Role01/dataset', target_is_directory=True)
            if (root/'Role01/embedding_cache').is_dir():
                (one/'embedding_cache').symlink_to(root/'Role01/embedding_cache', target_is_directory=True)
            if (root/'data').is_dir():
                (stage/'data').symlink_to(root/'data', target_is_directory=True)
            if (root/'Role01/.file_id_state.json').exists():
                shutil.copy2(root/'Role01/.file_id_state.json', one/'.file_id_state.json')
            if (root/'Role01/metadata.csv').exists():
                shutil.copy2(root/'Role01/metadata.csv', one/'metadata.csv')
            for source, name in ((root/'Role01/extracted_text.csv', '.previous_extracted_text.csv'),
                                 (root/'Role03/output/audit.csv', '.previous_audit.csv')):
                if source.is_file():
                    shutil.copy2(source, one/name)
            if integrated:
                shutil.copy2(root/'update_pipeline_integrated.py', stage/'update_pipeline_integrated.py')
                shutil.copy2(root/'Role01/file_reload_append_only.py', one/'file_reload_append_only.py')
                two = stage/'Role02'
                two.mkdir()
                for name in ('description_generator.py', 'classify_metadata.py',
                             'project_classifier.py', 'project_classifier_v3.py', 'role_classifier.py'):
                    shutil.copy2(root/'Role02'/name, two/name)
                for name in ('project_classifier_artifacts_v3', 'role_classifier_artifacts'):
                    (two/name).symlink_to(root/'Role02'/name, target_is_directory=True)
                for name in ('metadata_description_generated.csv', 'metadata_classification_generated.csv',
                             'description_hashes.json'):
                    if (root/'Role02'/name).is_file():
                        shutil.copy2(root/'Role02'/name, two/name)
                for name in ('extracted_text.csv', '.extraction_cache.json'):
                    if (root/'Role01'/name).is_file():
                        shutil.copy2(root/'Role01'/name, one/name)
                if progress:
                    progress('본문 추출 · Qwen 설명 · 자동 분류 · 검색 인덱스 갱신')
                runner(stage/'update_pipeline_integrated.py')
            if progress:
                progress('파일 목록과 메타데이터 갱신')
            print('[1/4] 파일 목록과 메타데이터 갱신', flush=True)
            if not integrated:
                runner(one/'file_reload_code.py')
            if progress:
                progress('전체 파일 본문 추출')
            print('[2/4] 전체 파일 본문 추출', flush=True)
            if not integrated:
                runner(one/'extract_content.py')
            # Per-file unsupported/empty content is valid; I/O/parser errors are not.
            import csv
            with (one/'extracted_text.csv').open(encoding='utf-8-sig', newline='') as stream:
                failures = [r for r in csv.DictReader(stream)
                            if r['extraction_status'].startswith('error:') or r['extraction_status']=='file_not_found']
            if failures:
                raise RuntimeError(f"본문 추출 실패 {len(failures)}건: {failures[0]['filename']} — {failures[0]['extraction_status']}")
            if progress:
                progress('DB와 파일 관계 갱신')
            print('[3/4] DB와 파일 관계 갱신', flush=True)
            runner(three/'file_db.py', '--metadata', one/'metadata.csv', '--texts', one/'extracted_text.csv')
            if progress:
                progress('검색 임베딩과 인덱스 갱신')
            print('[4/4] 검색 임베딩과 인덱스 갱신', flush=True)
            if not integrated:
                runner(one/'refresh_search.py', '--build-index')
            if snapshot:
                import sqlite3
                old, live = str(one/'dataset/files'), str(root/'Role01/dataset/files')
                with sqlite3.connect(three/'output/files.sqlite3') as connection:
                    connection.execute('UPDATE files SET local_path=REPLACE(local_path,?,?)', (old, live))
                audit_path = three/'output/audit.csv'
                with audit_path.open(encoding='utf-8-sig', newline='') as stream:
                    reader = csv.DictReader(stream)
                    columns, rows = reader.fieldnames, list(reader)
                for row in rows:
                    row['local_path'] = row['local_path'].replace(old, live)
                with audit_path.open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=columns)
                    writer.writeheader(); writer.writerows(rows)
            artifacts = None
            if integrated:
                artifacts = [name for name in ARTIFACTS if name != 'Role01/.file_id_state.json']
                artifacts += ['Role02/metadata_description_generated.csv',
                              'Role02/metadata_classification_generated.csv',
                              'Role02/description_hashes.json', 'Role01/.extraction_cache.json']
            publish(root, stage, artifacts)
            print('갱신 완료. 실행 중인 검색은 다음 검색부터 새 데이터를 사용합니다.', flush=True)
    finally:
        lock.unlink(missing_ok=True)


def publish(root, stage, artifacts=None):
    """Keep a persistent backup and restore published files on an ordinary failure."""
    backup = root/'update_backups'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup.mkdir(parents=True)
    published = []
    try:
        for relative in (ARTIFACTS if artifacts is None else artifacts):
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
