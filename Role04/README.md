# Role04 · Context Search GUI

기존 웹 GUI에 최신 팀 검색 엔진의 의미·시간 검색, 파일 관계, 실제 원본 열기와 등록·갱신을 연결했습니다.

## 실행

**macOS:** [GUI 실행/Context Search 실행.command](GUI%20실행/Context%20Search%20실행.command)를 더블클릭합니다.

**Windows:** `GUI 실행/Context Search 실행.cmd`를 더블클릭합니다. Windows 실제 실행은 미검증입니다.

처음 설치하는 팀원은 Git과 Python 3.13을 설치하고 전체 저장소를 받은 뒤 `GUI 실행/처음 설치.command` 또는 `처음 설치.cmd`를 실행하세요. 최초 설치와 모델 다운로드에는 인터넷이 필요합니다. 이후에는 실행 파일만 사용합니다. 상세 사용법은 [GUI 실행 안내](GUI%20실행/README.md)를 참고하세요.

터미널에서 실행하려면 저장소 루트에서:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r Role04/requirements-search.txt
.venv/bin/python Role04/scripts/launch_gui.py
```

Windows PowerShell에서는:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Role04/requirements-search.txt
.\.venv\Scripts\python.exe Role04/scripts/launch_gui.py
```

실행기는 이 프로젝트의 기존 서버를 다시 열거나 5173~5193에서 사용 가능한 포트를 선택합니다. 터미널을 유지하고 종료는 Ctrl+C입니다. 특정 포트는 `serve_web.py --port 5176 --open-browser`로 지정할 수 있습니다. 화면 예시만 보려면 `serve_web.py --demo --open-browser`를 사용하세요.

## 기능과 데이터

- 의미 검색: 엔진의 상위 5개 순위·유사도·본문 발췌를 그대로 표시합니다. 유사도는 정답 확률이 아닙니다.
- 시간 검색: 생성일·수정일과 명시 날짜, 지난달, 최근 N일 등 최신 엔진이 지원하는 표현을 사용합니다. 잘못되거나 지원하지 않는 표현은 오류로 안내합니다.
- 관계: Role01의 내용·참조 후보와 Role03 DB의 해결된 정적 참조를 구분합니다. 관련 파일을 검색 결과와 별도 목록으로 제공하며 근거를 표시합니다.
- 원본: 파일 ID로 원본을 찾아 다운로드합니다. 코드·텍스트·이미지 미리보기와 PDF 페이지 렌더링을 제공합니다.
- 등록: 서버에 복사 → 본문 추출 → SQLite·임베딩·관계 갱신 → 검색 가능 상태를 작업 API로 추적합니다. 중복 등록을 감지합니다.
- 갱신: 내 파일 화면의 갱신 버튼으로 앱 데이터·DB·검색·관계를 다시 만듭니다. 파일별 실패는 로그로 확인합니다.

`prepare_search.py`는 검증 대상 Git 커밋 `bf2b9af642e0514c784df543aa2fde34e82172a1`의 Role01·02·03과 갱신 코드를 `runtime/backend/`에 준비합니다. 초기 목록은 203개입니다. 팀원 작업 폴더와 기존 `runtime/search`를 변경하지 않습니다. 동일 버전의 준비를 다시 실행해도 등록 파일과 갱신 데이터를 덮어쓰지 않습니다. 11월 9일 버전은 기존 파일·수동 라벨을 보존하여 전환하고 이전 폴더를 `runtime/backend-before-*`로 백업합니다. 파일 ID가 충돌하면 적용 전에 중단합니다.

`runtime/backend/Role01/dataset/files/uploads/`에는 사용자가 등록한 파일이 남습니다. 실행 폴더 전체는 Git에서 제외되며, 데이터 보존을 위해 백업하세요. GUI 갱신은 GitHub 소스 업데이트와 별개입니다. 다른 팀 커밋으로 변경할 때는 호환성을 검증하고 준비 버전을 갱신해야 합니다.

이미지와 OCR 전용 새 문서의 검색 등록은 지원하지 않습니다. 기존 OCR 본문은 감사 데이터의 원본 SHA-256과 일치할 때만 재사용합니다. 기존 수동 프로젝트·역할 라벨을 유지하며, 빈 라벨에는 Role02 v3.1의 확인 불필요 예측만 적용합니다. 확인이 필요한 예측과 신뢰도는 상세 정보에서 따로 표시합니다. 실제 사용 이력을 추정하지 않습니다. OS 폴더 열기는 미지원입니다.

## 최신 팀 기능 연결

- Role02의 생성 설명을 파일 ID로 결합하여 목록·검색 설명·임베딩에 반영합니다.
- 과목·역할을 포함한 검색(예: `시계열분석 코드`)을 지원합니다. 팀 엔진은 등록된 라벨 단어를 필터로 해석하므로 여러 역할을 함께 적으면 결과가 제한될 수 있습니다.
- 작업 보기에서 제공된 과목·프로젝트별 파일을 모아 볼 수 있습니다. 같은 작업이라는 추정은 추가하지 않습니다.
- 내 파일 → 폴더 자동 연결에 자료 폴더의 전체 경로를 입력하면 서버 실행 중 변경을 감지하고 보관본·본문·분류·DB·인덱스를 갱신합니다. 연결 해제 후 보관본은 유지합니다.
- 등록·갱신 시 새 파일 및 본문이 달라진 파일의 자동 분류를 계산합니다. 삭제된 파일의 자동 결과도 목록에서 제거합니다.
- `http://127.0.0.1:11434`에서 Ollama의 `qwen3.5:4b`가 실행 중이면 새 설명도 생성합니다. 없으면 기존 설명과 본문으로 계속 검색하며 완료 안내에 사유를 표시합니다. 모델을 자동 설치하지 않습니다.
- HTML·CSS·JavaScript·SQL도 등록할 수 있습니다. 각 파일 25MB 제한입니다.

## 구성

- `web/`: 기존 브라우저 GUI와 API 어댑터
- `scripts/search_api.py`: 검색·관계·원본·작업 상태 연결
- `scripts/refresh_workspace.py`: 팀 갱신기의 이전 추출 결과 경로를 보완하고 원본 해시 검증 후 재사용
- `scripts/prepare_search.py`: 동일 버전 백엔드·데이터 준비
- `scripts/launch_gui.py`: 실행 중 서버 재사용·포트 선택
- `scripts/serve_web.py`: localhost 정적 화면·동일 출처 API
- `runtime/logs/`: 갱신 로그
- `runtime/backend/update_backups/`: 갱신 직전 데이터 백업

검색·갱신은 이 컴퓨터에서 실행합니다. 외부 추론 API로 문서를 전송하지 않습니다. 서버는 127.0.0.1에만 바인딩하며 클라이언트 임의 경로를 파일 접근에 사용하지 않습니다.

## 개발 검증

```sh
.venv/bin/python -m unittest discover -s Role04/tests -p 'test_*.py'
node --test Role04/tests/*.mjs
.venv/bin/python -m pip check
```

HTTP 테스트에는 로컬 포트 바인딩 권한이 필요합니다. 실제 모델·등록 흐름 검증 기록은 [최신 통합 점검](docs/integration-2026-11-19.md)을 참고하세요. 이전 문서의 미지원 설명은 작성 당시 상태이며 현재 기능은 이 문서를 기준으로 합니다.
