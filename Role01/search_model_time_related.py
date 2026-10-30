from pathlib import Path
import sys
import hashlib
import re
from datetime import datetime, timedelta

import numpy as np

import pandas as pd
from sentence_transformers import SentenceTransformer

# 1. 파일 경로 설정
BASE_DIR = Path(__file__).resolve().parent

TEXT_CSV = BASE_DIR / "extracted_text.csv"
METADATA_CSV = BASE_DIR / "metadata.csv"
EVALUATION_CSV = BASE_DIR / "evaluation_queries.csv"
RESULTS_CSV = BASE_DIR / "evaluation_results_time_fixed.csv"
RELATIONS_CSV = BASE_DIR / "file_relations.csv"

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

# metadata.csv를 메타데이터의 기준으로 사용한다.
# extracted_text.csv에도 같은 열이 있을 수 있으므로, 기존 열을 제거한 뒤 병합한다.
if METADATA_CSV.exists():
    metadata = pd.read_csv(
        METADATA_CSV,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig"
    )
    if "file_id" not in metadata.columns:
        raise ValueError("metadata.csv에 file_id 열이 없습니다.")

    metadata = metadata.drop_duplicates(subset=["file_id"], keep="first")
    metadata_columns = [col for col in metadata.columns if col != "file_id"]
    # 파일명은 추출 데이터의 값을 유지하고, 나머지 메타데이터는 metadata.csv를 우선한다.
    replace_columns = [col for col in metadata_columns if col != "filename"]
    df = df.drop(columns=replace_columns, errors="ignore")
    df = df.merge(
        metadata[["file_id"] + replace_columns],
        on="file_id",
        how="left"
    )
    for col in replace_columns:
        df[col] = df[col].fillna("")

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
for column in ("project", "role", "path", "description", "created_at", "modified_at"):
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

# 5. 시간 조건 분석 및 검색 기능
# 날짜는 현재 metadata.csv에 저장된 값을 그대로 사용한다.
# 파일 수집 시점이 created_at에 들어갔다면 그 날짜를 기준으로 평가된다.

def parse_metadata_date(value):
    """2026-10-02 14:53:20, 2026.4.10 18:31 등을 모두 처리."""
    value = str(value).strip()
    if not value or value.lower() in ("nan", "nat", "none"):
        return pd.NaT
    value = re.sub(r"^(\d{4})[./](\d{1,2})[./](\d{1,2})", r"\1-\2-\3", value)
    return pd.to_datetime(value, errors="coerce")


file_dates = {}
for _, row in df.iterrows():
    file_dates[row["file_id"]] = {
        "created_at": parse_metadata_date(row["created_at"]),
        "modified_at": parse_metadata_date(row["modified_at"]),
    }


