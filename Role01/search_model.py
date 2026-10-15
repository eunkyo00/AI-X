from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer


# 1. 파일 경로 설정
BASE_DIR = Path(__file__).resolve().parent

TEXT_CSV = BASE_DIR / "extracted_text.csv"
METADATA_CSV = BASE_DIR / "metadata.csv"

EVALUATION_CSV = BASE_DIR / "evaluation_queries.csv"
RESULTS_CSV = BASE_DIR / "evaluation_results.csv"

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


# 6. 검색 기능을 함수로 만들기

def search_files(query, top_k=5):
    """
    검색어를 입력받아 관련 파일을 점수순으로 반환한다.
    기존 검색 방식을 그대로 사용한다.
    """

    # 검색어를 임베딩 벡터로 변환
    query_embedding = model.encode(
        ["query: " + query],
        normalize_embeddings=True,
        convert_to_numpy=True
    )[0]

    # 파일 텍스트 조각과 검색어 사이의 유사도 계산
    scores = document_embeddings @ query_embedding

    # 같은 파일에 속한 여러 조각 중 가장 높은 점수 사용
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

    # 유사도 점수가 높은 순서대로 정렬
    ranked_results = sorted(
        best_results.values(),
        key=lambda result: result["score"],
        reverse=True
    )

    return ranked_results[:top_k]


# 7. 평가용 CSV 읽기

if not EVALUATION_CSV.exists():
    raise FileNotFoundError(
        f"평가용 CSV 파일을 찾을 수 없습니다: {EVALUATION_CSV}"
    )

evaluation_df = pd.read_csv(
    EVALUATION_CSV,
    dtype=str,
    keep_default_na=False,
    encoding="utf-8-sig"
)

# 필요한 열이 있는지 확인
required_eval_columns = {"query", "relevant_files"}

if not required_eval_columns.issubset(evaluation_df.columns):
    raise ValueError(
        "evaluation_queries.csv에는 "
        "'query', 'relevant_files' 열이 필요합니다."
    )

if evaluation_df.empty:
    raise ValueError("평가할 검색어가 없습니다.")


# 파일 이름을 비교하기 쉽게 정리하는 함수
def normalize_filename(filename):
    """
    파일 경로가 들어와도 파일 이름만 비교한다.
    윈도우 경로의 역슬래시도 처리한다.
    """
    filename = str(filename).strip()
    return filename.replace("\\", "/").split("/")[-1].casefold()


# 8. 9개 검색어 자동 평가

print("\n" + "=" * 50)
print("검색 성능 평가 시작")
print("=" * 50)

evaluation_results = []

for query_number, row in enumerate(
    evaluation_df.to_dict("records"), start=1
):
    query = row["query"].strip()

    # 정답 파일 이름은 세미콜론(;)으로 구분
    relevant_files = [
        filename.strip()
        for filename in row["relevant_files"].split(";")
        if filename.strip()
    ]

    if not query or not relevant_files:
        print(
            f"\n[{query_number}] 평가 건너뜀: "
            "검색어 또는 정답 파일이 비어 있습니다."
        )
        continue

    # 기존 검색 기능으로 Top 5 검색
    top_results = search_files(query, top_k=5)

    # 검색된 파일 이름 목록
    top5_filenames = [
        result["filename"] for result in top_results
    ]

    # 정답과 검색 결과 비교
    relevant_set = {
        normalize_filename(name) for name in relevant_files
    }

    matched_files = [
        filename for filename in top5_filenames
        if normalize_filename(filename) in relevant_set
    ]

    # 정답 파일이 하나라도 있으면 성공
    hit = int(len(matched_files) > 0)

    status = "성공" if hit else "실패"

    print(f"\n[{query_number}/{len(evaluation_df)}] {query}")
    print(f"평가 결과: {status}")

    print("검색 결과 Top 5:")
    for rank, result in enumerate(top_results, start=1):
        print(
            f"  {rank}. {result['filename']} "
            f"(유사도: {result['score']:.4f})"
        )

    print(
        "찾은 정답 파일: "
        + (", ".join(matched_files) if matched_files else "없음")
    )

    # 나중에 CSV로 저장할 평가 기록
    evaluation_results.append({
        "query": query,
        "relevant_files": ";".join(relevant_files),
        "top5_files": ";".join(top5_filenames),
        "matched_files": ";".join(matched_files),
        "hit_at_5": hit,
        "status": status
    })


# 9. 전체 Hit@5 계산 및 결과 저장

if not evaluation_results:
    raise ValueError("평가를 완료한 검색어가 없습니다.")

results_df = pd.DataFrame(evaluation_results)

total_queries = len(results_df)
successful_queries = int(results_df["hit_at_5"].sum())
failed_queries = total_queries - successful_queries

hit_at_5 = successful_queries / total_queries * 100

print("\n" + "=" * 50)
print("최종 평가 결과")
print("=" * 50)
print(f"평가한 검색어 수: {total_queries}")
print(f"성공: {successful_queries}")
print(f"실패: {failed_queries}")
print(f"전체 Hit@5: {hit_at_5:.2f}%")

# 검색어별 결과를 CSV 파일로 저장
results_df.to_csv(
    RESULTS_CSV,
    index=False,
    encoding="utf-8-sig"
)

print(f"\n평가 결과 저장 완료: {RESULTS_CSV}")


# 10. 평가가 끝난 후 기존처럼 직접 검색하기

print("\n추가로 직접 검색할 수 있습니다.")
print("종료하려면 q를 입력하세요.")

while True:
    query = input("\n검색어: ").strip()

    if query.lower() == "q":
        print("검색을 종료합니다.")
        break

    if not query:
        print("검색어를 입력해 주세요.")
        continue

    ranked_results = search_files(query, top_k=5)

    print("\n===== 검색 결과 Top 5 =====")

    for rank, result in enumerate(ranked_results, start=1):
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
