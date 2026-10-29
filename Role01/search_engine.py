"""파일 단위 의미 검색 엔진.

기존 search_model_modified.py의 검색 로직을 API에서 재사용하도록 분리.
평가 및 대화형 입력은 포함하지 않으며 문서 임베딩은 디스크에 캐싱한다.
"""
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent
TEXT_CSV = BASE_DIR / "extracted_text.csv"
METADATA_CSV = BASE_DIR / "metadata.csv"
MODEL_NAME = "intfloat/multilingual-e5-small"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80
TOP_K = 5


def normalize_filename(filename):
    """경로가 포함되어도 파일명만 비교하고 대소문자를 통일한다."""
    filename = str(filename).strip().replace("\\", "/")
    return filename.split("/")[-1].casefold()


def split_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """긴 텍스트를 겹치는 구간이 있는 여러 조각으로 나눈다."""
    text = str(text).strip()
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size는 1 이상이어야 합니다.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap은 0 이상이고 chunk_size보다 작아야 합니다.")
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


class SearchEngine:
    """최초 생성 시 CSV를 읽고 임베딩 캐시를 로딩하거나 생성한다."""

    def __init__(self, text_csv=TEXT_CSV, metadata_csv=METADATA_CSV,
                 model_name=MODEL_NAME):
        text_csv = Path(text_csv)
        metadata_csv = Path(metadata_csv)
        if not text_csv.exists():
            raise FileNotFoundError(f"텍스트 추출 파일을 찾을 수 없습니다: {text_csv}")

        df = pd.read_csv(text_csv, dtype=str, keep_default_na=False,
                         encoding="utf-8-sig")
        required_columns = {"file_id", "filename", "extracted_text"}
        if not required_columns.issubset(df.columns):
            raise ValueError(
                f"필요한 열: {required_columns}\n현재 열: {list(df.columns)}"
            )

        if metadata_csv.exists():
            metadata = pd.read_csv(metadata_csv, dtype=str,
                                   keep_default_na=False, encoding="utf-8-sig")
            if "file_id" in metadata.columns:
                metadata = metadata.drop_duplicates(subset=["file_id"], keep="first")
                extra_columns = [
                    col for col in metadata.columns
                    if col not in df.columns and col != "file_id"
                ]
                if extra_columns:
                    df = df.merge(metadata[["file_id"] + extra_columns],
                                  on="file_id", how="left")

        df = df[
            df["file_id"].astype(str).str.strip().ne("")
            & df["filename"].astype(str).str.strip().ne("")
            & df["extracted_text"].astype(str).str.strip().ne("")
        ].copy()
        df = df.drop_duplicates(subset=["file_id"], keep="first").reset_index(drop=True)
        if df.empty:
            raise ValueError("검색할 텍스트가 없습니다.")
        for column in ("project", "role", "path"):
            if column not in df.columns:
                df[column] = ""
        df[["project", "role", "path"]] = df[["project", "role", "path"]].fillna("")

        self.df = df
        self.documents = []
        self.chunk_info = []
        for _, row in df.iterrows():
            for chunk_number, chunk in enumerate(split_text(row["extracted_text"])):
                self.documents.append(
                    f"파일명: {row['filename']}\n"
                    f"프로젝트: {row['project']}\n"
                    f"파일 역할: {row['role']}\n"
                    f"파일 내용:\n{chunk}"
                )
                self.chunk_info.append({
                    "file_id": row["file_id"],
                    "filename": row["filename"],
                    "path": row["path"],
                    "chunk_number": chunk_number,
                    "chunk_text": chunk,
                })

        print(f"검색 대상 파일 수: {len(df)}")
        print(f"검색 텍스트 조각 수: {len(self.documents)}")
        print("임베딩 모델을 불러오는 중...")
        self.model = SentenceTransformer(model_name)

        # 검색 문서가 바뀌면 캐시 키도 달라지도록 실제 입력 문자열을 해시한다.
        passages = ["passage: " + text for text in self.documents]
        hasher = hashlib.sha256()
        hasher.update(model_name.encode("utf-8"))
        for passage in passages:
            encoded = passage.encode("utf-8")
            hasher.update(len(encoded).to_bytes(8, "big"))
            hasher.update(encoded)

        cache_key = hasher.hexdigest()[:16]
        cache_dir = BASE_DIR / "embedding_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"embeddings_{cache_key}.npy"

        if cache_path.exists():
            print("저장된 임베딩 불러오는 중...")
            self.document_embeddings = np.load(cache_path, allow_pickle=False)
            if self.document_embeddings.ndim != 2 or self.document_embeddings.shape[0] != len(passages):
                raise ValueError("임베딩 캐시 크기가 검색 문서와 맞지 않습니다. 캐시 파일을 삭제하고 재실행하세요.")
            print("임베딩 캐시 로딩 완료!")
        else:
            print("파일 내용을 숫자 벡터로 변환하는 중...")
            self.document_embeddings = self.model.encode(
                passages,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=True,
            )
            np.save(cache_path, self.document_embeddings)
            print("임베딩 계산 및 저장 완료!")

    def search_files(self, query, top_k=TOP_K):
        """검색어와 청크 유사도를 계산해 파일 단위 Top K를 반환한다."""
        query = str(query).strip()
        if not query or top_k <= 0:
            return []

        query_embedding = self.model.encode(
            ["query: " + query],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0]
        scores = self.document_embeddings @ query_embedding

        best_results = {}
        for index, score in enumerate(scores):
            info = self.chunk_info[index]
            file_id = info["file_id"]
            if file_id not in best_results or score > best_results[file_id]["score"]:
                best_results[file_id] = {**info, "score": float(score)}

        ranked_results = sorted(
            best_results.values(), key=lambda result: result["score"], reverse=True
        )
        return ranked_results[:top_k]


_engine = None


def get_engine():
    """최초 호출 시 한 번만 엔진을 만들고 재사용한다(단일 프로세스 기준)."""
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine


def search_files(query, top_k=TOP_K):
    """백엔드에서 바로 호출할 수 있는 인터페이스."""
    return get_engine().search_files(query, top_k=top_k)


if __name__ == "__main__":
    results = search_files("SARIMA 예측 코드", top_k=5)
    for rank, result in enumerate(results, 1):
        print(f"{rank}. {result['filename']} ({result['file_id']}): {result['score']:.4f}")
