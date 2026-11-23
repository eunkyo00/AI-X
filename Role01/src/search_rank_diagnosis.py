from pathlib import Path
import hashlib

import numpy as np

import pandas as pd
from sentence_transformers import SentenceTransformer

# 1. 파일 경로 설정
BASE_DIR = Path(__file__).resolve().parent

TEXT_CSV = BASE_DIR / "extracted_text.csv"
METADATA_CSV = BASE_DIR / "metadata.csv"
EVALUATION_CSV = BASE_DIR / "evaluation_queries.csv"
RESULTS_CSV = BASE_DIR / "evaluation_results_rerank.csv"
DIAG_CSV = BASE_DIR / "failed_query_rank_diagnosis.csv"

MODEL_NAME = "intfloat/multilingual-e5-small"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80
TOP_K = 5

# 리랭킹 실험 가중치: 평가 결과를 보면서 조정
RERANK_CANDIDATES = 30
MULTI_CHUNK_WEIGHT = 0.15
FILENAME_WEIGHT = 0.04


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
for column in ("project", "role", "path"):
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

    for chunk_number, chunk in enumerate(split_text(content)):
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

# 5. 전체 순위 진단 (기존 검색 / 리랭킹 검색)
import re
from collections import defaultdict


def filename_match_score(query, filename):
    query_tokens = set(re.findall(r"[가-힣]+|[a-z0-9]+", query.casefold()))
    filename_tokens = set(re.findall(r"[가-힣]+|[a-z0-9]+", filename.casefold()))
    stopwords = {"코드", "파일", "자료", "분석", "예측", "관련", "찾아줘", "pdf", "py", "r", "ipynb", "txt", "csv"}
    query_tokens -= stopwords
    return len(query_tokens & filename_tokens) / len(query_tokens) if query_tokens else 0.0


def get_all_rankings(query):
    """모든 파일의 기존 순위와 리랭킹 후 순위를 반환한다.

    리랭킹은 원본 스크립트와 동일하게 기존 상위 30개 후보에만 적용한다.
    나머지 파일은 기존 순서 그대로 뒤에 붙인다.
    """
    query_vector = model.encode(
        ["query: " + query], normalize_embeddings=True, convert_to_numpy=True
    )[0]
    scores = document_embeddings @ query_vector
    grouped = defaultdict(list)
    for index, score in enumerate(scores):
        grouped[chunk_info[index]["file_id"]].append((float(score), index))

    candidates = []
    for file_id, values in grouped.items():
        values.sort(key=lambda item: item[0], reverse=True)
        best_score, best_index = values[0]
        info = chunk_info[best_index]
        candidates.append({
            "file_id": file_id,
            "filename": info["filename"],
            "path": info["path"],
            "original_score": best_score,
            "chunk_scores": values,
        })
    baseline = sorted(candidates, key=lambda x: x["original_score"], reverse=True)

    candidate_count = max(RERANK_CANDIDATES, TOP_K)
    reranked_head = []
    for item in baseline[:candidate_count]:
        values = [score for score, _ in item["chunk_scores"]]
        top3_mean = sum(values[:3]) / min(3, len(values))
        name_score = filename_match_score(query, item["filename"])
        rerank_score = (
            (1 - MULTI_CHUNK_WEIGHT) * item["original_score"]
            + MULTI_CHUNK_WEIGHT * top3_mean
            + FILENAME_WEIGHT * name_score
        )
        reranked_head.append({**item, "rerank_score": rerank_score})
    reranked_head.sort(key=lambda x: x["rerank_score"], reverse=True)
    # 주의: 30위 밖의 파일은 리랭킹 점수가 아닌 기존 점수 순서를 유지한다.
    reranked_all = reranked_head + baseline[candidate_count:]
    return baseline, reranked_all


def best_gold_rank(results, gold_ids):
    for rank, result in enumerate(results, start=1):
        if result["file_id"] in gold_ids:
            return rank, result
    return None, None


if not EVALUATION_CSV.exists():
    raise FileNotFoundError(f"평가 파일이 없습니다: {EVALUATION_CSV}")
