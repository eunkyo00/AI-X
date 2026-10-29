from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
MODEL_NAME = "intfloat/multilingual-e5-small"


def load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def signature(text_csv, metadata_csv):
    digest = hashlib.sha256(MODEL_NAME.encode())
    for path in (text_csv, metadata_csv):
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def build_index(text_csv, metadata_csv, output, encoder=None):
    TEXT_CSV, METADATA_CSV = Path(text_csv), Path(metadata_csv)
    # 2. CSV 읽기
    if not TEXT_CSV.exists():
        raise FileNotFoundError(
            f"텍스트 추출 파일을 찾을 수 없습니다: {TEXT_CSV}"
        )

    df = pd.read_csv(
        TEXT_CSV,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig"
    )

    required_columns = {
        "file_id",
        "filename",
        "extracted_text"
    }

    if not required_columns.issubset(df.columns):
        raise ValueError(
            f"필요한 열: {required_columns}\n"
            f"현재 열: {list(df.columns)}"
        )


    # metadata.csv에만 있는 정보도 가져오기
    if METADATA_CSV.exists():

        metadata = pd.read_csv(
            METADATA_CSV,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig"
        )

        if "file_id" in metadata.columns:

            extra_columns = [
                col for col in metadata.columns
                if col not in df.columns and col != "file_id"
            ]

            if extra_columns:
                df = df.merge(
                    metadata[["file_id"] + extra_columns],
                    on="file_id",
                    how="left"
                )


    # 추출에 성공한 텍스트가 있는 파일만 사용
    df = df[
        df["extracted_text"].astype(str).str.strip().ne("")
    ].copy()

    df = df.sort_values("file_id").reset_index(drop=True)



    # 3. 긴 파일을 작은 조각으로 나누기
    def split_text(text, chunk_size=500, overlap=80):
        """
        긴 텍스트를 여러 조각으로 나눈다.
        overlap은 앞뒤 조각이 조금씩 겹치도록 하는 길이다.
        """

        text = str(text).strip()

        if not text:
            return []

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


    # 파일별 텍스트와 메타데이터 준비
    documents = []
    chunk_info = []

    for _, row in df.iterrows():

        filename = row["filename"]
        file_id = row["file_id"]
        content = row["extracted_text"]

        project = row.get("project", "")
        role = row.get("role", "")
        description = row.get("description", "")
        path = row.get("path", "")

        chunks = split_text(content)

        for chunk_number, chunk in enumerate(chunks):

            # 파일 정보와 내부 내용을 함께 검색 대상으로 구성
            document_text = (
                f"파일명: {filename}\n"
                f"프로젝트: {project}\n"
                f"파일 역할: {role}\n"
                f"파일 설명: {description}\n"
                f"파일 내용:\n{chunk}"
            )

            documents.append(document_text)

            chunk_info.append({
                "file_id": file_id,
                "filename": filename,
                "path": path,
                "chunk_number": chunk_number,
                "chunk_text": chunk
            })


    print(f"검색 대상 파일 수: {len(df)}")
    print(f"검색 텍스트 조각 수: {len(documents)}")

    # 4. 임베딩 모델 불러오기
    print("\n임베딩 모델을 불러오는 중...")

    model = encoder


    # 5. 파일 내용 임베딩
    print("\n파일 내용을 숫자 벡터로 변환하는 중...")

    passages = ["passage: " + text for text in documents]
    legacy_digest = hashlib.sha256(MODEL_NAME.encode())
    for passage in passages:
        encoded = passage.encode("utf-8")
        legacy_digest.update(len(encoded).to_bytes(8, "big"))
        legacy_digest.update(encoded)
    legacy_cache = BASE_DIR / "embedding_cache" / f"embeddings_{legacy_digest.hexdigest()[:16]}.npy"
    if legacy_cache.is_file():
        print("기존 검색 캐시 재사용")
        document_embeddings = np.load(legacy_cache, allow_pickle=False)
        if document_embeddings.ndim != 2 or len(document_embeddings) != len(documents):
            raise ValueError("기존 검색 캐시와 본문 수가 다릅니다.")
    else:
        if model is None and documents:
            model = load_model()
        document_embeddings = (model.encode(
            ["passage: " + text for text in documents],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True
        ) if documents else np.empty((0, 0)))

    print("파일 임베딩 완료!")



    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output / "embeddings.npz", embeddings=document_embeddings)
    (output / "index.json").write_text(json.dumps({
        "signature": signature(TEXT_CSV, METADATA_CSV),
        "model": MODEL_NAME, "chunks": chunk_info,
    }, ensure_ascii=False), encoding="utf-8")


def load_index(directory):
    directory = Path(directory)
    info = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    with np.load(directory / "embeddings.npz", allow_pickle=False) as data:
        embeddings = data["embeddings"].copy()
    if len(info["chunks"]) != len(embeddings):
        raise ValueError("검색 인덱스의 본문과 벡터 수가 다릅니다.")
    return info, embeddings


class SearchEngine:
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
            except (FileNotFoundError, ValueError):
                info = {}
            if info.get("signature") != current:
                build_index(text_csv, metadata_csv, directory, encoder=self.model)
                info, embeddings = load_index(directory)
            self.info, self.embeddings = info, embeddings
            self.loaded_signature = current
        if not self.info["chunks"]:
            return []
        query_embedding = self.model.encode(["query: " + query], normalize_embeddings=True,
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
            print(result['chunk_text'].replace("\n", " ")[:200])


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-index", action="store_true")
    args = parser.parse_args()
    if args.build_index:
        build_index(BASE_DIR / "extracted_text.csv", BASE_DIR / "metadata.csv", BASE_DIR / "search_index")
    else:
        main()
