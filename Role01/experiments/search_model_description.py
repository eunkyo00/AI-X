from pathlib import Path
import sys
import hashlib

import numpy as np

import pandas as pd
from sentence_transformers import SentenceTransformer

# 1. 파일 경로 설정
BASE_DIR = Path(__file__).resolve().parent

TEXT_CSV = BASE_DIR / "extracted_text.csv"
METADATA_CSV = BASE_DIR / "metadata.csv"
EVALUATION_CSV = BASE_DIR / "evaluation_queries.csv"
RESULTS_CSV = BASE_DIR / "evaluation_results_description.csv"

MODEL_NAME = "intfloat/multilingual-e5-small"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80
TOP_K = 5


# 2. 텍스트 데이터와 메타데이터 읽기
if not TEXT_CSV.exists():
    raise FileNotFoundError(f"텍스트 추출 파일을 찾을 수 없습니다: {TEXT_CSV}")

df = pd.read_csv(
    TEXT_CSV,
    dtype=str,
    keep_default_na=False,
    encoding="utf-8-sig"
)

required_columns = {"file_id", "filename", "extracted_text"}
if not required_columns.issubset(df.columns):
    raise ValueError(
        f"필요한 열: {required_columns}\n현재 열: {list(df.columns)}"
    )

# metadata.csv에만 있는 열을 file_id 기준으로 추가한다.
if METADATA_CSV.exists():
    metadata = pd.read_csv(
        METADATA_CSV,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig"
    )

    if "file_id" in metadata.columns:
        metadata = metadata.drop_duplicates(subset=["file_id"], keep="first")
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

# 파일 ID와 파일명이 없거나 텍스트 추출 결과가 빈 행은 제외한다.
df = df[
    df["file_id"].astype(str).str.strip().ne("")
    & df["filename"].astype(str).str.strip().ne("")
    & df["extracted_text"].astype(str).str.strip().ne("")
].copy()

# 동일 file_id가 중복되어 있으면 첫 행만 사용한다.
df = df.drop_duplicates(subset=["file_id"], keep="first").reset_index(drop=True)

if df.empty:
    raise ValueError("검색할 텍스트가 없습니다.")

# 메타데이터 열이 없어도 코드가 작동하도록 빈 열을 만든다.
for column in ("project", "role", "path", "description"):
    if column not in df.columns:
        df[column] = ""

# 3. 파일명 정규화 및 텍스트 청킹
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


documents = []
chunk_info = []

for _, row in df.iterrows():
    filename = row["filename"]
    file_id = row["file_id"]
    content = row["extracted_text"]

    project = row.get("project", "")
    role = row.get("role", "")
    path = row.get("path", "")
    description = row.get("description", "")

    for chunk_number, chunk in enumerate(split_text(content)):
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

# 4. 임베딩 모델 불러오기 및 파일 임베딩
print("\n임베딩 모델을 불러오는 중...")
model = SentenceTransformer(MODEL_NAME)

# search_engine.py와 동일한 캐시 키/경로를 사용해 임베딩을 공유한다.
passages = ["passage: " + text for text in documents]
hasher = hashlib.sha256()
hasher.update(MODEL_NAME.encode("utf-8"))
for passage in passages:
    encoded = passage.encode("utf-8")
    hasher.update(len(encoded).to_bytes(8, "big"))
    hasher.update(encoded)

cache_key = hasher.hexdigest()[:16]
cache_dir = BASE_DIR / "embedding_cache"
cache_dir.mkdir(parents=True, exist_ok=True)
cache_path = cache_dir / f"embeddings_{cache_key}.npy"

if cache_path.exists():
    print("\n저장된 임베딩 불러오는 중...")
    document_embeddings = np.load(cache_path, allow_pickle=False)
    if document_embeddings.ndim != 2 or document_embeddings.shape[0] != len(passages):
        raise ValueError(
            "임베딩 캐시 크기가 검색 문서와 맞지 않습니다. "
            "캐시 파일을 삭제하고 재실행하세요."
        )
    print("임베딩 캐시 로딩 완료!")
else:
    print("\n파일 내용을 숫자 벡터로 변환하는 중...")
    document_embeddings = model.encode(
        passages,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True
    )
    np.save(cache_path, document_embeddings)
    print("파일 임베딩 계산 및 저장 완료!")