evaluation_df = pd.read_csv(EVALUATION_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
for column in ("query", "file_id", "relevant_files"):
    if column not in evaluation_df.columns:
        raise ValueError(f"평가 파일에 '{column}' 열이 없습니다.")

# 지난 리랭킹 평가 결과가 있으면 실패 쿼리만 골라 계산한다.
# 파일이 없을 때는 전체 쿼리를 평가한 뒤 실패한 것만 저장한다.
failed_queries = None
if RESULTS_CSV.exists():
    previous = pd.read_csv(RESULTS_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if {"query", "hit_at_5"}.issubset(previous.columns):
        failed_queries = set(previous.loc[previous["hit_at_5"].str.strip() == "0", "query"].str.strip())
        print(f"기존 평가 CSV에서 실패 쿼리 {len(failed_queries)}개 확인")

indexed_ids = set(df["file_id"].astype(str))
records = []
for number, row in enumerate(evaluation_df.to_dict("records"), start=1):
    query = row["query"].strip()
    gold_ids = [s.strip() for s in row["file_id"].split(";") if s.strip()]
    if not query or not gold_ids:
        continue
    if failed_queries is not None and query not in failed_queries:
        continue

    baseline, reranked = get_all_rankings(query)
    old_rank, old_item = best_gold_rank(baseline, set(gold_ids))
    new_rank, new_item = best_gold_rank(reranked, set(gold_ids))
    if new_rank is not None and new_rank <= TOP_K:
        # 기존 결과 파일이 없을 때 성공 쿼리는 저장하지 않는다.
        continue

    if new_rank is None:
        category = "정답 파일 미색인"
    elif new_rank <= 10:
        category = "6~10위: 순위 조정 후보"
    elif new_rank <= 30:
        category = "11~30위: 후보 내 순위 조정 가능"
    else:
        category = "31위 이하: 후보 확장/검색 표현 개선 검토"

    record = {
        "query": query,
        "gold_file_ids": ";".join(gold_ids),
        "relevant_files": row["relevant_files"],
        "gold_indexed": all(g in indexed_ids for g in gold_ids),
        "baseline_gold_rank": old_rank if old_rank is not None else "미색인",
        "rerank_gold_rank": new_rank if new_rank is not None else "미색인",
        "rank_change_positive_is_better": (old_rank - new_rank) if old_rank and new_rank else "",
        "gold_filename": new_item["filename"] if new_item else "",
        "gold_original_score": round(new_item["original_score"], 6) if new_item else "",
        "gold_rerank_score": (round(new_item["rerank_score"], 6)
                              if new_item and "rerank_score" in new_item else "후보 30위 밖"),
        "rerank_top5_ids": ";".join(x["file_id"] for x in reranked[:5]),
        "rerank_top5_files": ";".join(x["filename"] for x in reranked[:5]),
        "diagnosis": category,
    }
    records.append(record)
    print(f"[{number}/{len(evaluation_df)}] 정답 {new_rank if new_rank is not None else '미색인'}위"
          f" (기존 {old_rank if old_rank is not None else '미색인'}위) | {query}")

columns = [
    "query", "gold_file_ids", "relevant_files", "gold_indexed",
    "baseline_gold_rank", "rerank_gold_rank", "rank_change_positive_is_better",
    "gold_filename", "gold_original_score", "gold_rerank_score",
    "rerank_top5_ids", "rerank_top5_files", "diagnosis",
]
result_df = pd.DataFrame(records, columns=columns)
if not result_df.empty:
    result_df = result_df.sort_values(
        "rerank_gold_rank", key=lambda s: pd.to_numeric(s, errors="coerce").fillna(10**9)
    )
result_df.to_csv(DIAG_CSV, index=False, encoding="utf-8-sig")
print("\n" + "=" * 60)
print(f"진단 완료: 리랭킹 Hit@5 실패 {len(result_df)}개")
print("정답 순위별 분포:")
for category, count in result_df["diagnosis"].value_counts().items():
    print(f"  {category}: {count}개")
print(f"결과 파일: {DIAG_CSV}")
print("기존 코드와 캐시, 평가 결과 CSV는 수정하지 않았습니다.")
