"""Serve the existing GUI and the Role01 semantic search API on localhost."""
import argparse
import atexit
import json
import os
import mimetypes
import shutil
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote, parse_qs
from email.parser import BytesParser
from email.policy import default as email_policy
from search_api import BusyError, MAX_UPLOAD

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    service = None
    # Windows registry MIME associations must not prevent ES module loading.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        '.js': 'text/javascript; charset=utf-8',
        '.mjs': 'text/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
    }

    def valid_host(self):
        if self.headers.get('Host') not in {f'{host}:{self.server.server_port}' for host in ('127.0.0.1', 'localhost')}:
            self.json_response(403, {'error': '로컬 GUI 주소로 접속하세요.'})
            return False
        return True

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def json_response(self, status, body):
        content = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if not self.valid_host():
            return
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.json_response(200, {'status': 'ok', 'contract_version': 'gui-v1',
                'app_id': 'context-search-gui-v2', 'workspace': str(ROOT.parent),
                'index_ready': self.service is not None and not getattr(self.service, 'active_job', None),
                'active_job': getattr(self.service, 'active_job', None),
                'last_job': getattr(self.service, 'last_job', None),
                'watch': self.service.watch_status() if hasattr(self.service, 'watch_status') else None,
                'capabilities': {'reveal': False, 'upload': hasattr(self.service, 'add'),
                                 'refresh': hasattr(self.service, 'start_refresh'), 'content': self.service is not None}})
        if path == '/api/folders' and self.service and getattr(self.service, 'watcher', None):
            return self.json_response(200, self.service.watch_status())
        if path == '/api/files':
            try:
                files = (self.service.list_files() if hasattr(self.service, 'list_files') else list(self.service.catalog.values())) if self.service else []
                return self.json_response(200, {'files': files})
            except Exception as error:
                return self.json_response(503, {'error': str(error)})
        if path.startswith('/api/jobs/') and self.service and hasattr(self.service, 'job'):
            try:
                return self.json_response(200, self.service.job(path[len('/api/jobs/'):]))
            except FileNotFoundError as error:
                return self.json_response(404, {'error': str(error)})
        if path.startswith('/api/files/') and path.endswith('/preview'):
            file_id = unquote(path[len('/api/files/'):-len('/preview')])
            if not self.service or file_id not in self.service.catalog:
                return self.json_response(404, {'error': '등록된 파일 ID를 찾을 수 없습니다.'})
            try:
                page = int(parse_qs(urlsplit(self.path).query).get('page', ['1'])[0])
                return self.json_response(200, self.service.preview_pdf(file_id, page))
            except FileNotFoundError:
                return self.json_response(404, {'error': '원본 PDF가 없습니다. 데이터 준비를 다시 실행하세요.'})
            except ValueError as error:
                return self.json_response(400, {'error': str(error)})
            except Exception:
                self.log_error('PDF 미리보기 실패')
                return self.json_response(500, {'error': 'PDF 페이지를 표시하지 못했습니다. 원본 다운로드를 이용하세요.'})
        if path.startswith('/api/files/') and path.endswith('/content'):

            file_id = unquote(path[len('/api/files/'):-len('/content')])
            if not self.service or file_id not in self.service.catalog:
                return self.json_response(404, {'error': '등록된 파일 ID를 찾을 수 없습니다.'})
            try:
                original = self.service.content(file_id)
                stream = original.open('rb')
            except (FileNotFoundError, ValueError):
                return self.json_response(404, {'error': '원본 파일이 없습니다. prepare_search.py를 다시 실행하세요.'})
            with stream:
                self.send_response(200)
                mime = mimetypes.guess_type(original.name)[0] or 'application/octet-stream'
                if original.suffix.lower() in ('.r', '.py', '.txt', '.md', '.csv', '.json', '.ipynb', '.tsv', '.html', '.css', '.js', '.sql'):
                    mime = 'text/plain; charset=utf-8'
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(os.fstat(stream.fileno()).st_size))
                self.send_header('Content-Disposition', 'attachment')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                shutil.copyfileobj(stream, self.wfile)
            return
        if path.startswith('/api/'):

            return self.json_response(404, {'error': '요청한 API 경로를 찾을 수 없습니다.'})
        if path == '/runtime-config.js':
            body = ('window.CONTEXT_SEARCH_CONFIG = ' + json.dumps(
                {'mode': 'api', 'base': '/api'} if self.service else {}) + ';').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return self.wfile.write(body)
        return super().do_GET()

    def do_POST(self):
        if not self.valid_host():
            return
        # GUI and API use one origin; reject cross-site browser mutations.
        origin = self.headers.get('Origin')
        allowed_origins = {f'http://{host}:{self.server.server_port}' for host in ('127.0.0.1', 'localhost')}
        if (origin and origin not in allowed_origins) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return self.json_response(403, {'error': '허용되지 않은 요청 출처입니다.'})
        path = urlsplit(self.path).path
        if path not in ('/api/search', '/api/files', '/api/refresh', '/api/folders', '/api/folders/remove'):
            return self.json_response(404, {'error': '요청한 API 경로를 찾을 수 없습니다.'})
        if not self.service:
            return self.json_response(503, {'error': '검색 엔진을 사용하지 않는 화면 확인 모드입니다.'})
        if path in ('/api/folders', '/api/folders/remove'):
            try:
                if not getattr(self.service, 'watcher', None):
                    return self.json_response(501, {'error': '자동 감시를 지원하지 않습니다.'})
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('요청 크기를 확인하세요.')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('JSON 객체가 필요합니다.')
                if path.endswith('/remove'):
                    self.service.watcher.remove_folder(body.get('id', ''))
                else:
                    if not isinstance(body.get('path'), str) or not body['path'].strip():
                        raise ValueError('원본 폴더의 전체 경로가 필요합니다.')
                    self.service.watcher.add_folder(body['path'])
                return self.json_response(200, self.service.watch_status())
            except (ValueError, OSError, KeyError) as error:
                return self.json_response(400, {'error': str(error)})
        if path == '/api/files':
            if not hasattr(self.service, 'add'):
                return self.json_response(501, {'error': '파일 등록을 지원하지 않는 서버입니다.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_UPLOAD + 65536 or self.headers.get_content_type() != 'multipart/form-data':
                    raise ValueError('multipart 파일 1개와 25MB 제한을 확인하세요.')
                message = BytesParser(policy=email_policy).parsebytes(
                    ('Content-Type: ' + self.headers['Content-Type'] + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + self.rfile.read(length))
                if not message.is_multipart():
                    raise ValueError('잘못된 파일 등록 요청입니다.')
                fields, uploads = {}, []
                for part in message.iter_parts():
                    key = part.get_param('name', header='content-disposition')
                    if key == 'file':
                        uploads.append((part.get_filename(), part.get_payload(decode=True)))
                    elif key in ('relative_path', 'modified_at'):
                        fields[key] = part.get_payload(decode=True).decode('utf-8')
                if len(uploads) != 1 or not uploads[0][0]:
                    raise ValueError('파일 1개가 필요합니다.')
                result = self.service.add(*uploads[0], relative_path=fields.get('relative_path', ''), modified_at=fields.get('modified_at'))
                return self.json_response(200, result)
            except BusyError as error:
                return self.json_response(409, {'error': str(error)})
            except (ValueError, UnicodeError, TypeError, OverflowError) as error:
                return self.json_response(400, {'error': str(error)})
            except Exception as error:
                self.log_error('파일 등록 실패: %s', error)
                return self.json_response(500, {'error': '파일 등록에 실패했습니다. 서버 로그를 확인하세요.'})
        if path == '/api/refresh':
            if not hasattr(self.service, 'start_refresh'):
                return self.json_response(501, {'error': '갱신을 지원하지 않는 서버입니다.'})
            try:
                return self.json_response(202, {'job_id': self.service.start_refresh()})
            except BusyError as error:
                return self.json_response(409, {'error': str(error)})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError('요청 크기가 올바르지 않습니다.')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('JSON 요청이 필요합니다.')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or not isinstance(body.get('query'), str):
                raise ValueError('query 문자열이 필요합니다.')
            query = body['query'].strip()
            if len(query) > 2000:
                raise ValueError('검색어는 2,000자까지 입력할 수 있습니다.')
        except (ValueError, UnicodeError) as error:
            return self.json_response(400, {'error': str(error)})
        try:
            return self.json_response(200, self.service.search(query))
        except ValueError as error:
            return self.json_response(400, {'error': str(error)})
        except BusyError as error:
            return self.json_response(409, {'error': str(error)})
        except RuntimeError as error:
            return self.json_response(503, {'error': str(error)})
        except Exception:
            self.log_error('검색 처리 실패')
            return self.json_response(500, {'error': '검색 처리 중 오류가 발생했습니다. 서버 로그를 확인하세요.'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5173)
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--demo', action='store_true', help='모델 없이 화면만 확인')
    parser.add_argument('--engine-dir', type=Path, default=ROOT / 'runtime' / 'backend' / 'Role01')
    args = parser.parse_args()
    if not args.demo:
        if args.engine_dir == ROOT / 'runtime' / 'backend' / 'Role01':
            from prepare_search import prepare
            prepare()
        lock_path = args.engine_dir.resolve().parent / '.gui-server.lock'
        if lock_path.is_file():
            try:
                process_id = int(lock_path.read_text())
                os.kill(process_id, 0)
            except ProcessLookupError:
                lock_path.unlink()
            except (ValueError, PermissionError):
                raise SystemExit('실행 잠금 파일을 확인하세요: ' + str(lock_path))
            else:
                raise SystemExit('이 데이터의 GUI가 이미 실행 중입니다. Context Search 실행 파일로 기존 화면을 여세요.')
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(str(os.getpid()))
        atexit.register(lambda: lock_path.unlink(missing_ok=True))
        os.environ.setdefault('HF_HOME', str(ROOT / 'runtime' / 'hf-cache'))
        from search_api import SearchService
        print('검색 엔진 준비 중입니다. 첫 실행은 모델 다운로드가 필요합니다.', flush=True)
        Handler.service = SearchService(args.engine_dir)
        Handler.service.start_watching()
        atexit.register(Handler.service.close)
    handler = partial(Handler, directory=str(ROOT / 'web'))
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'Context Search: http://127.0.0.1:{args.port}', flush=True)
        if args.open_browser:
            threading.Timer(0.5, lambda: webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            if Handler.service and hasattr(Handler.service, 'close'):
                Handler.service.close()
            if Handler.service and getattr(Handler.service, 'active_job', None):
                print('진행 중인 갱신을 마친 뒤 종료합니다. 잠시 기다려 주세요.', flush=True)
                job = Handler.service.active_job
                while Handler.service.job(job)['status'] == 'processing':
                    threading.Event().wait(0.2)


if __name__ == '__main__':
    main()
