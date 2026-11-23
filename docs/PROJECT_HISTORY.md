# AI-X 개발 기록

AI-X는 “지난달 R 과제에 쓴 데이터”처럼 기억나는 상황을 입력해 파일과 관련 자료를 찾는 개인 검색 시스템이다.

**개발 흐름: 자료 정리 → 의미 검색 → 설명·시간·분류 추가 → 관련 파일 추천 → GUI·자동 갱신 통합**

개발·실험 조사 기준은 2026-11-23의 `main` [6606aee](https://github.com/eunkyo00/AI-X/commit/6606aee277c154051d3d94be07842b85bed1a687)이다. 코드·보고서·평가 자료와 커밋 142개를 확인했다. 아래 날짜는 별도 표시가 없으면 커밋 기록일이다. 파일 목록은 현재 `main` 기준이며, 비슷한 버전과 반복 작업은 묶었다.

## 1. 프로젝트 개요

파일명과 위치를 몰라도 내용, 생성·수정 시각, 과목·파일 역할, 파일 간 참조를 단서로 자료를 찾는 것이 목표다.

사용 흐름은 다음과 같다.

**파일 등록 → 본문 추출·설명·분류 → DB·검색 인덱스 갱신 → 자연어 검색 → 결과·근거·관련 파일 확인 → 원본 열기**

| 영역 | 담당 기능 |
| --- | --- |
| Role01 — 검색 | 의미 검색, 시간·과목·역할 조건, 관련 파일 추천 |
| Role02 — 분류·평가 | 데이터·정답 구성, 과목·유형 분류, 설명 생성, 성능 평가 |
| Role03 — 파일 처리·DB | 파일 ID·메타데이터·본문 저장, 참조 추출, 데이터 품질 점검 |
| Role04 — GUI·통합 | 검색 화면, 파일 등록·열기, 백엔드 연결, 자동 갱신 |

주요 기술은 Python, E5 임베딩(문장의 의미를 벡터로 표현), 로지스틱 회귀, SQLite, Ollama/Qwen이다. 현재 GUI는 HTML·CSS·JavaScript와 로컬 Python 서버로 동작한다. 초기 PySide6 구상은 실제 웹 GUI와 구분한다. [프로젝트 소개](../README.md)

## 2. 전체 개발 타임라인

| 시기 | 주요 작업 | 결과 |
| --- | --- | --- |
| 9/17~9/24 | 저장소 생성, 문제 정의, 검색 화면 구상 | 상황으로 파일을 다시 찾는 목표 설정 |
| 9/28~10/12 | 강의·코드·데이터 수집, 라벨·설명 작성, 본문 추출 | 여러 형식의 파일을 검색할 기반 마련 |
| 10/12~10/18, 6주차 보고 | SQLite와 파일 참조 추출 구현 | 161개 입력 사본 저장, 파일 ID로 조회 |
| 10/14~10/26 | 의미 검색·평가 질문 구성, 추출 실패 분석, API용 엔진 분리 | 동명 파일 문제를 발견하고 ID 기반 평가로 보완 |
| 10/19, 점검 보고 | DB·참조·파일 크기·추출 품질 검수 | TSV 2개 복구, 줄바꿈 차이와 참조 오탐 확인 |
| 10/19~10/29 | 웹 GUI 개발, 설명·시간·재정렬 실험, 실제 검색·원본 열기 연결 | 검색부터 근거·PDF 미리보기까지 동작 |
| 10/29~11/12 | 관계 추천, 과목·유형 분류, Qwen 설명 생성, 정답 ID 교정 | 검색 단서 확대, 신규 과목 감지와 설명 효과 평가 |
| 11/16 | 폴더 감시·통합 갱신·바뀐 파일의 검색 데이터 갱신 | 추가·수정·삭제를 검색 데이터에 반영 |
| 11/19~11/23 | 관계 추천 V3~V5 비교, GUI 전체 흐름 검증·공유 | 분류·DB·검색·추천·원본을 하나의 앱으로 통합 |
| 11/23 | 신규 표본과 처리 결과 추가 | 저장소 기준 파일 204개, V5 추천 1,020건 |

GUI의 실제 검증일은 11/9·11/19·11/23이며, 해당 보고서를 GitHub에 공유한 커밋은 11/23이다. [6주차 보고](../Role03/WEEK06_REPORT.md), [GUI 검증 기록](../Role04/docs/integration-2026-11-23.md)

## 3. 역할별 작업과 파일

개발 흐름 순서로 정리했다. `*.py`처럼 표시한 항목은 여러 버전 묶음, `/`로 끝나는 항목은 폴더 안의 모든 파일이다. 모델은 학습한 분류기, 캐시는 재사용하려고 저장한 계산 결과다.

### Role01 — 파일 검색·관련 자료 추천

**본문 검색 → 설명·시간 조건 추가 → 관련 파일 추천 → 검색 갱신**

| 순서·종류 | 파일·묶음 | 핵심 내용 |
| --- | --- | --- |
| 안내 | [README.md](../Role01/README.md) | 검색 담당 범위·계획·실행 방법 |
| 파일 목록 | [file_inform.py](../Role01/file_inform.py) · [file_reload*.py](../Role01/) · [paths.py](../Role01/paths.py) | 파일 ID·경로·날짜 수집, 기존 값 보존·정렬 |
| 본문 추출 | [extract_content*.py](../Role01/) | 문서·코드·표에서 글 추출; 이전 구현도 보관 |
| 처리 결과 | [metadata.csv](../Role01/metadata.csv) · [extracted_text.csv](../Role01/extracted_text.csv) | 파일 목록·수동 라벨·추출 본문 |
| 기본 검색 | [search_model(prior).py](../Role01/search_model%28prior%29.py) · [search_model.py](../Role01/search_model.py) · [search_model_modified.py](../Role01/search_model_modified.py) | E5 의미 검색, 파일별 순위·ID 기준 평가 |
| 검색 개선 | [search_model_rerank.py](../Role01/search_model_rerank.py) · [search_model_description.py](../Role01/search_model_description.py) · [search_model_time.py](../Role01/search_model_time.py) | 순위 재정렬·설명 추가·시간 조건 실험 |
| 관련 파일 조회 | [search_model_time_related*.py](../Role01/) | 시간 검색에 관련 파일·근거 조회와 진단 추가 |
| 앱 연결 | [search_engine*.py](../Role01/) | GUI에서 호출할 검색 엔진; 시간·통합 버전 포함 |
| 검색 갱신 | [refresh_search.py](../Role01/refresh_search.py) | 바뀐 파일만 새로 임베딩, 검색 인덱스 갱신 |
| 추천 코드 | [file_relations*.py](../Role01/) | 참조·폴더 → 내용 유사도 → E5 → 여러 단서·주차 결합 |
| 추천 결과 | [file_relations*.csv](../Role01/) | 기본·V3·V4·V5의 관련 파일·점수·근거 |
| 검색 정답 | [evaluation_queries*.csv](../Role01/) | 질문·정답 ID와 교정 전후 백업 |
| 검색 평가 | [evaluation_results*.csv](../Role01/) | 기본·재정렬·설명·시간 검색의 상위 결과와 성공 여부 |
| 관계 평가 | [evaluate_relations.py](../Role01/evaluate_relations.py) · [relations_ground_truth*.csv](../Role01/) · [relations_evaluation*.csv](../Role01/) | 관련 파일 정답·백업, 버전별 점수·상세 결과 |
| 오류 점검 | [search_rank_diagnosis.py](../Role01/search_rank_diagnosis.py) · [missed_files.py](../Role01/missed_files.py) · [check_failed_r.py](../Role01/check_failed_r.py) · [check_pdf.py](../Role01/check_pdf.py) · [failed_*.csv](../Role01/) | 놓친 정답·순위·빈 본문·R/PDF 추출 문제 확인 |
| 분류·감시 자동화 | [auto_label.py](../Role01/auto_label.py) · [automation_code/](../Role01/automation_code) | 초기 과목 추정, 분류·시간 정보 생성, 폴더 감시 실행 |
| 자동화 결과 | [auto_label_results.csv](../Role01/auto_label_results.csv) · [auto_classification_results.csv](../Role01/auto_classification_results.csv) · [auto_time_results.csv](../Role01/auto_time_results.csv) | 과목·유형 예측과 시간 정보 |
| 캐시·임시 결과 | [.extraction_cache.json](../Role01/.extraction_cache.json) · [embedding_cache/](../Role01/embedding_cache) · [__pycache__/](../Role01/__pycache__) | 원본 해시·저장 임베딩·Python 실행 캐시 |

### Role02 — 파일 분류·설명 생성·성능 평가

**데이터·정답 준비 → 과목·유형·시간 분류 → 설명 생성 → 효과 비교**

| 순서·종류 | 파일·묶음 | 핵심 내용 |
| --- | --- | --- |
| 안내 | [README.md](../Role02/README.md) | 데이터·정답 구성과 평가 기준 |
| 과목 분류 | [PROJECT_CLASSIFIER.md](../Role02/PROJECT_CLASSIFIER.md) · [project_classifier*.py](../Role02/) · [train_project_classifier*.py](../Role02/) · [classify_new_file*.py](../Role02/) | v1~v3.1 입력·학습·예측, 새 과목 감지 |
| 과목 모델·결과 | [project_classifier_artifacts*/](../Role02/) | 학습 모델(.joblib), 점수(JSON), 파일별 평가·오분류표(CSV); v1·v2·v3·백업 |
| 유형 분류 | [FILE_METADATA_CLASSIFIERS.md](../Role02/FILE_METADATA_CLASSIFIERS.md) · [role_classifier.py](../Role02/role_classifier.py) · [train_role_classifier.py](../Role02/train_role_classifier.py) · [classify_role.py](../Role02/classify_role.py) | 강의·실습·코드·과제·데이터·안내 6종 분류, 규칙+모델 |
| 유형 모델·결과 | [role_classifier_artifacts/](../Role02/role_classifier_artifacts) | 유형 모델·정확도·파일별 예측·오분류표 |
| 시간 정보 | [time_classifier.py](../Role02/time_classifier.py) · [evaluate_time_classifier.py](../Role02/evaluate_time_classifier.py) · [time_classifier_artifacts/](../Role02/time_classifier_artifacts) | 수정일 등을 월·분기·반기·계절로 변환, 처리 결과 저장 |
| 분류 통합 | [classify_file_metadata.py](../Role02/classify_file_metadata.py) · [classify_metadata.py](../Role02/classify_metadata.py) | 과목·유형·시간을 한 번에 계산, 수동 값과 자동 예측 분리 |
| 설명 생성 | [description_generator.py](../Role02/description_generator.py) · [merge_descriptions.py](../Role02/merge_descriptions.py) | Qwen으로 짧은 설명 생성, 수동 설명 보존·병합 |
| 생성 데이터 | [metadata_*.csv](../Role02/) · [description_hashes.json](../Role02/description_hashes.json) | 생성 설명·진행/병합본·자동 분류, 변경 확인용 본문 해시 |
| 설명 비교 | [DESCRIPTION_AB_EXPERIMENT.md](../Role02/DESCRIPTION_AB_EXPERIMENT.md) · [description_ab_experiment.json](../Role02/description_ab_experiment.json) | 설명 유무에 따른 신뢰도·새 과목 감지 비교 |
| 평가·실패 기록 | [auto_classification_result.csv](../Role02/auto_classification_result.csv) · [search_fail.txt](../Role02/search_fail.txt) | 과목별 예측·오분류와 검색 실패 사례 |
| 검증 코드·산출물 | [test_*.py](../Role02/) · [test_output/](../Role02/test_output) | 설명·신규 파일·분류·시간 시험, 시험용 생성 설명; 일부는 과거 호출 방식 |

### Role03 — 파일 정보 저장·참조 확인·품질 점검

**DB 저장 → 파일 간 참조 확인 → 오류 원인 조사·복구**

| 순서·종류 | 파일·묶음 | 핵심 내용 |
| --- | --- | --- |
| 안내 | [README.md](../Role03/README.md) | DB 실행·조회 방법, 지원 범위 |
| 입력 사본 | [input/](../Role03/input) | 파일 161개의 목록·본문 사본, 원본 커밋 기록 |
| DB 코드 | [file_db.py](../Role03/file_db.py) · [query_example.py](../Role03/query_example.py) | SQLite 저장·조회, 코드·문서의 파일 참조와 근거 추출 |
| DB·처리 결과 | [files.sqlite3](../Role03/output/files.sqlite3) · [audit.csv](../Role03/output/audit.csv) · [relations.csv](../Role03/output/relations.csv) · [summary.json](../Role03/output/summary.json) · [source_checks.json](../Role03/output/source_checks.json) | 파일 DB·원본 대조·참조·처리 집계·원본 확인 기록 |
| 품질 점검 | [audit_results.py](../Role03/audit_results.py) · [*_issues.csv](../Role03/output/) · [quality_summary.json](../Role03/output/quality_summary.json) | 크기·빈 본문·미등록 참조의 원인 분류 |
| 개발·점검 보고 | [WEEK06_REPORT.md](../Role03/WEEK06_REPORT.md) · [REFERENCE_CHECK_REPORT.md](../Role03/REFERENCE_CHECK_REPORT.md) · [QUALITY_CHECK_REPORT.md](../Role03/QUALITY_CHECK_REPORT.md) | DB 구현 → 참조 보완 → 줄바꿈 차이·TSV 복구·오탐 수정 |
| 검증 | [test_file_db.py](../Role03/test_file_db.py) | 중복 ID·경로·참조 상태·재등록·실패 처리 시험 |

### Role04 — 화면에서 등록·검색·열기까지 연결

**화면 설계 → 웹 GUI → 실제 검색·등록 연결 → 자동 갱신·통합 검증**

| 순서·종류 | 파일·묶음 | 핵심 내용 |
| --- | --- | --- |
| 현재 안내 | [README.md](../Role04/README.md) | GUI 기능·실행·연동 범위·남은 한계 |
| 화면 구상 | [images/](../docs/images) | 초기·수정 화면 PNG와 생성 프롬프트 MD |
| 설계·개발 기록 | [gui-usability-plan.md](../Role04/docs/gui-usability-plan.md) · [web-development.md](../Role04/docs/web-development.md) · [api-contract.md](../Role04/docs/api-contract.md) | 사용 흐름·웹 구현·GUI/백엔드 데이터 규격 |
| 검색 연결 기록 | [search-engine-validation.md](../Role04/docs/search-engine-validation.md) | 실제 검색·캐시·원본 열기·PDF 표시 검증 |
| 통합 보고 | [integration-*.md](../Role04/docs/) | 11/9 등록·검색 → 11/19 분류·동기화 → 11/23 V5 추천 검증 |
| 인수인계 | [gui-handoff.md](../Role04/docs/gui-handoff.md) | 이전 GUI의 시연·사용성 점검과 미완료 항목 |
| 화면 뼈대 | [index.html](../Role04/web/index.html) · [styles.css](../Role04/web/styles.css) · [app.js](../Role04/web/app.js) | 화면 구성·스타일·메뉴·검색 입력 |
| 검색 화면 | [search-data.mjs](../Role04/web/search-data.mjs) · [search-view.mjs](../Role04/web/search-view.mjs) · [search-service.mjs](../Role04/web/search-service.mjs) | 예시 데이터·결과 표시·비동기 검색·취소·오류 처리 |
| 파일·설정 화면 | [workspace-service.mjs](../Role04/web/workspace-service.mjs) · [workspace-ui.mjs](../Role04/web/workspace-ui.mjs) · [history.mjs](../Role04/web/history.mjs) | 파일 등록·보관·API 호출·설정·미리보기·최근 검색 |
| 백엔드 준비·실행 | [prepare_search.py](../Role04/scripts/prepare_search.py) · [launch_gui.py](../Role04/scripts/launch_gui.py) · [serve_web.py](../Role04/scripts/serve_web.py) | 검증한 백엔드 준비, 서버 실행·포트 선택·화면 열기 |
| 검색·등록 연결 | [search_api.py](../Role04/scripts/search_api.py) · [registration_api.py](../Role04/scripts/registration_api.py) · [refresh_workspace.py](../Role04/scripts/refresh_workspace.py) | 검색·분류·관계·원본 API, 업로드 해석, 해시 확인·갱신 |
| 설치·실행 파일 | [GUI 실행/](../Role04/GUI%20%EC%8B%A4%ED%96%89) · [requirements-search.txt](../Role04/requirements-search.txt) | Mac/Windows 설치·실행 스크립트, 사용 안내·필요 패키지 |
| 검증 코드 | [test_*](../Role04/tests/) | API·등록·갱신·검색·분류 연결과 화면 동작 시험 |
| 검증용 파일 | [fixtures/](../Role04/tests/fixtures) | 코드·CSV·텍스트·미지원 형식 시험 자료 |

## 4. 핵심 실험과 결과

### 검색: 재정렬보다 설명 추가가 효과적이었다

저장된 결과 중 같은 질문·정답 ID 158개를 비교했다. Hit@5는 정답 파일이 상위 5개에 포함된 비율이다.

| 방식 | 성공 | Hit@5 |
| --- | ---: | ---: |
| 기본 의미 검색 | 129/158 | 81.65% |
| 상위 후보 재정렬 | 129/158 | 81.65% |
| 파일 설명 추가 | 158/158 | 100.00% |

재정렬은 성공·실패가 한 건씩 바뀌어 평균 개선이 없었다. 설명 추가는 기존 질문에서 효과가 있었다. 개발에 쓰지 않은 새 질문으로 확인한 최종 성능은 아니다. [재정렬 결과](../Role01/evaluation_results_rerank.csv), [설명 결과](../Role01/evaluation_results_description.csv)

시간 조건과 정답 ID를 교정한 결과는 **194질의 중 192개 성공(98.97%)**, 이 중 시간 질의는 **23/23 성공**이다. 이전 결과와 정답 ID가 171행에서 달라져 점수 변화를 시간 알고리즘만의 효과로 볼 수는 없다. [시간 검색 결과](../Role01/evaluation_results_time_fixed.csv)

### 분류: 기존 과목 선택과 신규 감지를 나누어 평가했다

| 실험 | 결과 | 의미 |
| --- | --- | --- |
| 기존 과목 분류 v3.1 | 158개·5-fold 정확도 100%, Macro F1 1.0 | 기존 5개 과목 선택 성능. 자동 확정은 148/158개 |
| 생성 설명 A/B | 신규 감지 34/41 → 39/41 | 기존 자동 확정은 149개 → 148개로 한 개 감소 |
| 자료 유형 분류 | 규칙 추가 후 정확도 89.87% → 91.14%, Macro F1 0.830929 → 0.850884 | 158개·4-fold에서 임베딩만 쓸 때보다 개선 |

신규 감지 실험은 빈 과목 라벨 41개를 모두 신규로 가정했고, 설명 조건마다 판정 기준도 다시 맞췄다. 실제 신규 과목 정답과 작업 단위 독립 검증은 추가로 필요하다. [과목 지표](../Role02/project_classifier_artifacts_v3/project_classifier_metrics.json), [설명 A/B](../Role02/DESCRIPTION_AB_EXPERIMENT.md), [유형 지표](../Role02/role_classifier_artifacts/role_classifier_metrics.json)

### 관계 추천: V5가 V4의 누락을 줄였다

검토 집합의 출발 파일 17개에 대한 결과다. Recall@5는 정답 관련 파일의 회수 비율, MRR@5는 첫 정답이 얼마나 앞에 나오는지 나타낸다.

| 버전 | 사용한 단서 | Hit@5 | Recall@5 | MRR@5 |
| --- | --- | ---: | ---: | ---: |
| V3 | 의미 유사도 | 0.8824 | 0.8431 | 0.8529 |
| V4 | 의미·과목·역할·시간·폴더·참조 | 0.9412 | 0.8137 | 0.7706 |
| V5 | V4에 동일 주차 추가·가중치 조정 | 0.9412 | 0.8725 | 0.8471 |

V4는 적중률이 높아졌지만 회수율과 순위는 나빠졌다. V5는 이를 보완했으나 MRR은 V3보다 조금 낮다. 같은 확정 정답으로 채점했지만 저장된 전체 대상은 V3/V4 202개, 최신 V5 204개로 달라 주차 단서만의 효과라고 단정할 수는 없다. [관계 평가 요약](../Role01/relations_evaluation_summary.csv)

### 처리 속도: 변경 없는 파일을 재사용하도록 개선했다

초기에는 본문·임베딩을 전체 생성했다. 이후 파일 해시와 입력별 캐시를 도입했다. 203개 반복 갱신 로그에서는 본문·임베딩 모두 203개를 재사용했고, 목록·본문·설명·분류·인덱스 단계가 총 39.61초였다. DB·관계 생성은 별도 시간이며, 같은 조건의 전량 처리 측정이 없어 속도 향상 배수는 확인할 수 없다. [시간 로그](../update_timing.log)

## 5. 주요 문제와 해결

| 문제 | 대응과 결과 |
| --- | --- |
| 동명 파일·오래된 ID로 오채점 | 파일 ID·경로로 평가하고 정답표 교정 |
| 본문 추출 실패·경로 차이 | 형식별 추출·TSV 복구·경로 정규화, 원본 해시가 같을 때 기존 본문 재사용 |
| 잘못된 관련 파일 연결 | 참조 근거·불확실 상태를 저장하고 GUI에서 확인/추론 구분 |
| 갱신 실패·수정 후 오래된 예측 | 임시 결과 검증·백업 복원, GUI에서 변경 파일 재분류 |
| PDF 뷰어 빈 화면 | 서버에서 페이지를 이미지로 렌더링하여 표시 |

## 6. 현재 상태와 남은 과제

기준 커밋의 저장 결과는 **파일 204개, 본문 추출 성공 204개, 코드·문서의 참조 197건, V5 추천 1,020건**이다. PDF·R·노트북·CSV·Markdown·Python·JSON·TSV·XLSX가 포함된다. GUI의 11/23 검증은 고정 백엔드의 **203개** 기준이므로 두 집계를 구분한다. [현재 처리 집계](../Role03/output/summary.json), [최신 GUI 검증](../Role04/docs/integration-2026-11-23.md)

문서 조사 시 DB·분류 로직·GUI 테스트 63개가 통과했다. 최상위 갱신 테스트는 21개 중 19개 통과·2개 실패로, 과거 배치 등록 API와 현재 GUI API의 계약 차이가 남아 있다. DB 구조 검사는 정상이다.

남은 과제는 다음과 같다.

- 데이터·질문·설정을 고정한 독립 최종 평가와 키워드 기준선 비교
- 실제 신규 과목과 주차 단서가 없는 파일의 분류·추천 검증
- Windows GUI, 외부 사용자 사용성, 최신 GUI의 신규 Qwen 설명 생성 검증
- 새 이미지·OCR 전용 문서 등록과 강제 종료 중 갱신 복구 보완

현재는 과목별 파일과 참조 관계를 보여 준다. 사용자가 실제로 언제 어떤 작업에 썼는지까지 확인하는 기능은 아니다.

## 7. 공통 파일·원본 자료·실행 산출물

### 공통 실행·설정

| 순서·종류 | 파일·묶음 | 핵심 내용 |
| --- | --- | --- |
| 프로젝트 안내 | [README.md](../README.md) · [PROJECT_HISTORY.md](../docs/PROJECT_HISTORY.md) | 프로젝트 소개·전체 개발 기록 |
| 갱신 실행 | [update_pipeline.py](../update_pipeline.py) · [update_pipeline_integrated.py](../update_pipeline_integrated.py) · [update_data.py](../update_data.py) · [update_data_backup_before_v5.py](../update_data_backup_before_v5.py) | 목록 → 본문 → 설명·분류 → DB·검색·추천 갱신; 이전 구현 보관 |
| 폴더 감시 | [auto_refresh.py](../auto_refresh.py) | 추가·수정·삭제 감지, 변경을 모아 갱신 요청 |
| 공통 시험 | [test_auto_refresh.py](../test_auto_refresh.py) · [test_update_data.py](../test_update_data.py) · [test_search.py](../test_search.py) | 감시·갱신·검색 동작 확인 |
| 실행 로그 | [backend.log](../backend.log) · [update_timing.log](../update_timing.log) | 실행 과정·오류·단계별 시간 |
| 환경·개발 설정 | [requirements.txt](../requirements.txt) · [.gitignore](../.gitignore) · [.vscode/](../.vscode) · [Role02/.gitignore](../Role02/.gitignore) · [Role03/.gitignore](../Role03/.gitignore) · [Role04/.gitignore](../Role04/.gitignore) · [Role04/.vscode/](../Role04/.vscode) | 필요 패키지, Git 제외 규칙, 편집기 실행 설정 |
| 이전 묶음 | [Role02.zip](../Role02.zip) | 과거 Role02 코드·모델·평가 파일 압축본 |
| 별도 저장소 연결 | [AI-X-GUI](../AI-X-GUI) | Git 연결 항목; 이 저장소에 개별 구현 파일은 포함되지 않음 |

### 검색·평가에 사용한 원본 자료

아래 자료는 검색 대상이다. 자료 안의 YOLO·R 분석 기능을 AI-X 자체 기능으로 세지는 않는다. 폴더 항목 수에는 출처·관리 파일도 포함된다. 원본 압축 파일은 보관·출처 기준이며 현재 검색 대상 전체와 같지는 않다.

| 순서·종류 | 파일·묶음 | 핵심 내용 |
| --- | --- | --- |
| 데이터 안내 | [README.md](../data/README.md) | 원본·정답 구분, 자료 출처·관리 기준 |
| 압축 원본 | [raw/](../data/raw) | 공개 데이터사이언스·자료구조·역사·딥러닝·시계열·캡스톤 ZIP 9개와 폴더 유지 파일 |
| 라벨 묶음 | [labeled/](../data/labeled) | 역사·캡스톤 라벨 ZIP 4개와 폴더 유지 파일 |
| 공개 수업 자료 | [microsoft-data-science-for-beginners/](../Role01/dataset/files/microsoft-data-science-for-beginners) | 55항목: 수업 MD·과제·노트북·표 데이터, 출처·라이선스 |
| 데이터사이언스 | [데이터사이언스/](../Role01/dataset/files/%EB%8D%B0%EC%9D%B4%ED%84%B0%EC%82%AC%EC%9D%B4%EC%96%B8%EC%8A%A4) | 38개: 강의 PDF·실습 노트북·CSV |
| 딥러닝 | [딥러닝_수업자료/](../Role01/dataset/files/%EB%94%A5%EB%9F%AC%EB%8B%9D_%EC%88%98%EC%97%85%EC%9E%90%EB%A3%8C) | 11개: 신경망·학습 방법 강의 PDF |
| 금융 | [생활속의금융/](../Role01/dataset/files/%EC%83%9D%ED%99%9C%EC%86%8D%EC%9D%98%EA%B8%88%EC%9C%B5) | 3개: 금융 개념·상품 강의 PDF |
| 시계열 | [시계열 분석_code/](../Role01/dataset/files/%EC%8B%9C%EA%B3%84%EC%97%B4%20%EB%B6%84%EC%84%9D_code) | 38항목: 주차별 R 분석 코드·폴더 유지 파일 |
| 캡스톤 | [캡스톤디자인/](../Role01/dataset/files/%EC%BA%A1%EC%8A%A4%ED%86%A4%EB%94%94%EC%9E%90%EC%9D%B8) | 17개: YOLO·영상 전송·거리 측정·음성 안내 코드/노트북 |
| 한국근현대사 | [한국근현대사역사기행0*/](../Role01/dataset/files/) | 01~03 폴더 42항목: 역사 읽기 PDF·폴더 유지 파일 |
| 신규 등록 표본 | [op.py](../Role01/dataset/files/op.py) · [password_generator.py](../Role01/dataset/files/password_generator.py) · [test_*.py](../Role01/dataset/files/) | 직접 등록한 Python 5개: 간단 코드·비밀번호 생성·검색/분류 시험 |

### 실행할 때 생성되는 파일·폴더

Git에 올라온 파일과 별개로, 실행 코드가 만드는 주요 산출물이다.

| 위치 | 핵심 내용 |
| --- | --- |
| `Role04/runtime/backend/` | GUI 실행용 코드·파일·DB·검색 데이터 |
| `Role04/runtime/logs/` | GUI 갱신 작업 로그 |
| `Role04/runtime/backend/failed_uploads/` | 분석에 실패한 업로드 보관 |
| `Role01/search_index/` | 본문 조각 정보(`index.json`)·검색 벡터(`embeddings.npz`) |
| `Role01/embedding_cache/per_file/` | 파일별 임베딩 캐시 |
| `Role01/.file_id_state.json` | 다음 파일 ID 번호 |
| `.auto-refresh/` | 연결 폴더 설정·마지막 반영 상태 |
| `.update-data.lock`, `.update-*/` | 중복 갱신 방지·처리 중 임시 데이터 |
| `update_backups/`, `Role04/runtime/backend/update_backups/` | 반영 전 CSV·DB·인덱스 백업 |

파일 목록 기준 `main`([52c9faa](https://github.com/eunkyo00/AI-X/commit/52c9faad79c1c763e0d79156c11e6f1f7f27c926))의 추적 항목 **436개**를 위 묶음에 빠짐없이 포함했다. 비슷한 버전·백업은 함께 표시했으며, 파일을 옮기거나 삭제하지 않았다. [조사 기준 커밋 이력](https://github.com/eunkyo00/AI-X/commits/6606aee277c154051d3d94be07842b85bed1a687/)
