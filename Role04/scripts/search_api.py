"""Bridge the current team backend to the existing gui-v1 browser interface."""
import base64
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import uuid
from contextlib import closing
from datetime import datetime

MAX_UPLOAD = 25 * 1024 * 1024
UPLOAD_EXTENSIONS = {'.pdf', '.csv', '.tsv', '.xlsx', '.txt', '.py', '.r', '.docx', '.pptx', '.md', '.json', '.ipynb', '.html', '.css', '.js', '.sql'}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Latest engine imports a sibling; keep staged/live modules isolated.
    sibling = Path(path).parent / 'refresh_search.py'
    previous = sys.modules.pop('refresh_search', None) if sibling.is_file() else None
    sys.path.insert(0, str(Path(path).parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
        if sibling.is_file():
            sys.modules.pop('refresh_search', None)
            if previous is not None:
                sys.modules['refresh_search'] = previous
    return module


def original_path(engine_dir, file_id, filename):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', str(file_id)):
        raise ValueError('잘못된 파일 ID입니다.')
    suffix = Path(str(filename)).suffix.lower()
    if suffix and not re.fullmatch(r'\.[a-z0-9]+', suffix):
        raise ValueError('잘못된 확장자입니다.')
    root = (Path(engine_dir) / 'originals').resolve()
    candidate = root / (str(file_id) + suffix)
    if not candidate.resolve().is_relative_to(root):
        raise ValueError('원본 폴더 밖의 경로입니다.')
    return candidate


class BusyError(RuntimeError):
    pass


class SearchService:
    def __init__(self, engine_dir):
        self.engine_dir = Path(engine_dir).resolve()
        self.backend = self.engine_dir.parent
        self.lock = threading.RLock()
        self.job_lock = threading.Lock()
        self.jobs = {}
        self.active_job = None
        self.last_job = None
        source = self.engine_dir / 'search_engine.py'
        if not source.is_file():
            raise FileNotFoundError('검색 엔진이 없습니다. 처음 설치 실행 파일을 실행하세요.')
        subprocess.run([sys.executable, str(self.engine_dir / 'refresh_search.py'), '--build-index'], check=True)
        self.module = load_module(source, 'role01_search_engine')
        self.engine = self.module.SearchEngine()
        self.original_root = (self.engine_dir / 'dataset' / 'files').resolve()
        self._reload_catalog()
        self.watcher = None
        self.watch_stop = threading.Event()
        self.watch_thread = None
        self.watch_error = ''

    def _reload_catalog(self):
        with (self.engine_dir / 'metadata.csv').open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        def read_extra(name):
            path = self.backend / 'Role02' / name
            if not path.is_file():
                return {}
            with path.open(encoding='utf-8-sig', newline='') as stream:
                entries = list(csv.DictReader(stream))
            if len({row['file_id'] for row in entries}) != len(entries):
                raise ValueError(name + ': 중복 파일 ID')
            return {row['file_id']: row for row in entries}
        descriptions = read_extra('metadata_description_generated.csv')
        classifications = read_extra('metadata_classification_generated.csv')
        catalog, originals = {}, {}
        actual = {unicodedata.normalize('NFC', p.relative_to(self.original_root).as_posix()): p
                  for p in self.original_root.rglob('*') if p.is_file()}
        searchable = set(self.engine.df['file_id'].astype(str))
        for row in rows:
            file_id = str(row['file_id'])
            row = dict(row)
            description = descriptions.get(file_id, {}).get('description', '')
            if description.strip():
                row['description'] = description
            prediction = classifications.get(file_id, {})
            for field in ('project', 'role'):
                if not row.get(field, '').strip() and str(prediction.get(field + '_needs_confirmation', '')).lower() in ('false', '0', 'no'):
                    row[field] = prediction.get('predicted_' + field, '')
            item = self.file(row)
            item['classification'] = prediction
            item.update({key: prediction.get(key, '') for key in ('activity_at', 'time_source', 'year_month', 'quarter', 'half_year', 'season')})
            raw = str(row.get('path', '')).replace('\\', '/')
            relative = raw.split('dataset/files/', 1)[-1] if 'dataset/files/' in raw else ''
            path = actual.get(unicodedata.normalize('NFC', relative))
            if path and path.resolve().is_relative_to(self.original_root):
                originals[file_id] = path
            item['content_available'] = file_id in originals
            item['relations_available'] = True
            item['index_status'] = 'ready' if file_id in searchable else 'no_text'
            catalog[file_id] = item
        self.originals = originals
        self.catalog = catalog

    def list_files(self):
        if self.active_job:
            return list(self.catalog.values())
        with self.lock:
            self.engine.refresh()
            self._reload_catalog()
            return list(self.catalog.values())

    def content(self, file_id):
        path = self.originals.get(file_id)
        if path is None or not path.resolve().is_relative_to(self.original_root) or not path.is_file():
            raise FileNotFoundError('등록된 원본 파일이 없습니다.')
        return path

    def preview_pdf(self, file_id, page=1):
        import pymupdf
        path = self.content(file_id)
        if path.suffix.lower() != '.pdf':
            raise ValueError('PDF 파일만 페이지 미리보기를 지원합니다.')
        with pymupdf.open(path) as document:
            if not 1 <= page <= len(document):
                raise ValueError('존재하지 않는 페이지입니다.')
            source = document[page - 1]
            scale = min(1.5, 1600 / max(source.rect.width, source.rect.height, 1))
            pixmap = source.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            return {'page': page, 'page_count': len(document),
                    'image_base64': base64.b64encode(pixmap.tobytes('png')).decode('ascii')}

    @staticmethod
    def file(row):
        def date(value):
            for fmt in ('%Y.%m.%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
                try:
                    return datetime.strptime(str(value), fmt).isoformat()
                except ValueError:
                    pass
            return ''
        try:
            size = int(row.get('size_bytes', ''))
        except (ValueError, TypeError):
            size = None
        return {'file_id': str(row['file_id']), 'name': str(row['filename']),
                'path': str(row.get('path', '')).replace('\\', '/'),
                'role': str(row.get('role', '')), 'summary': str(row.get('description', '')),
                'project': str(row.get('project', '')),
                'size': size, 'created_at': date(row.get('created_at', '')),
                'modified_at': date(row.get('modified_at', '')),
                'index_status': 'ready', 'evidence': [],
                'content_available': False, 'relations_available': True}

    def search(self, query):
        if self.active_job:
            raise BusyError('데이터 갱신 중입니다. 내 파일의 진행 상태를 확인한 뒤 다시 검색하세요.')
        with self.lock:
            results = self.engine.search_files(query, top_k=5)
            self._reload_catalog()
            files = [{**self.catalog[r['file_id']], 'score': r['score'], 'excerpt': r['chunk_text']} for r in results]
            relations, extra = [], {}
            labels = {'references': '파일 경로·파일명 참조', 'reference_candidate': '파일명 참조 후보',
                      'content_similar': '내용 유사 후보', 'semantic_related': '의미 유사 후보',
                      'same_context': '같은 맥락 후보'}
            for result in results:
                source = result['file_id']
                for relation in self.engine.get_related_files(source, top_n=3):
                    target = relation['target_file_id']
                    if target not in self.catalog:
                        continue
                    kind = relation['relation_type']
                    # Backend heuristic matches are candidates. Only resolved DB
                    # references below are presented as confirmed static references.
                    relations.append({'source_file_id': source, 'target_file_id': target,
                                      'label': labels.get(kind, kind), 'certainty': 'inferred',
                                      'evidence': relation.get('evidence', '')})
                    extra[target] = self.catalog[target]
            recommendations = self.engine_dir / 'file_relations_v5.csv'
            if recommendations.is_file():
                selected = {r['file_id'] for r in results}
                recommended_links = []
                with recommendations.open(encoding='utf-8-sig', newline='') as stream:
                    for row in csv.DictReader(stream):
                        source, target = row['source_file_id'], row['target_file_id']
                        if source not in selected or target not in self.catalog:
                            continue
                        recommended_links.append({
                            'source_file_id': source, 'target_file_id': target,
                            'label': '복합 맥락 추천', 'certainty': 'inferred',
                            'evidence': row.get('evidence', '')})
                        extra[target] = self.catalog[target]
                relations = recommended_links + relations
            db = self.backend / 'Role03' / 'output' / 'files.sqlite3'
            if db.is_file():
                import sqlite3
                with closing(sqlite3.connect(db)) as connection:
                    connection.row_factory = sqlite3.Row
                    for result in results:
                        for row in connection.execute('SELECT * FROM relations WHERE source_id=? OR target_id=?',
                                                      (result['file_id'], result['file_id'])):
                            if row['status'] != 'resolved' or row['target_id'] not in self.catalog or row['source_id'] not in self.catalog:
                                continue
                            labels_db = {'reads': '코드의 읽기 참조', 'writes': '코드의 저장 경로 참조', 'mentions': '문서의 명시적 참조'}
                            link = {'source_file_id': row['source_id'], 'target_file_id': row['target_id'],
                                    'label': labels_db.get(row['relation_type'], row['relation_type']),
                                    'certainty': 'confirmed', 'evidence': row['evidence']}
                            if link not in relations:
                                relations.append(link)
                            extra[row['source_id']] = self.catalog[row['source_id']]
                            extra[row['target_id']] = self.catalog[row['target_id']]
            merged = {}
            for link in relations:
                key = (link['source_file_id'], link['target_file_id'])
                if key not in merged or link['certainty'] == 'confirmed':
                    merged[key] = link
            return {'files': files, 'catalog': list(extra.values()), 'relations': list(merged.values())}

    def job(self, job_id):
        with self.job_lock:
            if job_id not in self.jobs:
                raise FileNotFoundError('작업을 찾을 수 없습니다. 서버 재시작 후에는 내 파일을 새로고침하세요.')
            return dict(self.jobs[job_id])

    def _set_job(self, job_id, **values):
        with self.job_lock:
            self.jobs[job_id].update(values)

    def start_refresh(self, upload=None):
        if self.active_job:
            raise BusyError('다른 파일 등록·갱신 작업이 진행 중입니다.')
        with self.job_lock:
            if self.active_job:
                raise BusyError('다른 파일 등록·갱신 작업이 진행 중입니다.')
            job_id = uuid.uuid4().hex
            self.active_job = job_id
            self.last_job = job_id
            self.jobs[job_id] = {'status': 'processing', 'phase': '파일·DB·검색 인덱스 갱신 준비'}
            # Bound process memory while keeping recent job results available.
            for old in list(self.jobs)[:-100]:
                del self.jobs[old]
        threading.Thread(target=self._run_refresh, args=(job_id, upload), daemon=True).start()
        return job_id

    def add(self, name, content, relative_path='', modified_at=None):
        name = unicodedata.normalize('NFC', name)
        relative = unicodedata.normalize('NFC', relative_path or name).replace('\\', '/')
        parts = relative.split('/')
        if (not content or len(content) > MAX_UPLOAD or Path(name).suffix.lower() not in UPLOAD_EXTENSIONS
                or any(part in ('', '.', '..') or ':' in part or any(ord(c) < 32 for c in part) for part in parts)
                or '/' in name or '\\' in name or parts[-1] != name or len(relative) > 400):
            raise ValueError('지원 형식·25MB 제한·파일명과 상대 경로를 확인하세요. 이미지는 현재 검색 등록을 지원하지 않습니다.')
        stamp = None
        if modified_at is not None:
            import math
            stamp = float(modified_at) / 1000
            if not math.isfinite(stamp) or not 0 < stamp <= datetime.now().timestamp() + 86400:
                raise ValueError('올바른 파일 수정 시각이 필요합니다.')
        if self.active_job:
            raise BusyError('다른 파일 등록·갱신이 진행 중입니다.')
        with self.lock:
            if self.active_job:
                raise BusyError('다른 파일 등록·갱신이 진행 중입니다.')
            digest = hashlib.sha256(content).hexdigest()
            path = self.original_root / 'uploads' / digest[:16] / relative
            if not path.resolve().is_relative_to(self.original_root):
                raise ValueError('허용 폴더 밖의 경로입니다.')
            for file_id, original in self.originals.items():
                if path.is_file() and original.is_file() and original.samefile(path) and path.read_bytes() == content:
                    return {'file': self.catalog[file_id], 'duplicate': True}
            if path.exists() and path.read_bytes() != content:
                raise ValueError('같은 위치에 다른 파일이 있습니다.')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            if stamp is not None:
                os.utime(path, (stamp, stamp))
            next_number = max([int(x[1:]) for x in self.catalog if re.fullmatch(r'F\d+', x)] or [0]) + 1
            state = self.engine_dir / '.file_id_state.json'
            if state.is_file():
                next_number = max(next_number, int(json.loads(state.read_text())['next_file_number']))
            file_id = 'F%03d' % next_number
            if getattr(self, 'watcher', None):
                # Upload is already queued below; avoid a second watcher refresh.
                self.watcher.observed = self.watch_module.scan(self.original_root)
            row = {'file_id': file_id, 'filename': name, 'extension': path.suffix.lower(),
                   'path': path.relative_to(self.engine_dir).as_posix(), 'size_bytes': str(len(content)),
                   'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   'modified_at': datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                   'project': '', 'role': '', 'description': ''}
            job_id = self.start_refresh(upload=row)
            return {'file': {**self.file(row), 'index_status': 'processing'}, 'job_id': job_id, 'duplicate': False}

    def _run_refresh(self, job_id, upload):
        log_dir = self.backend.parent / 'logs'
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f'update-{job_id}.log'
        try:
            observed = self.watcher.observed.copy() if getattr(self, 'watcher', None) else None
            with self.lock, tempfile.TemporaryDirectory(prefix='gui-update-', dir=self.backend.parent) as temporary:
                stage = Path(temporary)
                for role in ('Role01', 'Role02', 'Role03'):
                    folder = stage / role
                    folder.mkdir()
                    for source in (self.backend / role).glob('*.py'):
                        shutil.copy2(source, folder / source.name)
                two = stage / 'Role02'
                for source in (self.backend / 'Role02').iterdir():
                    if source.suffix in ('.csv', '.json'):
                        shutil.copy2(source, two / source.name)
                    elif source.is_dir() and source.name.endswith(('artifacts', 'artifacts_v3')):
                        (two / source.name).symlink_to(source, target_is_directory=True)
                one = stage / 'Role01'
                for name in ('metadata.csv', 'extracted_text.csv', 'file_relations.csv', '.extraction_cache.json'):
                    shutil.copy2(self.engine_dir / name, one / name)
                state = self.engine_dir / '.file_id_state.json'
                if state.is_file():
                    shutil.copy2(state, one / state.name)
                (one / 'dataset').symlink_to(self.engine_dir / 'dataset', target_is_directory=True)
                (one / 'embedding_cache').symlink_to(self.engine_dir / 'embedding_cache', target_is_directory=True)
                shutil.copy2(self.backend / 'update_data.py', stage / 'update_data.py')
                old_audit = self.backend / 'Role03' / 'output' / 'audit.csv'
                if old_audit.is_file():
                    (stage / 'Role03' / 'output').mkdir()
                    shutil.copy2(old_audit, stage / 'Role03' / 'output' / 'audit.csv')
                with (one / 'extracted_text.csv').open(encoding='utf-8-sig', newline='') as stream:
                    prior_texts = {r['file_id']: r.get('extracted_text', '') for r in csv.DictReader(stream)}
                if upload:
                    with (one / 'metadata.csv').open(encoding='utf-8-sig', newline='') as stream:
                        reader = csv.DictReader(stream)
                        columns, rows = reader.fieldnames, list(reader)
                    with (one / 'metadata.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                        writer = csv.DictWriter(stream, fieldnames=columns)
                        writer.writeheader()
                        writer.writerows(rows + [upload])
                with log_path.open('w', encoding='utf-8') as log:
                    for script, phase in ((Path(__file__).with_name('refresh_workspace.py'), '본문 추출·DB·검색 임베딩 갱신'),
                                          (one / 'file_relations_v2.py', '관련 파일 관계 갱신')):
                        self._set_job(job_id, phase=phase)
                        command = [sys.executable, '-u', str(script)]
                        if script.name == 'refresh_workspace.py':
                            command += ['--root', str(stage)]
                        subprocess.run(command, cwd=stage, stdout=log, stderr=subprocess.STDOUT, check=True)
                # Latest Role02 classifiers consume the staged texts. Qwen is
                # optional locally; retain supplied descriptions when unavailable.
                with (one / 'extracted_text.csv').open(encoding='utf-8-sig', newline='') as stream:
                    current_texts = {r['file_id']: r.get('extracted_text', '') for r in csv.DictReader(stream)}
                changed = {fid for fid, text in current_texts.items() if prior_texts.get(fid) != text}
                # The team's classifier preserves prior predictions by ID. Drop
                # changed/deleted entries so edits get a fresh prediction.
                for name in ('metadata_description_generated.csv', 'metadata_classification_generated.csv'):
                    table = two / name
                    with table.open(encoding='utf-8-sig', newline='') as stream:
                        reader = csv.DictReader(stream)
                        columns, entries = reader.fieldnames, list(reader)
                    with table.open('w', encoding='utf-8-sig', newline='') as stream:
                        writer = csv.DictWriter(stream, fieldnames=columns)
                        writer.writeheader()
                        writer.writerows(r for r in entries if r['file_id'] in current_texts and r['file_id'] not in changed)
                warnings = []
                with log_path.open('a', encoding='utf-8') as log:
                    from urllib.request import urlopen
                    try:
                        with urlopen('http://127.0.0.1:11434/api/tags', timeout=2) as response:
                            models = json.load(response).get('models', [])
                        qwen = any(item.get('name') == 'qwen3.5:4b' for item in models)
                    except (OSError, ValueError):
                        qwen = False
                    if qwen:
                        self._set_job(job_id, phase='Qwen 파일 설명 생성')
                        subprocess.run([sys.executable, str(two / 'description_generator.py')], stdout=log, stderr=subprocess.STDOUT, check=True)
                    else:
                        warnings.append('Qwen3.5:4b가 실행되지 않아 새 AI 설명은 생성하지 않았습니다. 기존 설명과 본문 검색을 사용합니다.')
                    self._set_job(job_id, phase='프로젝트·역할·시간 분류')
                    subprocess.run([sys.executable, str(two / 'classify_metadata.py')], stdout=log, stderr=subprocess.STDOUT, check=True)
                    self._set_job(job_id, phase='설명 반영 검색 인덱스 갱신')
                    subprocess.run([sys.executable, str(one / 'refresh_search.py'), '--build-index'], stdout=log, stderr=subprocess.STDOUT, check=True)
                recommendations = one / 'file_relations_v5.py'
                if recommendations.is_file():
                    self._set_job(job_id, phase='복합 맥락 추천 갱신')
                    with log_path.open('a', encoding='utf-8') as log:
                        subprocess.run([sys.executable, str(recommendations)], cwd=stage,
                                       stdout=log, stderr=subprocess.STDOUT, check=True)
                self._set_job(job_id, phase='새 검색 데이터 검증')
                candidate_module = load_module(one / 'search_engine.py', 'candidate_' + job_id)
                candidate = candidate_module.SearchEngine()
                updater = load_module(self.backend / 'update_data.py', 'gui_updater_' + job_id)
                updater.ARTIFACTS = updater.ARTIFACTS + ['Role01/file_relations.csv', 'Role01/.extraction_cache.json', 'Role02/metadata_description_generated.csv', 'Role02/metadata_classification_generated.csv', 'Role02/description_hashes.json']
                if (one / 'file_relations_v5.csv').is_file():
                    updater.ARTIFACTS += ['Role01/file_relations_v5.csv']
                # DB/audit paths must survive deletion of the staging directory.
                import sqlite3
                staged_root = str(one / 'dataset' / 'files')
                with closing(sqlite3.connect(stage / 'Role03' / 'output' / 'files.sqlite3')) as connection:
                    connection.execute('UPDATE files SET local_path=REPLACE(local_path,?,?)', (staged_root, str(self.original_root)))
                    connection.commit()
                audit_path = stage / 'Role03' / 'output' / 'audit.csv'
                with audit_path.open(encoding='utf-8-sig', newline='') as stream:
                    reader = csv.DictReader(stream)
                    columns, audits = reader.fieldnames, list(reader)
                for row in audits:
                    row['local_path'] = row['local_path'].replace(staged_root, str(self.original_root))
                with audit_path.open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=columns)
                    writer.writeheader(); writer.writerows(audits)
                self._set_job(job_id, phase='새 검색 데이터 적용')
                updater.publish(self.backend, stage)
                self.module = load_module(self.engine_dir / 'search_engine.py', 'live_' + job_id)
                self.engine = self.module.SearchEngine()
                self._reload_catalog()
                if observed is not None:
                    state = self.backend / '.auto-refresh' / 'indexed.json'
                    state.parent.mkdir(exist_ok=True)
                    state.write_text(json.dumps(observed), encoding='utf-8')
                if upload and self.catalog[upload['file_id']]['index_status'] != 'ready':
                    self._set_job(job_id, status='failed', phase='파일은 등록되었지만 검색할 본문이 없습니다.',
                                  error='파일은 내 파일에서 열 수 있습니다. 텍스트가 있는 파일로 다시 등록하세요.')
                else:
                    self._set_job(job_id, status='ready', phase='검색·원본·관련 파일 갱신 완료', warnings=warnings)
        except Exception as error:
            try:
                if upload and self.catalog.get(upload['file_id'], {}).get('path') != upload['path']:
                    failed_source = self.engine_dir / upload['path']
                    if failed_source.is_file() and failed_source.resolve().is_relative_to(self.original_root):
                        failed_target = self.backend / 'failed_uploads' / job_id / upload['filename']
                        failed_target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(failed_source), failed_target)
            except OSError as recovery_error:
                print(f'실패 파일 보관 위치를 확인하세요: {recovery_error}', file=sys.stderr, flush=True)
            self._set_job(job_id, status='failed', phase='갱신 실패', error=f'{error} · 로그: {log_path}')
            print(f'데이터 갱신 실패: {error} · {log_path}', file=sys.stderr, flush=True)
        finally:
            with self.job_lock:
                self.active_job = None

    def start_watching(self):
        if self.watch_thread:
            return
        module = load_module(self.backend / 'auto_refresh.py', 'gui_auto_refresh')
        self.watch_module = module
        self.watcher = module.AutoRefresh(root=self.backend)
        def watch():
            while not self.watch_stop.wait(2):
                try:
                    # Coordinate corpus copying and upload staging with refresh.
                    with self.lock:
                        if self.active_job:
                            continue
                        self.watcher.poll_once()
                        with self.watcher.condition:
                            if self.watcher.pending:
                                import time
                                if time.monotonic() >= self.watcher.deadline:
                                    self.start_refresh()
                                    # Job history belongs to SearchService; the
                                    # team watcher only supplies debounced events.
                                    self.watcher.jobs.pop(self.watcher.pending, None)
                                    self.watcher.pending = None
                                    self.watcher.last_job = None
                        self.watch_error = ''
                except Exception as error:
                    self.watch_error = str(error)
        self.watch_thread = threading.Thread(target=watch, name='gui-folder-watch', daemon=True)
        self.watch_thread.start()

    def watch_status(self):
        status = self.watcher.status() if self.watcher else {'watching': False, 'folders': []}
        return {'watching': status['watching'], 'folders': status['folders'], 'error': self.watch_error}

    def close(self):
        self.watch_stop.set()
        if self.watch_thread:
            self.watch_thread.join()
