"""프로젝트(과목) 분류기에 공통으로 사용하는 임베딩 유틸리티v2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_CSV = BASE_DIR.parent / "Role01" / "extracted_text.csv"
DEFAULT_ARTIFACT_DIR = BASE_DIR / "project_classifier_artifacts"
DEFAULT_MODEL_PATH = DEFAULT_ARTIFACT_DIR / "project_classifier.joblib"
MODEL_NAME = "intfloat/multilingual-e5-small"
CHUNK_CHARS = 1_200
MAX_CHUNKS = 4


@dataclass(frozen=True)
class FileText:
    """분류할 파일 한 개의 텍스트 정보."""

    filename: str
    extracted_text: str = ""
    description: str = ""
    extension: str = ""


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def row_to_file_text(row: Mapping[str, object]) -> FileText:
    """CSV 행을 프로젝트 라벨이 포함되지 않은 모델 입력으로 변환한다."""
    return FileText(
        filename=_clean(row.get("filename", "")),
        extracted_text=_clean(row.get("extracted_text", "")),
        description=_clean(row.get("description", "")),
        extension=_clean(row.get("extension", "")),
    )


def select_text_chunks(
    text: str,
    chunk_chars: int = CHUNK_CHARS,
    max_chunks: int = MAX_CHUNKS,
) -> list[str]:
    """문서의 처음부터 끝까지 고르게 최대 ``max_chunks``개를 선택한다."""
    text = _clean(text)
    if not text:
        return []
    if chunk_chars <= 0 or max_chunks <= 0:
        raise ValueError("chunk_chars와 max_chunks는 1 이상이어야 합니다.")
    if len(text) <= chunk_chars:
        return [text]

    last_start = max(0, len(text) - chunk_chars)
    starts = np.linspace(0, last_start, num=max_chunks, dtype=int)
    chunks: list[str] = []
    seen: set[str] = set()
    for start in starts:
        chunk = text[int(start): int(start) + chunk_chars].strip()
        if chunk and chunk not in seen:
            chunks.append(chunk)
            seen.add(chunk)
    return chunks


def build_passages(
    file_text: FileText,
    chunk_chars: int = CHUNK_CHARS,
    max_chunks: int = MAX_CHUNKS,
) -> list[str]:

    # description은 사용하지 않음
    header = (
        f"파일명: {file_text.filename}\n"
        f"확장자: {file_text.extension}\n"
    )

    # 본문을 청크로 나누기
    chunks = select_text_chunks(
        file_text.extracted_text,
        chunk_chars=chunk_chars,
        max_chunks=max_chunks,
    )

    passages = []

    for chunk in chunks:
        passage = (
            "passage: "
            + header
            + f"파일 내용:\n{chunk}"
        )
        passages.append(passage)

    return passages

def encode_file_texts(
    model,
    records: Iterable[FileText],
    chunk_chars: int = CHUNK_CHARS,
    max_chunks: int = MAX_CHUNKS,
    batch_size: int = 32,
    show_progress_bar: bool = True,
) -> np.ndarray:
    """파일별 여러 청크를 임베딩한 뒤 평균하여 파일 벡터 하나로 만든다."""
    record_list = list(records)
    all_passages: list[str] = []
    spans: list[tuple[int, int]] = []
    for record in record_list:
        passages = build_passages(
            record,
            chunk_chars=chunk_chars,
            max_chunks=max_chunks,
        )
        start = len(all_passages)
        all_passages.extend(passages)
        spans.append((start, len(all_passages)))

    if not all_passages:
        raise ValueError("임베딩할 파일 텍스트가 없습니다.")

    passage_embeddings = model.encode(
        all_passages,
        normalize_embeddings=True,
        convert_to_numpy=True,
        batch_size=batch_size,
        show_progress_bar=show_progress_bar,
    )

    file_embeddings = []
    for start, end in spans:
        vector = passage_embeddings[start:end].mean(axis=0)
        norm = np.linalg.norm(vector)
        if norm:
            vector = vector / norm
        file_embeddings.append(vector.astype(np.float32, copy=False))
    return np.stack(file_embeddings)