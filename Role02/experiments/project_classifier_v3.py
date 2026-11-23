"""프로젝트 분류기 v3의 임베딩과 새 프로젝트 판정 유틸리티."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_CSV = BASE_DIR.parent / "Role01" / "extracted_text.csv"
GENERATED_DESCRIPTION_CSV = BASE_DIR / "metadata_description_generated.csv"
MERGED_DESCRIPTION_CSV = BASE_DIR / "metadata_description_merged.csv"
DEFAULT_DESCRIPTION_CSV = (
    GENERATED_DESCRIPTION_CSV
    if GENERATED_DESCRIPTION_CSV.exists()
    else MERGED_DESCRIPTION_CSV
)
DEFAULT_ARTIFACT_DIR = BASE_DIR / "project_classifier_artifacts_v3"
DEFAULT_MODEL_PATH = DEFAULT_ARTIFACT_DIR / "project_classifier_v3.joblib"

MODEL_NAME = "intfloat/multilingual-e5-small"
CHUNK_CHARS = 1_200
MAX_CHUNKS = 4
VIEW_WEIGHTS = {
    "content": 0.50,
    "description": 0.40,
    "filename": 0.10,
}


@dataclass(frozen=True)
class FileText:
    """분류할 파일 한 개에서 프로젝트 정답을 제외한 입력 정보."""

    filename: str
    extracted_text: str = ""
    description: str = ""
    extension: str = ""


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def row_to_file_text(row: Mapping[str, object]) -> FileText:
    return FileText(
        filename=clean_text(row.get("filename", "")),
        extracted_text=clean_text(row.get("extracted_text", "")),
        description=clean_text(row.get("description", "")),
        extension=clean_text(row.get("extension", "")),
    )


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    """행별 L2 정규화. 0 벡터는 그대로 둔다."""
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.clip(norms, 1e-12, None)


def select_text_chunks(
    text: str,
    chunk_chars: int = CHUNK_CHARS,
    max_chunks: int = MAX_CHUNKS,
) -> list[str]:
    """문서 전체를 반영하도록 앞·중간·뒤에서 고르게 텍스트를 선택한다."""
    text = clean_text(text)
    if not text:
        return []
    if chunk_chars <= 0 or max_chunks <= 0:
        raise ValueError("chunk_chars와 max_chunks는 1 이상이어야 합니다.")
    if len(text) <= chunk_chars:
        return [text]

    starts = np.linspace(0, len(text) - chunk_chars, num=max_chunks, dtype=int)
    chunks: list[str] = []
    seen: set[str] = set()
    for start in starts:
        chunk = text[int(start): int(start) + chunk_chars].strip()
        if chunk and chunk not in seen:
            chunks.append(chunk)
            seen.add(chunk)
    return chunks


def build_content_passages(
    record: FileText,
    chunk_chars: int = CHUNK_CHARS,
    max_chunks: int = MAX_CHUNKS,
) -> list[str]:
    header = f"파일명: {record.filename}\n확장자: {record.extension}\n"
    chunks = select_text_chunks(record.extracted_text, chunk_chars, max_chunks)
    if not chunks:
        return ["passage: " + header + "파일 내용 없음"]
    return ["passage: " + header + f"파일 내용:\n{chunk}" for chunk in chunks]


def _encode_content_view(
    model,
    records: list[FileText],
    chunk_chars: int,
    max_chunks: int,
    batch_size: int,
    show_progress_bar: bool,
) -> np.ndarray:
    passages: list[str] = []
    spans: list[tuple[int, int]] = []
    for record in records:
        record_passages = build_content_passages(record, chunk_chars, max_chunks)
        start = len(passages)
        passages.extend(record_passages)
        spans.append((start, len(passages)))

    passage_vectors = model.encode(
        passages,
        normalize_embeddings=True,
        convert_to_numpy=True,
        batch_size=batch_size,
        show_progress_bar=show_progress_bar,
    )
    vectors = [passage_vectors[start:end].mean(axis=0) for start, end in spans]
    return normalize_rows(np.stack(vectors))


def encode_file_texts(
    model,
    records: Iterable[FileText],
    *,
    chunk_chars: int = CHUNK_CHARS,
    max_chunks: int = MAX_CHUNKS,
    view_weights: Mapping[str, float] = VIEW_WEIGHTS,
    batch_size: int = 32,
    show_progress_bar: bool = True,
) -> np.ndarray:
    """본문·설명·파일명을 따로 임베딩한 뒤 가중 결합한다."""
    record_list = list(records)
    if not record_list:
        raise ValueError("임베딩할 파일이 없습니다.")
    missing_weights = set(VIEW_WEIGHTS) - set(view_weights)
    if missing_weights:
        raise ValueError(f"뷰 가중치가 없습니다: {sorted(missing_weights)}")

    content = _encode_content_view(
        model,
        record_list,
        chunk_chars,
        max_chunks,
        batch_size,
        show_progress_bar,
    )
    descriptions = model.encode(
        [f"passage: 파일 설명: {record.description}" for record in record_list],
        normalize_embeddings=True,
        convert_to_numpy=True,
        batch_size=batch_size,
        show_progress_bar=show_progress_bar,
    )
    filenames = model.encode(
        [f"passage: 파일명: {record.filename}" for record in record_list],
        normalize_embeddings=True,
        convert_to_numpy=True,
        batch_size=batch_size,
        show_progress_bar=show_progress_bar,
    )
    combined = np.concatenate(
        [
            float(view_weights["content"]) * content,
            float(view_weights["description"]) * descriptions,
            float(view_weights["filename"]) * filenames,
        ],
        axis=1,
    )
    return normalize_rows(combined)


def score_embeddings(
    artifact: Mapping[str, object],
    embeddings: np.ndarray,
) -> dict[str, np.ndarray]:
    """기존 프로젝트 또는 ``새 과목``으로 자동 판정한다."""
    classifier = artifact["classifier"]
    centroids = np.asarray(artifact["class_centroids"], dtype=np.float32)
    thresholds = artifact["open_set_thresholds"]

    probabilities = classifier.predict_proba(embeddings)
    probability_order = np.argsort(probabilities, axis=1)[:, ::-1]
    best = probability_order[:, 0]
    second = probability_order[:, 1]
    rows = np.arange(len(embeddings))
    closest = classifier.classes_[best]
    confidence = probabilities[rows, best]
    probability_margin = confidence - probabilities[rows, second]

    similarities = embeddings @ centroids.T
    similarity_order = np.argsort(similarities, axis=1)[:, ::-1]
    similarity_best = similarity_order[:, 0]
    centroid_project = classifier.classes_[similarity_best]
    centroid_similarity = similarities[rows, similarity_best]
    centroid_margin = (
        centroid_similarity - similarities[rows, similarity_order[:, 1]]
    )

    checks = {
        "model_agreement": closest == centroid_project,
        "confidence": confidence >= float(thresholds["confidence"]),
        "probability_margin": probability_margin
        >= float(thresholds["probability_margin"]),
        "centroid_similarity": centroid_similarity
        >= float(thresholds["centroid_similarity"]),
        "centroid_margin": centroid_margin
        >= float(thresholds["centroid_margin"]),
    }
    accepted = np.logical_and.reduce(list(checks.values()))
    predicted = np.where(accepted, closest, "새 과목")
    return {
        "predicted_project": predicted,
        "closest_existing_project": closest,
        "centroid_project": centroid_project,
        "confidence": confidence,
        "probability_margin": probability_margin,
        "centroid_similarity": centroid_similarity,
        "centroid_margin": centroid_margin,
        "accepted_as_existing": accepted,
        **{f"check_{name}": value for name, value in checks.items()},
        "probabilities": probabilities,
    }


