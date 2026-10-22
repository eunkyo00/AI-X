# GUI ↔ 팀원 서비스 연결 규격 초안 (gui-v1)

작성: 2026-10-19. 프런트엔드 구현 기준의 **합의 전 초안**이다. 검색·DB 담당자가 구현하거나 검토한 규격이 아니다. 현재 팀원 API가 없으므로 실제 통합 검증은 대기 상태다.

## 연결 구조

웹 화면 → `ApiWorkspace` → 팀원의 Python HTTP 서버 → 검색·DB·파일 처리.

설정 화면에서 모드를 **팀원 API**로 선택하고 API 기본 주소를 저장한다. 예: `http://127.0.0.1:8000/api`. 기본 주소에 아래 경로를 붙인다. 인증·쿼리·해시를 주소에 넣지 않는다.

개발 서버는 `http://127.0.0.1:5173` 출처의 CORS와 `GET`, `POST`, `OPTIONS`, `Content-Type`을 허용해야 한다. localhost와 127.0.0.1은 다른 출처다. 현재 어댑터는 `credentials: omit`, 리다이렉트 금지이며 인증 없는 로컬 개발용이다. 배포용 인증은 별도 합의한다. 프런트엔드가 원본 경로를 임의로 지정해 OS 명령을 실행하지 않는다.

## 담당 경계

- 1번: 질의 해석, 순위, 검색 근거, 관련 파일·작업 관계 판단.
- 3번: 등록, 파일 ID·경로, 실제 파일 접근, 추출·인덱싱 작업 상태, 파일 내용 응답.
- GUI: 비동기 요청·표시·오류 복구·선택·사용성 점검.
- 2번: 실제 통합에 쓸 질문·정답·대표 파일 세트 제공 및 검수.

## 공통 파일 형식

```json
{
  "file_id": "file-001",
  "name": "학생 데이터.csv",
  "path": "R_project/data/학생 데이터.csv",
  "type": "data",
  "role": "입력 데이터",
  "modified_at": "2026-10-15T12:00:00+09:00",
  "size": 2048,
  "task_id": "task-r-01",
  "task_name": "R 데이터 분석 과제",
  "index_status": "ready",
  "summary": "분석 코드에서 참조하는 입력 파일입니다.",
  "evidence": [
    {
      "text": "analysis.R에 파일 읽기 구문이 있습니다.",
      "certainty": "confirmed"
    }
  ]
}
```

필수: 문자열 `file_id`, `name`. 나머지는 누락·null 허용. 크기는 바이트 숫자 또는 표시 문자열, 수정 시각은 ISO 문자열이다. 미제공 역할·날짜·크기는 알 수 없음, 근거는 빈 목록으로 표시한다. task_id가 없으면 같은 작업으로 묶지 않는다.

`type`: document/data/code/image/presentation. 미제공 시 확장자에서 파일 형식만 분류한다. `certainty`: confirmed/inferred. 다른 값은 분류 미제공으로 표시하며 확인된 사실로 바꾸지 않는다. 수정 시각을 사용 시각으로, 저장 구문을 실행 이력으로 표현하지 않는다.

## GET /health

```json
{
  "status": "ok",
  "contract_version": "gui-v1",
  "index_ready": false,
  "capabilities": { "reveal": false }
}
```

연결 점검은 이 응답과 GET /files를 검증한다. health만 성공했다고 전체 통합 완료로 간주하지 않는다. 실제 인덱스 준비를 모르면 index_ready를 true로 만들지 않는다.

## POST /search

입력: application/json.

```json
{ "query": "지난달 R 과제할 때 사용했던 데이터", "request_id": "프런트엔드가 만든 UUID" }
```

응답:

```json
{
  "files": [
    { "file_id": "data-1", "name": "data.csv", "type": "data", "task_id": "task-1", "task_name": "분석 과제" }
  ],
  "catalog": [
    { "file_id": "code-1", "name": "analysis.R", "task_id": "task-1", "task_name": "분석 과제" }
  ],
  "relations": [
    { "source_file_id": "code-1", "target_file_id": "data-1", "label": "코드에서 읽기 참조", "certainty": "confirmed" }
  ]
}
```

files는 **이미 정렬된 검색 결과**다. GUI는 응답 배열 순서에 따라 추천 번호를 붙이며 새로운 관련도 점수를 계산하지 않는다. 사용자가 정렬을 바꾸는 경우에만 화면에서 재정렬한다.

catalog는 상세 탐색에 필요한 추가 파일이다. 관계의 양쪽 파일이 files 또는 catalog에 포함되어야 한다. 조회되지 않는 ID로 연결된 관계는 표시하지 않는다. 중복 검색 결과 ID나 필수 필드 누락은 오류 처리하며 예시 데이터로 자동 대체하지 않는다.