# 5. 검색 기능
def search_files(query, top_k=TOP_K):
    """검색어와 각 텍스트 조각의 유사도를 계산해 파일 단위 Top K를 반환한다."""
    query = str(query).strip()

    if not query or top_k <= 0:
        return []

    query_embedding = model.encode(
        ["query: " + query],
        normalize_embeddings=True,
        convert_to_numpy=True
    )[0]

    # 임베딩이 정규화되어 있으므로 내적은 코사인 유사도와 같다.
    scores = document_embeddings @ query_embedding

    # 동일 파일의 여러 조각 중 가장 높은 점수를 파일 점수로 사용한다.
    best_results = {}

    for index, score in enumerate(scores):
        info = chunk_info[index]
        file_id = info["file_id"]

        if file_id not in best_results or score > best_results[file_id]["score"]:
            best_results[file_id] = {**info, "score": float(score)}

    ranked_results = sorted(
        best_results.values(),
        key=lambda result: result["score"],
        reverse=True
    )
    return ranked_results[:top_k]

# 6. 평가용 CSV 읽기
if not EVALUATION_CSV.exists():
    raise FileNotFoundError(f"평가용 CSV 파일을 찾을 수 없습니다: {EVALUATION_CSV}")

evaluation_df = pd.read_csv(
    EVALUATION_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig"
)
required_eval_columns = {"query", "relevant_files", "file_id"}
if not required_eval_columns.issubset(evaluation_df.columns):
    raise ValueError(
        f"evaluation_queries.csv에 필요한 열: {required_eval_columns}\n"
        f"현재 열: {list(evaluation_df.columns)}"
    )
if evaluation_df.empty:
    raise ValueError("평가할 검색어가 없습니다.")

# 7. 정답 file_id 진단
indexed_files = df.set_index("file_id")
missing_gold_ids = []
filename_mismatches = []
invalid_rows = []

for row_number, row in enumerate(evaluation_df.to_dict("records"), start=1):
    query = row["query"].strip()
    gold_ids = [item.strip() for item in row["file_id"].split(";") if item.strip()]
    gold_names = [item.strip() for item in row["relevant_files"].split(";") if item.strip()]
    if not query or not gold_ids:
        invalid_rows.append(row_number)
        continue
    for gold_id in gold_ids:
        if gold_id not in indexed_files.index:
            missing_gold_ids.append((row_number, gold_id, query))
    # 파일명이 여러 개일 때는 각 이름과 ID의 순서가 일치한다고 가정한다.
    if len(gold_ids) == len(gold_names):
        for gold_id, gold_name in zip(gold_ids, gold_names):
            if gold_id in indexed_files.index:
                actual_name = indexed_files.loc[gold_id, "filename"]
                if normalize_filename(actual_name) != normalize_filename(gold_name):
                    filename_mismatches.append((row_number, gold_id, gold_name, actual_name))

print("\n" + "=" * 60)
print("정답 파일 ID 진단")
print("=" * 60)
print(f"평가 CSV 행 수: {len(evaluation_df)}")
print(f"검색 대상 파일 수: {len(df)}")
print(f"검색 대상에 없는 정답 ID 수: {len(missing_gold_ids)}")
for row_number, gold_id, query in missing_gold_ids:
    print(f"  [행 {row_number}] {gold_id}: {query}")
print(f"정답 ID와 파일명이 일치하지 않는 항목 수: {len(filename_mismatches)}")
for row_number, gold_id, expected, actual in filename_mismatches:
    print(f"  [행 {row_number}] {gold_id}: CSV={expected}, 색인={actual}")
print(f"검색어 또는 정답 ID가 비어 있는 행 수: {len(invalid_rows)}")
if missing_gold_ids:
    print("주의: 색인에 없는 정답 ID는 검색으로 맞힐 수 없으므로 평가 데이터/추출 결과를 확인하세요.")

# 8. 검색 성능 평가 (정답 file_id 기준)
print("\n" + "=" * 60)
print("검색 성능 평가 시작 (description 포함 실험)")
print("=" * 60)
evaluation_results = []

