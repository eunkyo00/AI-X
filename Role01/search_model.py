from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer


# 1. 파일 경로 설정
BASE_DIR = Path(__file__).resolve().parent

TEXT_CSV = BASE_DIR / "extracted_text.csv"
METADATA_CSV = BASE_DIR / "metadata.csv"

MODEL_NAME = "intfloat/multilingual-e5-small"

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

df = df.reset_index(drop=True)

if df.empty:
    raise ValueError("검색할 텍스트가 없습니다.")

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
    path = row.get("path", "")

    chunks = split_text(content)

    for chunk_number, chunk in enumerate(chunks):

        # 파일 정보와 내부 내용을 함께 검색 대상으로 구성
        document_text = (
            f"파일명: {filename}\n"
            f"프로젝트: {project}\n"
            f"파일 역할: {role}\n"
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

model = SentenceTransformer(MODEL_NAME)


# 5. 파일 내용 임베딩
print("\n파일 내용을 숫자 벡터로 변환하는 중...")

document_embeddings = model.encode(
    ["passage: " + text for text in documents],
    normalize_embeddings=True,
    convert_to_numpy=True,
    show_progress_bar=True
)

print("파일 임베딩 완료!")


# 6. 검색어 입력 및 검색
print("\n검색을 시작할 수 있습니다.")
print("종료하려면 q를 입력하세요.")

while True:

    query = input("\n검색어: ").strip()

    if query.lower() == "q":
        print("검색을 종료합니다.")
        break

    if not query:
        print("검색어를 입력해 주세요.")
        continue

    # 검색어도 동일한 임베딩 모델로 변환
    query_embedding = model.encode(
        ["query: " + query],
        normalize_embeddings=True,
        convert_to_numpy=True
    )[0]

    # 벡터 간 유사도 계산
    scores = document_embeddings @ query_embedding

    # 파일 하나에 여러 텍스트 조각이 있다면
    # 그중 가장 높은 점수를 해당 파일의 점수로 사용
    best_results = {}

    for index, score in enumerate(scores):

        info = chunk_info[index]
        file_id = info["file_id"]

        if (
            file_id not in best_results
            or score > best_results[file_id]["score"]
        ):
            best_results[file_id] = {
                **info,
                "score": float(score)
            }

    # 점수가 높은 순서로 정렬
    ranked_results = sorted(
        best_results.values(),
        key=lambda result: result["score"],
        reverse=True
    )

    print("\n===== 검색 결과 Top 5 =====")

    for rank, result in enumerate(ranked_results[:5], start=1):

        print(f"\n[{rank}위] {result['filename']}")
        print(f"파일 ID: {result['file_id']}")
        print(f"유사도 점수: {result['score']:.4f}")

        if result["path"]:
            print(f"경로: {result['path']}")

        preview = (
            result["chunk_text"]
            .replace("\n", " ")
            .strip()
        )

        print(f"관련 내용: {preview[:200]}")