def analyze_time_query(query, now=None):
    """시간 범위 [start, end) 및 기준 열을 분석한다.

    반환값: None(일반 검색) 또는 {field, start, end, semantic_query}.
    명시적으로 지원하지 않는 시간 표현은 ValueError로 알린다.
    """
    now = pd.Timestamp.now().normalize() if now is None else pd.Timestamp(now).normalize()
    text = str(query).strip()
    field = "created_at" if re.search(r"생성|만든|작성|저장한|생긴|추가한|추가된", text) else "modified_at"
    # 수정과 생성이 동시에 나오면 어느 날짜 기준인지 모호하므로 제외한다.
    if re.search(r"생성|만든|작성|저장한|생긴|추가한|추가된", text) and re.search(r"수정|변경|편집|업데이트", text):
        raise ValueError("생성일과 수정일이 동시에 지정됨")

    match = None
    start = end = None
    patterns = [
        (r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", "day"),
        (r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", "day"),
        (r"(\d{4})년\s*(\d{1,2})월(?:달)?", "month"),
        (r"(\d{4})[-./](\d{1,2})(?![-./]\d)", "month"),
        (r"(\d{4})년", "year"),
        # 연도가 생략된 3월/3월달은 현재 연도로 해석한다.
        (r"(?<!\d)([1-9]|1[0-2])월(?:달)?(?!\d)", "month_only"),
    ]
    for pattern, kind in patterns:
        match = re.search(pattern, text)
        if match:
            vals = [int(v) for v in match.groups()]
            try:
                if kind == "day":
                    start = pd.Timestamp(vals[0], vals[1], vals[2])
                    end = start + pd.Timedelta(days=1)
                elif kind == "month":
                    start = pd.Timestamp(vals[0], vals[1], 1)
                    end = start + pd.DateOffset(months=1)
                elif kind == "month_only":
                    start = pd.Timestamp(now.year, vals[0], 1)
                    end = start + pd.DateOffset(months=1)
                else:
                    start = pd.Timestamp(vals[0], 1, 1)
                    end = start + pd.DateOffset(years=1)
            except (ValueError, OverflowError) as exc:
                raise ValueError(f"잘못된 날짜: {match.group(0)}") from exc
            break

    if start is None:
        relative = re.search(r"최근\s*(\d+)\s*(일|주|개월|달)", text)
        if relative:
            amount = int(relative.group(1))
            if amount < 1:
                raise ValueError("최근 기간은 1 이상이어야 함")
            unit = relative.group(2)
            end = now + pd.Timedelta(days=1)
            if unit == "일":
                start = now - pd.Timedelta(days=amount - 1)
            elif unit == "주":
                start = now - pd.Timedelta(days=7 * amount - 1)
            else:
                start = now - pd.DateOffset(months=amount)
            match = relative
        else:
            calendar = {
                "오늘": (now, now + pd.Timedelta(days=1)),
                "어제": (now - pd.Timedelta(days=1), now),
                "이번달": (now.replace(day=1), now.replace(day=1) + pd.DateOffset(months=1)),
                "이번 달": (now.replace(day=1), now.replace(day=1) + pd.DateOffset(months=1)),
                "지난달": (now.replace(day=1) - pd.DateOffset(months=1), now.replace(day=1)),
                "지난 달": (now.replace(day=1) - pd.DateOffset(months=1), now.replace(day=1)),
                "이번주": (now - pd.Timedelta(days=now.weekday()), now - pd.Timedelta(days=now.weekday()) + pd.Timedelta(days=7)),
                "이번 주": (now - pd.Timedelta(days=now.weekday()), now - pd.Timedelta(days=now.weekday()) + pd.Timedelta(days=7)),
                "지난주": (now - pd.Timedelta(days=now.weekday() + 7), now - pd.Timedelta(days=now.weekday())),
                "지난 주": (now - pd.Timedelta(days=now.weekday() + 7), now - pd.Timedelta(days=now.weekday())),
                "올해": (pd.Timestamp(now.year, 1, 1), pd.Timestamp(now.year + 1, 1, 1)),
                "작년": (pd.Timestamp(now.year - 1, 1, 1), pd.Timestamp(now.year, 1, 1)),
            }
            for phrase in sorted(calendar, key=len, reverse=True):
                found = re.search(re.escape(phrase), text)
                if found:
                    start, end = calendar[phrase]
                    match = found
                    break

    if start is None:
        # 시간 표현이 있지만 미지원이라면 일반 의미 검색으로 조용히 넘기지 않는다.
        if re.search(r"지난|이번|최근|\d+일\s*(전|동안)|\d+주\s*전|\d+월\s*전|\d{1,2}월달?", text):
            raise ValueError("아직 지원하지 않는 시간 표현")
        return None

    semantic_query = (text[:match.start()] + " " + text[match.end():]).strip()
    semantic_query = re.sub(
        r"생성된|생성한|만든|작성한|추가한|추가된|수정된|수정한|변경된|편집한|업데이트한|저장한|동안|이내",
        " ",
    semantic_query
    )
    semantic_query = re.sub(r"^\s*(?:에|의|동안|부터|까지|중에|내에)\s*", "", semantic_query)
    semantic_query = re.sub(r"\s+", " ", semantic_query).strip()
    if not semantic_query:
        semantic_query = text
    return {"field": field, "start": start, "end": end, "semantic_query": semantic_query}

def search_files(query, top_k=TOP_K, return_time_info=False):
    """전체 파일 유사도 계산 후 시간 필터 적용; 시간 없는 쿼리는 기존 검색과 동일."""
    query = str(query).strip()
    if not query or top_k <= 0:
        return ([], None) if return_time_info else []

    time_info = analyze_time_query(query)
    semantic_query = time_info["semantic_query"] if time_info else query
    query_embedding = model.encode(
        ["query: " + semantic_query],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )[0]
    scores = document_embeddings @ query_embedding
    best_results = {}
    for index, score in enumerate(scores):
        info = chunk_info[index]
        file_id = info["file_id"]
        if time_info is not None:
            date = file_dates[file_id][time_info["field"]]
            if pd.isna(date) or not (time_info["start"] <= date < time_info["end"]):
                continue
        if file_id not in best_results or score > best_results[file_id]["score"]:
            best_results[file_id] = {**info, "score": float(score)}
    ranked_results = sorted(best_results.values(), key=lambda result: result["score"], reverse=True)
    result = ranked_results[:top_k]
    return (result, time_info) if return_time_info else result

# 6. 검색 결과와 연결된 파일 추천 (기존 검색 순위에는 영향을 주지 않음)
# 방향성 있는 references는 출발 파일에서만 추천한다.
# 반대 방향은 별도 표시하여 실제 파일 참조 방향을 혼동하지 않도록 한다.
RELATION_LABELS = {
    "references": "직접 참조",
    "reference_candidate": "참조 후보 (확인 필요)",
    "content_similar": "내용 유사 (자동 추정)",
    "semantic_related": "의미 유사 (자동 추정)",
    "same_context": "같은 맥락 (자동 추정)",
    "same_folder": "같은 폴더",
}
DEFAULT_RELATION_TYPES = {"references", "reference_candidate", "content_similar", "semantic_related", "same_context"}

file_names_by_id = dict(zip(df["file_id"], df["filename"]))
relations_by_source = {}
if RELATIONS_CSV.exists():
    relations_df = pd.read_csv(RELATIONS_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required_relation_columns = {"source_file_id", "target_file_id", "relation_type", "weight", "evidence"}
    if not required_relation_columns.issubset(relations_df.columns):
        raise ValueError(f"관계 CSV에 필요한 열이 없습니다: {required_relation_columns - set(relations_df.columns)}")
    for relation in relations_df.to_dict("records"):
        source_id = relation["source_file_id"].strip()
        target_id = relation["target_file_id"].strip()
        if source_id not in file_names_by_id or target_id not in file_names_by_id or source_id == target_id:
            continue
        try:
            weight = float(relation["weight"])
        except ValueError:
            continue
        entry = {
            "target_file_id": target_id,
            "target_filename": file_names_by_id[target_id],
            "relation_type": relation["relation_type"].strip(),
            "weight": weight,
            "evidence": relation["evidence"].strip(),
        }
        relations_by_source.setdefault(source_id, []).append(entry)
    print(f"관계 데이터 로딩 완료: {sum(map(len, relations_by_source.values()))}개")
else:
    print("관계 CSV가 없어 관련 파일 추천 없이 검색합니다.")


def get_related_files(file_id, top_n=3, include_same_folder=False):
    """하나의 검색 결과에 연결된 파일을 근거와 함께 반환한다."""
    allowed = set(DEFAULT_RELATION_TYPES)
    if include_same_folder:
        allowed.add("same_folder")
    candidates = [r for r in relations_by_source.get(file_id, []) if r["relation_type"] in allowed]
    # 동일 대상에 관계가 여러 개면 우선순위가 가장 높은 근거를 선택한다.
    type_priority = {"references": 5, "reference_candidate": 4, "semantic_related": 3,
                     "content_similar": 3, "same_context": 2, "same_folder": 1}
    candidates.sort(key=lambda r: (type_priority.get(r["relation_type"], 0), r["weight"]), reverse=True)
    unique = {}
    for candidate in candidates:
        unique.setdefault(candidate["target_file_id"], candidate)
    return list(unique.values())[:top_n]


def print_related_files(file_id, top_n=3):
    related = get_related_files(file_id, top_n=top_n)
    if not related:
        print("관련 파일: 탐지된 관계 없음")
        return
    print("관련 파일 추천 (검색 순위와 별개):")
    for item in related:
        label = RELATION_LABELS.get(item["relation_type"], item["relation_type"])
        print(f"  - {item['target_filename']} ({item['target_file_id']}) | {label} | 관계 가중치: {item['weight']:.3f}")
        if item["evidence"]:
            print(f"    근거: {item['evidence'][:160]}")


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

    try:
        top_results, time_info = search_files(query, top_k=TOP_K, return_time_info=True)
    except ValueError as exc:
        print(f"\n[{query_number}/{len(evaluation_df)}] 시간 조건 분석 실패: {query} ({exc})")
        evaluation_results.append({
            "query": query, "query_type": "temporal_unsupported", "relevant_files": ";".join(relevant_files),
            "gold_file_ids": ";".join(gold_ids), "gold_ids_indexed": False,
            "top5_files": "", "top5_file_ids": "", "top5_scores": "",
            "matched_file_ids": "", "hit_at_5": None, "status": "평가제외",
            "time_field": "", "time_start": "", "time_end": "", "gold_matches_time": None,
        })
        continue
    query_type = "temporal" if time_info else "semantic"
    time_field = time_info["field"] if time_info else ""
    time_start = str(time_info["start"]) if time_info else ""
    time_end = str(time_info["end"]) if time_info else ""
    gold_matches_time = None
    if time_info:
        gold_matches_time = any(
            (gold_id in file_dates)
            and pd.notna(file_dates[gold_id][time_field])
            and (time_info["start"] <= file_dates[gold_id][time_field] < time_info["end"])
            for gold_id in gold_ids
        )
        if not gold_matches_time:
            print(f"주의: 정답 파일이 {time_field} 시간 조건에 맞지 않습니다. CSV 정답/날짜 확인 필요")
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
        "query_type": query_type,
        "time_field": time_field,
        "time_start": time_start,
        "time_end": time_end,
        "gold_matches_time": gold_matches_time,
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
valid_results = results_df[results_df["hit_at_5"].notna()].copy()
total_queries = len(valid_results)
if total_queries == 0:
    raise ValueError("유효한 평가 쿼리가 없습니다.")
successful_queries = int(valid_results["hit_at_5"].sum())
failed_queries = total_queries - successful_queries
hit_at_5 = successful_queries / total_queries * 100

print("\n" + "=" * 60)
print("최종 평가 결과 (file_id 기준)")
print("=" * 60)
print(f"평가한 검색어 수: {total_queries}")
print(f"성공: {successful_queries}")
print(f"실패: {failed_queries}")
print(f"Hit@5 (file_id 기준): {hit_at_5:.2f}%")
print(f"정답 ID가 모두 색인에 있는 쿼리 수: {int(valid_results['gold_ids_indexed'].sum())}/{total_queries}")
for query_type, label in (("semantic", "의미 검색"), ("temporal", "시간 검색")):
    subset = valid_results[valid_results["query_type"] == query_type]
    if not subset.empty:
        successes = int(subset["hit_at_5"].sum())
        print(f"{label} Hit@5: {successes}/{len(subset)} ({successes / len(subset) * 100:.2f}%)")
print(f"시간 표현 미지원으로 평가 제외: {len(results_df) - total_queries}개")
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

    try:
        ranked_results = search_files(query, top_k=TOP_K)
    except ValueError as exc:
        print(f"시간 조건을 분석할 수 없습니다: {exc}")
        continue
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
        print_related_files(result["file_id"])