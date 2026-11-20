"""Open an existing GUI or start it on an available localhost port."""
import json
import os
from pathlib import Path
import socket
import sys
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[2]


def main():
    from importlib.util import find_spec
    required = ('sentence_transformers', 'pandas', 'numpy', 'pymupdf', 'openpyxl', 'docx', 'pptx', 'PIL', 'requests', 'joblib', 'sklearn')
    missing = [name for name in required if find_spec(name) is None]
    if missing:
        raise SystemExit('필요한 패키지가 없습니다: ' + ', '.join(missing) + '\nGUI 실행 폴더의 처음 설치 파일을 한 번 실행하세요.')
    available = None
    for port in range(5173, 5194):
        try:
            with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=0.3) as response:
                health = json.load(response)
            if health.get('app_id') == 'context-search-gui-v2' and health.get('workspace') == str(ROOT):
                webbrowser.open(f'http://127.0.0.1:{port}')
                print('이미 실행 중인 Context Search를 열었습니다.')
                return
        except (OSError, ValueError):
            pass
        if available is None:
            try:
                with socket.socket() as probe:
                    probe.bind(('127.0.0.1', port))
                available = port
            except OSError:
                pass
    if available is None:
        raise SystemExit('5173~5193 포트를 사용할 수 없습니다. 이전 서버 터미널을 종료하고 다시 실행하세요.')
    from serve_web import main as serve
    cache = ROOT / 'Role04' / 'runtime' / 'hf-cache' / 'hub' / 'models--intfloat--multilingual-e5-small'
    if (cache / 'refs' / 'main').is_file():
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
    sys.argv = [sys.argv[0], '--port', str(available), '--open-browser']
    serve()


if __name__ == '__main__':
    main()
