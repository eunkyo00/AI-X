"""자료 유형(role) 분류기에 공통으로 사용하는 설정과 변환 함수."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Mapping

from project_classifier import FileText


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ARTIFACT_DIR = BASE_DIR / "role_classifier_artifacts"
DEFAULT_MODEL_PATH = DEFAULT_ARTIFACT_DIR / "role_classifier.joblib"

# 현재 데이터의 세부 role을 사용자 검색에 적합한 6개 유형으로 통일한다.
ROLE_NORMALIZATION = {
    "강의자료": "강의자료",
    "코드": "코드",
    "과제 안내": "과제",
    "과제 실습": "과제",
    "실습 데이터": "데이터",
    "시각화 입력 데이터": "데이터",
    "분석 입력 데이터": "데이터",
    "전처리 입력 데이터": "데이터",
    "지역 조회 데이터": "데이터",
    "실습 시작 틀": "실습자료",
    "실습 풀이": "실습자료",
    "실습 예제": "실습자료",
    "분석 예제": "실습자료",
    "단원 안내": "안내자료",
    "실행 안내": "안내자료",
}


def normalize_role(value: object) -> str:
    return ROLE_NORMALIZATION.get(str(value or "").strip(), "")


def row_to_role_file_text(row: Mapping[str, object]) -> FileText:
    """role과 role 표현이 섞인 수동 description을 제외한 모델 입력."""
    filename = str(row.get("filename", "") or "").strip()
    extension = str(row.get("extension", "") or "").strip()
    extracted_text = str(row.get("extracted_text", "") or "").strip()
    return FileText(
        filename=filename,
        extension=extension,
        description="",
        extracted_text=extracted_text,
    )


def recognize_role_by_rule(record: FileText) -> tuple[str, str] | None:
    """파일명·확장자에 정답이 명시된 경우만 확정 규칙을 적용한다."""
    filename = record.filename.strip().lower()
    extension = (record.extension or Path(filename).suffix).strip().lower()

    if re.search(r"과제|assignment|homework", filename) or re.search(
        r"(?:^|[_\-\s])home(?:[_\-\s.]|$)", filename
    ):
        return "과제", "filename:assignment"
    if re.search(r"강의\s*자료|lecture", filename):
        return "강의자료", "filename:lecture"
    if extension in {".csv", ".tsv", ".json", ".xlsx", ".xls", ".parquet", ".db"}:
        return "데이터", f"extension:{extension}"
    if extension in {".py", ".r", ".js", ".ts", ".java", ".c", ".cpp"}:
        return "코드", f"extension:{extension}"
    return None
