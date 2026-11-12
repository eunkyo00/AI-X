"""파일별 임베딩 캐시를 사용해 검색 인덱스를 증분 갱신한다.

실행: python refresh_search.py --build-index
기존 search_index/index.json 및 embeddings.npz 출력 형식 유지.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import tempfile

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
MODEL_NAME = "intfloat/multilingual-e5-small"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80


def load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def signature(text_csv, metadata_csv):
    """기존 검색 인덱스와 호환되는 입력 해시."""
    digest = hashlib.sha256(MODEL_NAME.encode())
    for path in (text_csv, metadata_csv):
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def split_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    text = str(text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def read_documents(text_csv, metadata_csv):
    df = pd.read_csv(text_csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = {"file_id", "filename", "extracted_text"}
    if not required.issubset(df.columns):
        raise ValueError(f"extracted_text.csv 누락 열: {required - set(df.columns)}")

    # 메타데이터가 있으면 해당 값으로 갱신한다. 파일명과 본문은 추출 CSV 기준.
    if Path(metadata_csv).exists():
        metadata = pd.read_csv(metadata_csv, dtype=str, keep_default_na=False,
                               encoding="utf-8-sig")
        if "file_id" not in metadata.columns:
            raise ValueError("metadata.csv에 file_id 열이 없습니다.")
        metadata = metadata.drop_duplicates("file_id", keep="first")
        columns = [c for c in metadata.columns
                   if c not in ("file_id", "filename", "extracted_text")]
        df = df.drop(columns=columns, errors="ignore")
        df = df.merge(metadata[["file_id"] + columns], on="file_id", how="left")
        for column in columns:
            df[column] = df[column].fillna("")

    # Role02의 생성 설명을 우선 반영한다. 수동 설명도 이 CSV에 보존되어 있다.
    generated = Path(metadata_csv).parent.parent / "Role02" / "metadata_description_generated.csv"
    if generated.is_file():
        descriptions = pd.read_csv(generated, dtype=str, keep_default_na=False,
                                   encoding="utf-8-sig")
        if {"file_id", "description"}.issubset(descriptions.columns):
            lookup = descriptions.drop_duplicates("file_id").set_index("file_id")["description"]
            if "description" not in df.columns:
                df["description"] = ""
            proposed = df["file_id"].map(lookup).fillna("")
            df["description"] = proposed.where(proposed.str.strip().ne(""), df["description"])

    df = df[df["file_id"].str.strip().ne("") &
            df["filename"].str.strip().ne("") &
            df["extracted_text"].str.strip().ne("")].copy()
    df = df.drop_duplicates("file_id").sort_values("file_id").reset_index(drop=True)
    for column in ("project", "role", "description", "path"):
        if column not in df.columns:
            df[column] = ""
        df[column] = df[column].fillna("")
    return df


def build_index(text_csv, metadata_csv, output, encoder=None):
    text_csv, metadata_csv, output = map(Path, (text_csv, metadata_csv, output))
    if not text_csv.is_file():
        raise FileNotFoundError(text_csv)
    df = read_documents(text_csv, metadata_csv)

    # 파일 단위로 청크를 모아 두면 파일 하나만 바뀌어도 나머지는 재사용 가능.
    groups = []
    chunk_info = []
    for _, row in df.iterrows():
        passages = []
        for number, chunk in enumerate(split_text(row["extracted_text"])):
            document = (f"파일명: {row['filename']}\n"
                        f"프로젝트: {row['project']}\n"
                        f"파일 역할: {row['role']}\n"
                        f"파일 설명: {row['description']}\n"
                        f"파일 내용:\n{chunk}")
            passages.append("passage: " + document)
            chunk_info.append({"file_id": row["file_id"],
                               "filename": row["filename"], "path": row["path"],
                               "chunk_number": number, "chunk_text": chunk})
        if passages:
            groups.append((row["file_id"], passages))

    print(f"검색 대상 파일 수: {len(df)}")
    print(f"검색 텍스트 조각 수: {len(chunk_info)}")

    # 모델명과 파일별 실제 임베딩 입력으로 캐시를 구분한다.
    # 파일 ID를 포함하므로 다른 파일의 캐시와 섞이지 않는다.
    cache_dir = BASE_DIR / "embedding_cache" / "per_file"
    cache_dir.mkdir(parents=True, exist_ok=True)
    vectors = []
    reused = updated = 0
    model = encoder
    for file_id, passages in groups:
        digest = hashlib.sha256()
        digest.update(MODEL_NAME.encode("utf-8"))
        digest.update(file_id.encode("utf-8"))
        for passage in passages:
            raw = passage.encode("utf-8")
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
        key = digest.hexdigest()
        # 파일 ID가 변경되더라도 파일명에 특수문자가 들어가지 않게 해시만 사용.
        cache_file = cache_dir / f"{key}.npy"
        cached = None
        if cache_file.exists():
            try:
                cached = np.load(cache_file, allow_pickle=False)
                if cached.ndim != 2 or cached.shape[0] != len(passages):
                    cached = None
            except (OSError, ValueError):
                cached = None
        if cached is not None:
            vectors.append(cached)
            reused += 1
            continue
        if model is None:
            print("임베딩 모델을 불러오는 중...")
            model = load_model()
        print(f"{file_id}: 임베딩 생성 ({len(passages)}개 청크)", flush=True)
        embedded = np.asarray(model.encode(passages, normalize_embeddings=True,
                                           convert_to_numpy=True,
                                           show_progress_bar=False))
        if embedded.ndim != 2 or embedded.shape[0] != len(passages):
            raise ValueError(f"{file_id}: 모델 출력의 차원이 올바르지 않습니다.")
        # 계산 중 종료되어도 깨진 캐시를 남기지 않도록 임시 파일로 저장.
        with tempfile.NamedTemporaryFile(dir=cache_dir, suffix=".npy", delete=False) as tmp:
            temporary = Path(tmp.name)
        try:
            np.save(temporary, embedded)
            os.replace(temporary, cache_file)
        finally:
            temporary.unlink(missing_ok=True)
        vectors.append(embedded)
        updated += 1

    if not vectors:
        raise ValueError("임베딩할 문서가 없습니다.")
    document_embeddings = np.concatenate(vectors, axis=0)
    if len(document_embeddings) != len(chunk_info):
        raise ValueError("청크와 임베딩 개수가 일치하지 않습니다.")

    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output / "embeddings.npz", embeddings=document_embeddings)
    (output / "index.json").write_text(json.dumps({
        "signature": signature(text_csv, metadata_csv),
        "model": MODEL_NAME,
        "chunks": chunk_info,
    }, ensure_ascii=False), encoding="utf-8")
    print(f"기존 임베딩 재사용: {reused}개 파일")
    print(f"새로 임베딩: {updated}개 파일")
    print(f"검색 인덱스 저장 완료: {output}")


def load_index(directory):
    directory = Path(directory)
    info = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    with np.load(directory / "embeddings.npz", allow_pickle=False) as data:
        embeddings = data["embeddings"].copy()
    if len(info["chunks"]) != len(embeddings):
        raise ValueError("검색 인덱스의 본문과 벡터 수가 다릅니다.")
    return info, embeddings


class SearchEngine:
    """기존 refresh_search.py의 간단한 검색 인터페이스."""
    def __init__(self):
        self.model = load_model()
        self.loaded_signature = None

    def search(self, query, top_k=5):
        if (BASE_DIR.parent / ".update-data.lock").exists():
            raise RuntimeError("데이터 갱신 중입니다. 완료 후 다시 검색하세요.")
        text_csv = BASE_DIR / "extracted_text.csv"
        metadata_csv = BASE_DIR / "metadata.csv"
        directory = BASE_DIR / "search_index"
        current = signature(text_csv, metadata_csv)
        if self.loaded_signature != current:
            try:
                info, embeddings = load_index(directory)
            except (FileNotFoundError, ValueError, KeyError):
                info = {}
            if info.get("signature") != current:
                build_index(text_csv, metadata_csv, directory, encoder=self.model)
                info, embeddings = load_index(directory)
            self.info, self.embeddings = info, embeddings
            self.loaded_signature = current
        if not self.info["chunks"]:
            return []
        query_embedding = self.model.encode(["query: " + query],
                                            normalize_embeddings=True,
                                            convert_to_numpy=True)[0]
        scores = self.embeddings @ query_embedding
        best = {}
        for chunk, score in zip(self.info["chunks"], scores):
            if chunk["file_id"] not in best or score > best[chunk["file_id"]]["score"]:
                best[chunk["file_id"]] = dict(chunk, score=float(score))
        return sorted(best.values(), key=lambda r: r["score"], reverse=True)[:top_k]


_engine = None


def search_files(query, top_k=5):
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine.search(query, top_k)


def main():
    print("검색어를 입력하세요. 종료: q")
    while True:
        query = input("\n검색어: ").strip()
        if query.lower() == "q":
            break
        if not query:
            continue
        try:
            results = search_files(query)
        except RuntimeError as error:
            print(error)
            continue
        for rank, result in enumerate(results, 1):
            print(f"\n[{rank}위] {result['filename']} ({result['file_id']}) — {result['score']:.4f}")
            print(f"경로: {result['path']}")
            print(result["chunk_text"].replace("\n", " ")[:200])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-index", action="store_true")
    args = parser.parse_args()
    if args.build_index:
        build_index(BASE_DIR / "extracted_text.csv", BASE_DIR / "metadata.csv",
                    BASE_DIR / "search_index")
    else:
        main()
