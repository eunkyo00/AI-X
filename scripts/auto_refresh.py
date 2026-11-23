"""Local file registration and debounced refresh; source folders stay read-only."""
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import threading
import time
import uuid

from update_data import ROOT, SourceChanged, UpdateInProgress, update

SUPPORTED = {'.pdf', '.csv', '.tsv', '.xlsx', '.docx', '.pptx', '.txt', '.md',
             '.py', '.r', '.ipynb', '.json', '.html', '.css', '.js', '.sql'}
EXCLUDED = {'.DS_Store', '.Rhistory', 'LICENSE', 'SOURCE.json', 'node_modules', '__pycache__'}
MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_BATCH_SIZE = 100 * 1024 * 1024


def admitted(path):
    return (path.suffix.lower() in SUPPORTED
            and not any(part.startswith(('.', '~$')) or part in EXCLUDED for part in path.parts))


def scan(folder):
    """Only stat registered source data, never generated DB/index/config files."""
    result = {}
    for directory, names, files in os.walk(folder, followlinks=False, onerror=lambda error: (_ for _ in ()).throw(error)):
        names[:] = [name for name in names if not name.startswith('.') and name not in EXCLUDED
                    and not (Path(directory)/name).is_symlink()]
        for name in files:
            path = Path(directory)/name
            relative = path.relative_to(folder)
            if admitted(relative) and not path.is_symlink():
                stat = path.stat()
                result[relative.as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return result


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


class AutoRefresh:
    def __init__(self, root=ROOT, updater=update, interval=1.0, debounce=2.0):
        self.root = Path(root).resolve()
        self.corpus = self.root/'Role01/dataset/files'
        self.corpus.mkdir(parents=True, exist_ok=True)
        self.state_dir = self.root/'.auto-refresh'
        self.updater, self.interval, self.debounce = updater, interval, debounce
        self.condition = threading.Condition(threading.RLock())
        self.stopped = False
        self.threads = []
        self.jobs, self.pending, self.active = {}, None, None
        self.deadline = 0
        self.revision = 0
        self.last_job = None
        config = self.state_dir/'folders.json'
        self.folders = json.loads(config.read_text()) if config.exists() else []
        # Never trust persisted destinations; each is derived from its generated ID.
        for item in self.folders:
            if not isinstance(item.get('id'), str) or not item['id'].isalnum():
                raise ValueError('감시 폴더 설정이 올바르지 않습니다.')
        self.folder_errors = {}
        self.observed = scan(self.corpus)
        saved = self.state_dir/'indexed.json'
        if saved.exists():
            baseline = {key: tuple(value) for key, value in json.loads(saved.read_text()).items()}
            dirty = baseline != self.observed
        else:
            dirty = not self._matches_metadata(self.observed)
        if dirty:
            with self.condition:
                self._request_locked('앱을 끈 동안 변경된 파일 확인')

    def _matches_metadata(self, current):
        path = self.root/'Role01/metadata.csv'
        if not path.exists():
            return not current
        expected = {}
        with path.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                value = row['path'].replace('\\', '/')
                if 'dataset/files/' not in value:
                    return False
                relative = value.split('dataset/files/', 1)[1]
                if admitted(Path(relative)):
                    expected[relative] = (int(row['size_bytes']), row['modified_at'])
        from datetime import datetime
        actual = {key: (value[0], datetime.fromtimestamp(value[1]/1e9).strftime('%Y-%m-%d %H:%M:%S'))
                  for key, value in current.items()}
        return actual == expected

    def start(self):
        with self.condition:
            if self.threads:
                return self
            self.threads = [threading.Thread(target=self._watch, name='file-watch', daemon=True),
                            threading.Thread(target=self._work, name='file-refresh', daemon=False)]
            for thread in self.threads:
                thread.start()
        return self

    def close(self):
        with self.condition:
            self.stopped = True
            self.condition.notify_all()
        for thread in self.threads:
            thread.join()

    def _request_locked(self, reason):
        self.revision += 1
        if self.pending is None:
            self.pending = uuid.uuid4().hex
            self.jobs[self.pending] = {'job_id': self.pending, 'status': 'queued', 'phase': reason}
        job = self.jobs[self.pending]
        job['revision'] = self.revision
        self.last_job = self.pending
        self.deadline = time.monotonic() + self.debounce
        self.condition.notify_all()
        # Retain active jobs and the last 100 completed results.
        completed = [key for key, value in self.jobs.items() if value['status'] in {'ready', 'failed'}]
        for key in completed[:-100]:
            del self.jobs[key]
        return dict(job)

    def request(self, reason='등록 파일 분석 대기'):
        with self.condition:
            if self.stopped:
                raise RuntimeError('서버가 종료 중입니다.')
            return self._request_locked(reason)

    def job(self, job_id):
        with self.condition:
            if job_id not in self.jobs:
                raise KeyError('갱신 작업을 찾을 수 없습니다.')
            item = self.jobs[job_id]
            if item.get('follow_job'):
                return dict(self.job(item['follow_job']), job_id=job_id)
            return dict(item)

    def status(self):
        with self.condition:
            key = self.active or self.pending or self.last_job
            return {'job': dict(self.jobs[key]) if key else None,
                    'watching': not self.stopped,
                    'folders': [dict(item, error=self.folder_errors.get(item['id'])) for item in self.folders]}

    def register_files(self, files):
        """Validate the entire batch before touching the corpus. Paths are browser-relative."""
        if not files or len(files) > 500 or sum(len(data) for _, data in files) > MAX_BATCH_SIZE:
            raise ValueError('한 번에 최대 500개, 총 100MB까지 등록할 수 있습니다.')
        checked, seen = [], set()
        for name, data in files:
            normalized = str(name).replace('\\', '/')
            relative = PurePosixPath(normalized)
            if (not normalized or '\x00' in normalized or relative.is_absolute()
                    or ':' in normalized or any(part in {'', '.', '..'} for part in normalized.split('/'))
                    or not admitted(Path(normalized))):
                raise ValueError(f'지원하지 않는 파일 경로 또는 형식입니다: {name}')
            if len(data) > MAX_FILE_SIZE:
                raise ValueError('파일당 25MB까지 등록할 수 있습니다.')
            target = self.corpus/'uploads'/relative
            if not target.resolve().is_relative_to(self.corpus.resolve()):
                raise ValueError('등록 폴더 밖에는 저장할 수 없습니다.')
            if relative.as_posix() in seen:
                raise ValueError('같은 경로의 파일을 한 번에 중복 등록할 수 없습니다.')
            seen.add(relative.as_posix())
            checked.append((target, data))
        with self.condition:
            if self.stopped:
                raise RuntimeError('서버가 종료 중입니다.')
            for target, data in checked:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.upload-', delete=False) as stream:
                    temporary = Path(stream.name)
                    try:
                        stream.write(data)
                        stream.flush()
                        os.replace(temporary, target)
                    finally:
                        temporary.unlink(missing_ok=True)
            self.observed = scan(self.corpus)
            job = self._request_locked('등록 완료 · 검색 데이터 갱신 대기')
            current = self.jobs[job['job_id']]
            current['paths'] = sorted(set(current.get('paths', [])) | {target.relative_to(self.corpus).as_posix() for target, _ in checked})
            return dict(current)

    def add_folder(self, value):
        raw = Path(value).expanduser()
        if not raw.is_absolute():
            raise ValueError('원본 폴더의 전체 경로를 입력하세요.')
        source = raw.resolve(strict=True)
        if not source.is_dir():
            raise ValueError('폴더 경로를 선택하세요.')
        # A project ancestor/descendant would import generated files into itself.
        if source.is_relative_to(self.root) or self.root.is_relative_to(source):
            raise ValueError('프로그램 폴더와 겹치지 않는 자료 폴더를 선택하세요.')
        with self.condition:
            for item in self.folders:
                if Path(item['path']) == source:
                    return dict(item)
            if len(self.folders) >= 20:
                raise ValueError('감시 폴더는 최대 20개까지 등록할 수 있습니다.')
            folder_id = hashlib.sha256(os.fsencode(os.path.normcase(str(source)))).hexdigest()[:32]
            item = {'id': folder_id, 'path': str(source), 'name': source.name}
            self.folders.append(item)
            try:
                atomic_json(self.state_dir/'folders.json', self.folders)
            except Exception:
                self.folders.remove(item)
                raise
            self.condition.notify_all()
            return dict(item)

    def remove_folder(self, folder_id):
        with self.condition:
            new = [item for item in self.folders if item['id'] != folder_id]
            if len(new) == len(self.folders):
                raise KeyError('감시 폴더를 찾을 수 없습니다.')
            atomic_json(self.state_dir/'folders.json', new)
            self.folders = new
            self.folder_errors.pop(folder_id, None)

    def poll_once(self):
        with self.condition:
            for item in self.folders:
                try:
                    self._sync_folder(item)
                    self.folder_errors.pop(item['id'], None)
                except (OSError, ValueError) as error:
                    self.folder_errors[item['id']] = str(error)
            current = scan(self.corpus)
            if current != self.observed:
                self.observed = current
                self._request_locked('파일 추가·수정·삭제 감지')

    def _sync_folder(self, item):
        source = Path(item['path'])
        if not source.is_dir():
            raise ValueError('원본 폴더에 접근할 수 없습니다. 기존 보관본을 유지합니다.')
        snapshot = scan(source)
        target = self.corpus/'watched'/item['id']
        if target.is_symlink() or not target.resolve().is_relative_to(self.corpus.resolve()):
            raise ValueError('감시 자료 저장 경로가 올바르지 않습니다.')
        target.mkdir(parents=True, exist_ok=True)
        previous = scan(target)
        for relative, fingerprint in snapshot.items():
            if previous.get(relative) == fingerprint:
                continue
            origin, destination = source/relative, target/relative
            if not destination.resolve().is_relative_to(target.resolve()):
                raise ValueError('감시 자료 저장 경로 밖의 파일입니다.')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.sync-', delete=False) as stream:
                temporary = Path(stream.name)
            try:
                shutil.copy2(origin, temporary)
                stat = origin.stat()
                if (stat.st_size, stat.st_mtime_ns) != fingerprint:
                    continue  # Still being saved; retry on the next poll.
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        for relative in previous.keys() - snapshot.keys():
            (target/relative).unlink()

    def _file_results(self, paths):
        table = self.root/'Role01/extracted_text.csv'
        rows = {}
        if table.exists():
            with table.open(encoding='utf-8-sig', newline='') as stream:
                for row in csv.DictReader(stream):
                    path = row.get('path', '').replace('\\', '/')
                    if 'dataset/files/' in path:
                        rows[path.split('dataset/files/', 1)[1]] = row
        return [dict(path=path, file_id=rows.get(path, {}).get('file_id'),
                     extraction_status=rows.get(path, {}).get('extraction_status', 'missing')) for path in paths]

    def _watch(self):
        while True:
            with self.condition:
                if self.stopped:
                    return
            try:
                self.poll_once()
            except OSError:
                pass  # Never interpret an unreadable source as an empty folder.
            with self.condition:
                self.condition.wait(self.interval)

    def _work(self):
        while True:
            with self.condition:
                while True:
                    if self.stopped:
                        return
                    wait = self.deadline-time.monotonic()
                    if self.pending and wait <= 0:
                        break
                    self.condition.wait(max(wait, .01) if self.pending else None)
                job_id, self.pending = self.pending, None
                self.active = job_id
                self.jobs[job_id].update(status='running', phase='파일 분석 준비')
                try:
                    before = scan(self.corpus)
                except OSError as error:
                    self.jobs[job_id].update(status='failed', phase='원본 파일 확인 실패', error=str(error))
                    self.active = None
                    continue
            def progress(phase):
                with self.condition:
                    self.jobs[job_id]['phase'] = phase
            try:
                self.updater(self.root, progress=progress, snapshot=True)
                with self.condition:
                    atomic_json(self.state_dir/'indexed.json', before)
                    self.jobs[job_id].update(status='ready', phase='갱신 완료',
                                             files=self._file_results(self.jobs[job_id].get('paths', [])))
            except (UpdateInProgress, SourceChanged) as error:
                with self.condition:
                    self.jobs[job_id].update(status='queued', phase='파일 저장 완료 대기' if isinstance(error, SourceChanged) else '다른 갱신 작업 완료 대기')
                    if self.pending:
                        self.jobs[job_id]['follow_job'] = self.pending
                        pending = self.jobs[self.pending]
                        pending['paths'] = sorted(set(pending.get('paths', [])) | set(self.jobs[job_id].get('paths', [])))
                    else:
                        self.pending = job_id
                    self.deadline = time.monotonic()+max(self.debounce, 1)
            except Exception as error:
                with self.condition:
                    self.jobs[job_id].update(status='failed', phase='갱신 실패', error=str(error))
            finally:
                with self.condition:
                    self.active = None
                    self.condition.notify_all()
