# GUI 실행

팀원이 GUI를 실행할 때 사용하는 파일을 모은 폴더입니다. 전체 저장소를 받은 상태로 사용하세요. 이 폴더만 따로 복사하면 실행되지 않습니다.

## 처음 실행하는 경우

[설치·첫 실행 안내](../README.md)에 따라 Python 3.13, 검색 패키지, 검색 데이터를 먼저 준비합니다. 첫 모델 다운로드에는 인터넷이 필요합니다.

## 기존 설치자가 원본 열기 기능을 업데이트하는 경우

실행 중인 서버를 Ctrl+C로 종료하고, 최신 main 코드를 받은 뒤 **저장소 루트**에서 아래 명령을 실행하세요. 기존 작업 폴더에 수정 중인 파일이 있으면 별도 폴더에 최신 main을 clone하는 방법을 권장합니다. 코드 받기는 [상위 README](../README.md)를 참고하세요.

Mac/Linux:

```bash
.venv/bin/python -m pip install -r Role04/requirements-search.txt
.venv/bin/python Role04/scripts/prepare_search.py
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r Role04/requirements-search.txt
.\.venv\Scripts\python.exe Role04/scripts/prepare_search.py
```

준비 스크립트가 Git 이력에서 검색 데이터와 원본 158개를 준비합니다. 설치가 끝나면 아래 실행 파일을 더블클릭하세요. 새 패키지 설치나 데이터 준비 없이 예전 서버만 실행하면 원본 열기가 제공되지 않을 수 있습니다.

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

## 원본 열기 확인 방법

1. **내 파일**의 파일명 검색에 `Cross-Validation_Decoded.pdf`를 입력합니다.
2. **열기**를 누르면 원본 PDF 페이지가 표시됩니다. **다음 페이지**로 이동할 수 있습니다.
3. **보관본 다운로드**를 누르면 원본 PDF를 저장할 수 있습니다.
4. `week14_apple_forecast_analysis_2026_1.R`을 찾아 열면 전체 코드를 읽기 전용으로 볼 수 있습니다. 코드는 실행하지 않습니다.

검색 결과에서 파일을 선택하고 **열기**를 눌러도 같습니다. PDF·코드 외에 미리보기를 지원하지 않는 형식은 다운로드 후 연결 앱에서 확인하세요.

현재 제공: 실제 의미 검색, 파일 정보·본문 발췌, 원본 열기·다운로드. 새 파일 AI 등록·재인덱싱·OS 폴더 열기·파일 간 관계는 아직 미지원입니다. Windows 명령은 제공하지만 실제 Windows 실행은 미검증입니다.
