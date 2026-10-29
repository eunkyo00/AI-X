"""Serve the existing GUI and the Role01 semantic search API on localhost."""
import argparse
import json
import os
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    service = None

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
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.json_response(200, {'status': 'ok', 'contract_version': 'gui-v1',
                'index_ready': self.service is not None,
                'capabilities': {'reveal': False, 'upload': False, 'content': False}})
        if path == '/api/files':
            return self.json_response(200, {'files': list(self.service.catalog.values()) if self.service else []})
        if path.startswith('/api/'):
            return self.json_response(404, {'error': '이 서버는 검색과 파일 목록을 제공합니다. 원본 파일 열기는 아직 연결되지 않았습니다.'})
        if path == '/runtime-config.js':
            body = ('window.CONTEXT_SEARCH_CONFIG = ' + json.dumps(
                {'mode': 'api', 'base': '/api', 'searchOnly': True} if self.service else {}) + ';').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return self.wfile.write(body)
        return super().do_GET()

    def do_POST(self):
        # GUI and API use one origin; reject cross-site browser mutations.
        origin = self.headers.get('Origin')
        if origin and origin != f'http://127.0.0.1:{self.server.server_port}':
            return self.json_response(403, {'error': '허용되지 않은 요청 출처입니다.'})
        if urlsplit(self.path).path != '/api/search':
            return self.json_response(501, {'error': '파일 등록·재인덱싱은 아직 지원하지 않습니다.'})
        if not self.service:
            return self.json_response(503, {'error': '검색 엔진을 사용하지 않는 화면 확인 모드입니다.'})
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
        except Exception:
            self.log_error('검색 처리 실패')
            return self.json_response(500, {'error': '검색 처리 중 오류가 발생했습니다. 서버 로그를 확인하세요.'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5173)
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--demo', action='store_true', help='모델 없이 화면만 확인')
    parser.add_argument('--engine-dir', type=Path, default=ROOT / 'runtime' / 'search')
    args = parser.parse_args()
    if not args.demo:
        os.environ.setdefault('HF_HOME', str(ROOT / 'runtime' / 'hf-cache'))
        from search_api import SearchService
        print('검색 엔진 준비 중입니다. 첫 실행은 모델 다운로드가 필요합니다.', flush=True)
        Handler.service = SearchService(args.engine_dir)
    handler = partial(Handler, directory=str(ROOT / 'web'))
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'Context Search: http://127.0.0.1:{args.port}', flush=True)
        if args.open_browser:
            threading.Timer(0.5, lambda: webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