초기 관련 파일은 직접 연결 1단계만 표시한다. 여러 단계의 무제한 연결을 GUI에서 추론하지 않는다. 실제 작업 맥락에 필요한 추가 파일은 서버가 catalog로 제공한다.

## GET /files

응답: `{ "files": [공통 파일 형식...] }`.

서버 등록 목록이며 file_id는 등록·검색·내용·관계 전 과정에서 동일해야 한다. index_status가 ready인 항목만 검색 준비 완료라고 표시한다. 역할·작업 정보가 없으면 생략한다.

## POST /files

파일 1개씩 multipart/form-data로 전송한다. 필드:

- `file`: 사용자가 선택한 파일 본문.
- `relative_path`: 폴더 선택 시 상대 경로, 일반 파일 선택 시 파일명.

상대 경로는 참고 메타데이터이며 서버 임의 경로 쓰기나 명령 실행에 사용하지 않는다. 경로 정규화·허용 영역 검사는 서버 책임이다. 브라우저는 사용자 PC의 원본 절대 경로를 제공하지 않는다.

응답:

```json
{
  "file": { "file_id": "file-001", "name": "학생 데이터.csv", "index_status": "processing" },
  "job_id": "job-001",
  "duplicate": false
}
```

job_id가 없으면 등록된 상태까지만 표시한다. 준비 완료를 추정하지 않는다. 같은 파일의 재등록은 서버가 안정적인 ID·중복 정책으로 처리해야 한다. `duplicate: true`는 이미 등록된 항목으로 표시한다. 분석 실패 후 재시도 정책은 1번·3번과 별도 합의한다.

GUI 제한: 파일당 25MB, 한 번에 총 100MB/500개. 서버도 허용 형식·크기를 검증해야 한다. 일부 실패해도 성공 파일은 유지하고 실패 항목만 재시도한다.

## GET /jobs/{job_id}

```json
{ "status": "processing", "phase": "텍스트 추출 중" }
```

status: processing/ready/failed. ready는 검색 인덱스까지 준비된 상태다. GUI는 약 1초 간격으로 최대 30회 확인하고, 이후 서버 등록 완료·분석 미확인 상태로 남긴다. HTTP 요청별 제한은 별도다.

GUI의 대기 중단은 서버 취소를 보장하지 않는다. 업로드 응답을 받기 전에 중단되면 결과 미확인으로 표시한다. 내 파일을 다시 조회해 실제 상태를 확인한다. 서버가 취소 API를 제공하면 별도 연결한다.

## GET /files/{file_id}/content

선택된 file_id의 바이너리 내용을 반환한다. 경로를 프런트엔드에서 받지 말고 DB의 ID로 해석한다. 누락·권한 부족 시 적절한 오류 상태를 반환한다.

GUI의 열기 동작:

- TXT/CSV/Python/R/MD/JSON/IPYNB: 읽기 전용 텍스트, 앞부분 최대 300KB.
- PNG/JPG/WEBP: 이미지 미리보기.
- PDF: sandbox iframe의 브라우저 PDF 보기. 브라우저에 따라 다운로드로 확인.
- PPTX/DOCX 등: 보관본 다운로드 후 사용자 연결 앱에서 확인.

원본 코드를 자동 실행하지 않는다. 문서 안의 스크립트·매크로 실행 기능을 GUI에서 제공하지 않는다. 원본 수정 기능도 없다.

## POST /files/{file_id}/reveal (선택)

health.capabilities.reveal이 true일 때만 호출한다. 로컬 Python 서버가 OS의 파일 관리자로 저장 폴더를 열고 `{ "status": "ok" }`를 반환한다. OS별 처리는 서버 담당자가 구현·검증해야 한다. 현재 실제 구현체가 없으므로 OS 폴더 열기는 검증 대기다.

reveal 기능이 없으면 GUI는 저장 경로와 브라우저 한계를 안내한다. 브라우저 로컬 보관본은 원본 PC 경로를 알 수 없어 직접 폴더 열기를 제공하지 않는다.

## 오류·시간 제한

현재 GUI는 HTTP 실패, JSON·필드 형식 오류, 네트워크/CORS, 404, 시간 초과를 구분해 복구 동작을 제공한다. 일반 요청 10초, 파일 업로드 60초이며 실제 처리 SLA는 팀과 합의한다. 검색 요청의 버전과 AbortSignal로 오래된 응답을 배제한다.

실제 검색 완료 기준: 검수된 실제 파일을 등록 → 서버 인덱스 ready 확인 → 상황 검색 → 동일 ID의 결과·근거·관련 파일 확인 → content/reveal 확인. MockService나 API 어댑터 단위 테스트로 이 기준을 대신하지 않는다.
