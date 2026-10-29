# 파일 처리·DB 품질 점검 결과

점검일: 2026-10-19 · Role03 · 기존 입력 사본 161개 기준

## 무엇을 했나

1. 크기가 다른 36개를 원본 ZIP의 동일 파일과 바이트 단위로 대조했다.
2. 본문 추출 미성공 12개의 실제 형식·크기·본문 상태를 확인했다.
3. 미등록 참조 122건과 불확실 참조 22건을 원본 근거·로컬 파일·제공 ZIP 목록과 대조했다.
4. TSV 2개를 Python 기본 라이브러리로 읽어 DB에 저장하도록 보완했다.
5. 외부 링크의 표시 이름을 로컬 파일로 오인한 1건을 수정했다.
6. DB를 재생성하고 테스트 12개, DB 무결성과 분류 집계 일치를 확인했다.

## 크기 불일치 36개: 줄바꿈 차이 확인

모두 R 코드다. `data/raw/시계열 분석_code.zip`의 원본 크기가 메타데이터 크기와 같고, ZIP 원본의 CRLF를 LF로 바꾸면 현재 로컬 파일과 바이트가 일치했다. 줄바꿈 외 내용 차이는 없었다.

원본 메타데이터를 덮어쓰지 않았으므로 `summary.json`의 `size_mismatches`는 36으로 유지된다. 추가 분류인 `quality_summary.json`의 `size_categories.line_endings_only`에서 36건 모두 설명된다. 미해명 크기 차이는 0건이다.

## 추출 미성공 12개: 원인과 처리

| 원인 | 수 | 처리 |
| --- | ---: | --- |
| 이미지형 PDF, 텍스트 레이어 없음 | 6 | 전체 페이지 텍스트·이미지 유무 확인. OCR 필요로 분류. OCR은 수행하지 않음 |
| `.Rhistory`, `.DS_Store` | 3 | 기록·시스템 파일로 분류. 원본과 ID 보존 |
| 실제 0바이트 R 파일 | 1 | 원본 내용 없음으로 분류. 본문을 임의 생성하지 않음 |
| TSV 형식 미지원 | 2 | 첫 100행을 Python `csv`로 읽어 DB 본문 복구 |

TSV 파일 ID는 `F153`, `F156`이다. 입력 CSV는 보존하고 DB에 반영하는 추출 결과만 보완했다. 성공 수는 149에서 151로 증가했다. 남은 미성공은 10개다.

## 미등록 참조 122건: 오탐 1건 제거, 나머지 121건 분류

`F116` 문서의 외부 Kaggle 링크 표시 이름인 `metadata.csv`를 로컬 파일 참조로 잡았던 1건을 제거했다. 외부 링크 안의 로컬 미리보기 이미지 참조는 계속 보존한다.

| 분류 | 건수 | 판정 범위 |
| --- | ---: | --- |
| 코드의 입력 데이터 | 48 | 고유 경로 10개. 로컬 자료 및 제공 ZIP에 동일 파일명 후보 없음 |
| 샘플 문서의 이미지 | 63 | 로컬 자료 및 제공 ZIP에 동일 파일명 후보 없음 |
| 문서 예제 파일 | 6 | 고유 경로 5개. `train.csv`, `test.csv`, `dog.jpg`, `test.png`, `file.csv` |
| 코드 출력 경로 | 3 | 고유 경로 2개. 코드에 적힌 생성 대상이며 실행·생성 여부는 확인하지 않음 |
| 외부 URL | 1 | 외부 다운로드 참조. 로컬 파일 소실로 해석하지 않음 |
| 합계 | 121 | 등록 파일 ID가 없는 참조들 |

제공 ZIP 전체 13개를 읽어 파일명 후보를 확인했으며 ZIP 읽기 오류는 0건이었다. 위 부재 판정은 저장소의 로컬 자료 폴더와 제공 ZIP 범위에 한정되며 다른 PC·인터넷의 파일 존재를 뜻하지 않는다. 이 참조들은 삭제하지 않고 상태 `missing`과 세부 분류를 함께 유지했다.

불확실 참조 22건은 별도로 유지했다. 파일명 후보만으로 대상 ID를 연결하지 않았다. 외부 URL·출력 경로를 `resolved`로 바꾸거나 미등록 파일의 ID를 임의 생성하지 않았다.

## 수정 후 기본 실행 결과

```json
{
  "files": 161,
  "extraction_success": 151,
  "local_files_found": 161,
  "size_mismatches": 36,
  "references": 162,
  "resolved": 19,
  "ambiguous": 22,
  "missing": 121
}
```

## 결과 파일과 재실행

- `output/size_issues.csv`: 36개 각각의 원본·실제 크기와 원본 ZIP 근거.
- `output/extraction_issues.csv`: 기존 미성공 12개의 원인·현재 DB 상태·PDF 검사 수치.
- `output/reference_issues.csv`: 미등록 121건과 불확실 22건의 원문·위치·분류·확인 근거.
- `output/quality_summary.json`: 분류별 집계.
- `output/files.sqlite3`, `audit.csv`, `relations.csv`, `summary.json`: 수정된 실행 결과.

```sh
python3 Role03/file_db.py
python3 Role03/audit_results.py
python3 -m unittest discover -s Role03 -p 'test_*.py' -v
```

`file_db.py`와 테스트는 Python 기본 라이브러리만 사용한다. 점검 코드의 PDF 재검사에만 Python 라이브러리 PyMuPDF가 선택적으로 필요하다. 미설치 환경에서는 `pdf_inspection_unavailable`로 표시하며 OCR 필요를 확정하지 않는다. 이번에는 PyMuPDF가 있는 환경에서 6개를 모두 검사했다.

Role01 코드, 원본 파일, 입력 CSV는 수정하지 않았다. 기존 `WEEK06_REPORT.md`, `REFERENCE_CHECK_REPORT.md`, `source_checks.json`은 이전 시점 기록이며 최신 상태는 이 보고서와 새 출력 파일을 기준으로 확인한다. GitHub 업로드는 수행하지 않았다.