for query_number, row in enumerate(evaluation_df.to_dict("records"), start=1):
    query = row["query"].strip()
    relevant_files = [name.strip() for name in row["relevant_files"].split(";") if name.strip()]
    gold_ids = [item.strip() for item in row["file_id"].split(";") if item.strip()]
    if not query or not gold_ids:
        print(f"\n[{query_number}/{len(evaluation_df)}] 평가 건너뜀: 검색어 또는 정답 ID 없음")
        continue

    top_results = search_files(query, top_k=TOP_K)
    top5_filenames = [result["filename"] for result in top_results]
    top5_file_ids = [result["file_id"] for result in top_results]
    top5_scores = [f"{result['score']:.4f}" for result in top_results]
    matched_results = [result for result in top_results if result["file_id"] in set(gold_ids)]
    hit = int(bool(matched_results))
    status = "성공" if hit else "실패"
    gold_indexed = all(gold_id in indexed_files.index for gold_id in gold_ids)

    print(f"\n[{query_number}/{len(evaluation_df)}] {query}")
    print(f"평가 결과(file_id 기준): {status}")
    print(f"정답 file_id: {', '.join(gold_ids)}")
    if not gold_indexed:
        print("주의: 일부 정답 ID가 검색 색인에 없습니다.")
    print("검색 결과 Top 5:")
    for rank, result in enumerate(top_results, start=1):
        print(f"  {rank}. {result['filename']} (유사도: {result['score']:.4f}, file_id: {result['file_id']})")
    print("찾은 정답 파일: " + (
        ", ".join(f"{result['filename']} ({result['file_id']})" for result in matched_results)
        if matched_results else "없음"
    ))

    evaluation_results.append({
        "query": query,
        "relevant_files": ";".join(relevant_files),
        "gold_file_ids": ";".join(gold_ids),
        "gold_ids_indexed": gold_indexed,
        "top5_files": ";".join(top5_filenames),
        "top5_file_ids": ";".join(top5_file_ids),
        "top5_scores": ";".join(top5_scores),
        "matched_file_ids": ";".join(result["file_id"] for result in matched_results),
        "hit_at_5": hit,
        "status": status,
    })

# 9. 전체 Hit@5 계산 및 결과 저장
if not evaluation_results:
    raise ValueError("평가를 완료한 검색어가 없습니다.")
results_df = pd.DataFrame(evaluation_results)
total_queries = len(results_df)
successful_queries = int(results_df["hit_at_5"].sum())
failed_queries = total_queries - successful_queries
hit_at_5 = successful_queries / total_queries * 100

print("\n" + "=" * 60)
print("최종 평가 결과 (file_id 기준)")
print("=" * 60)
print(f"평가한 검색어 수: {total_queries}")
print(f"성공: {successful_queries}")
print(f"실패: {failed_queries}")
print(f"Hit@5 (file_id 기준): {hit_at_5:.2f}%")
print(f"정답 ID가 모두 색인에 있는 쿼리 수: {int(results_df['gold_ids_indexed'].sum())}/{total_queries}")
results_df.to_csv(RESULTS_CSV, index=False, encoding="utf-8-sig")
print(f"\n평가 결과 저장 완료: {RESULTS_CSV}")


# 10. 평가 후 직접 검색
print("\n추가로 직접 검색할 수 있습니다.")
print("종료하려면 q를 입력하세요.")

while "--no-interactive" not in sys.argv:
    query = input("\n검색어: ").strip()

    if query.lower() == "q":
        print("검색을 종료합니다.")
        break

    if not query:
        print("검색어를 입력해 주세요.")
        continue

    ranked_results = search_files(query, top_k=TOP_K)
    print("\n===== 검색 결과 Top 5 =====")

    if not ranked_results:
        print("검색 결과가 없습니다.")
        continue

    for rank, result in enumerate(ranked_results, start=1):
        print(f"\n[{rank}위] {result['filename']}")
        print(f"파일 ID: {result['file_id']}")
        print(f"유사도 점수: {result['score']:.4f}")

        if result["path"]:
            print(f"경로: {result['path']}")

        preview = result["chunk_text"].replace("\n", " ").strip()
        print(f"관련 내용: {preview[:200]}")
