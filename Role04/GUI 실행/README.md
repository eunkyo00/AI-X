# GUI 실행

팀원이 GUI를 실행할 때 사용하는 파일을 모은 폴더입니다. 전체 저장소를 받은 상태로 사용하세요. 이 폴더만 따로 복사하면 실행되지 않습니다.

## 처음 실행하는 경우

[설치·첫 실행 안내](../README.md)에 따라 Python 3.13, 검색 패키지, 검색 데이터를 먼저 준비합니다. 첫 모델 다운로드에는 인터넷이 필요합니다.

## 설치 후 실행

- **Mac:** `Context Search 실행.command` 더블클릭
- **Windows:** `Context Search 실행.cmd` 더블클릭

서버 준비가 끝나면 브라우저가 열립니다. 기본 주소는 http://127.0.0.1:5173 입니다. 실행하는 동안 터미널 창을 유지하고 종료는 Ctrl+C입니다.

포트가 사용 중이면 저장소 루트에서 다음과 같이 실행합니다.

```bash
# Mac
.venv/bin/python Role04/scripts/serve_web.py --port 5175 --open-browser
```

```powershell
# Windows
.\.venv\Scripts\python.exe Role04/scripts/serve_web.py --port 5175 --open-browser
```

GUI 소스는 `../web/`, 서버 코드는 `../scripts/`에 있습니다. 실행 파일은 현재 작업 폴더와 관계없이 이 위치를 기준으로 서버를 찾습니다.
