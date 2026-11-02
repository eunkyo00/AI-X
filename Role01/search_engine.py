"""파일 단위 의미·시간 검색 엔진.

기존 search_model_modified.py의 검색 로직을 API에서 재사용하도록 분리.
평가 및 대화형 입력은 포함하지 않으며 문서 임베딩은 디스크에 캐싱한다.
"""
from pathlib import Path
import hashlib
import json
import re

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


def parse_metadata_date(value):
    """2026-10-02 14:53:20, 2026.4.10 18:31 등을 모두 처리."""
    value = str(value).strip()
    if not value or value.lower() in ("nan", "nat", "none"):
        return pd.NaT
    value = re.sub(r"^(\d{4})[./](\d{1,2})[./](\d{1,2})", r"\1-\2-\3", value)
    return pd.to_datetime(value, errors="coerce")

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

class SearchEngine:
    """최초 생성 시 CSV를 읽고 임베딩 캐시를 로딩하거나 생성한다."""

    def __init__(self, text_csv=TEXT_CSV, metadata_csv=METADATA_CSV,
                 model_name=MODEL_NAME):
        self.text_csv = text_csv = Path(text_csv)
        self.metadata_csv = Path(metadata_csv)
        self.model_name = model_name
        self._input_signature = self.input_signature()
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
            if "file_id" not in metadata.columns:
                raise ValueError("metadata.csv에 file_id 열이 없습니다.")
            metadata = metadata.drop_duplicates(subset=["file_id"], keep="first")
            # filename과 추출 본문은 extracted_text.csv에서 유지한다.
            # 나머지 메타데이터는 metadata.csv의 값을 우선한다.
            replace_columns = [c for c in metadata.columns
                               if c not in ("file_id", "filename", "extracted_text")]
            df = df.drop(columns=replace_columns, errors="ignore")
            df = df.merge(metadata[["file_id"] + replace_columns],
                          on="file_id", how="left")
            for col in replace_columns:
                df[col] = df[col].fillna("")
            # ID가 달라져 잘못된 파일에 메타데이터가 연결되는 상황을 방지한다.
            if "path" in metadata.columns and "path" in df.columns:
                check = df.merge(metadata[["file_id", "filename"]].rename(
                    columns={"filename": "metadata_filename"}), on="file_id", how="left")
                mismatch = check[check["metadata_filename"].notna() &
                                 (check["metadata_filename"].map(normalize_filename) !=
                                  check["filename"].map(normalize_filename))]
                if not mismatch.empty:
                    raise ValueError(f"metadata.csv와 extracted_text.csv의 file_id/파일명 불일치: {len(mismatch)}개")

        df = df[
            df["file_id"].astype(str).str.strip().ne("")
            & df["filename"].astype(str).str.strip().ne("")
            & df["extracted_text"].astype(str).str.strip().ne("")
        ].copy()
        df = df.drop_duplicates(subset=["file_id"], keep="first").sort_values("file_id").reset_index(drop=True)
        if df.empty:
            raise ValueError("검색할 텍스트가 없습니다.")
        for column in ("project", "role", "description", "path", "created_at", "modified_at"):
            if column not in df.columns:
                df[column] = ""
        df[["project", "role", "description", "path", "created_at", "modified_at"]] = df[["project", "role", "description", "path", "created_at", "modified_at"]].fillna("")
        self.file_dates = {row["file_id"]: {
            "created_at": parse_metadata_date(row["created_at"]),
            "modified_at": parse_metadata_date(row["modified_at"]),
        } for _, row in df.iterrows()}

        self.df = df
        self.documents = []
        self.chunk_info = []
        for _, row in df.iterrows():
            for chunk_number, chunk in enumerate(split_text(row["extracted_text"])):
                self.documents.append(
                    f"파일명: {row['filename']}\n"
                    f"프로젝트: {row['project']}\n"
                    f"파일 역할: {row['role']}\n"
                    f"파일 설명: {row['description']}\n"
                    f"파일 내용:\n{chunk}"
                )
                self.chunk_info.append({
                    "file_id": row["file_id"],
                    "filename": row["filename"],
                    "path": row["path"],
                    "chunk_number": chunk_number,
                    "chunk_text": chunk,
                })

        self.relations_by_source = {}
        relations_path = self.text_csv.parent / "file_relations.csv"
        if relations_path.exists():
            relations_df = pd.read_csv(relations_path, dtype=str,
                                       keep_default_na=False, encoding="utf-8-sig")
            required = {"source_file_id", "target_file_id", "relation_type", "weight", "evidence"}
            if not required.issubset(relations_df.columns):
                raise ValueError(f"file_relations.csv 누락 열: {required - set(relations_df.columns)}")
            file_names = dict(zip(df["file_id"], df["filename"]))
            for relation in relations_df.to_dict("records"):
                source = relation["source_file_id"].strip()
                target = relation["target_file_id"].strip()
                if source not in file_names or target not in file_names or source == target:
                    continue
                try:
                    weight = float(relation["weight"])
                except ValueError:
                    continue
                self.relations_by_source.setdefault(source, []).append({
                    "target_file_id": target,
                    "target_filename": file_names[target],
                    "relation_type": relation["relation_type"].strip(),
                    "weight": weight,
                    "evidence": relation["evidence"].strip(),
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

        shared_dir = BASE_DIR / "search_index"
        shared_info = shared_dir / "index.json"
        shared_valid = False
        if shared_info.is_file():
            info = json.loads(shared_info.read_text(encoding="utf-8"))
            shared_valid = (info.get("signature") == self._input_signature
                            and info.get("model") == model_name)
        if shared_valid:
            with np.load(shared_dir / "embeddings.npz", allow_pickle=False) as data:
                self.document_embeddings = data["embeddings"].copy()
            if self.document_embeddings.shape[0] != len(passages):
                raise ValueError("통합 갱신 인덱스와 검색 본문의 수가 다릅니다.")
            print("통합 갱신 검색 인덱스 로딩 완료!")
        elif cache_path.exists():
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

    def input_signature(self):
        digest = hashlib.sha256(self.model_name.encode())
        for path in (self.text_csv, self.metadata_csv, self.text_csv.parent / "file_relations.csv"):
            if path.exists():
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def refresh(self):
        if (self.text_csv.parent.parent / ".update-data.lock").exists():
            raise RuntimeError("데이터 갱신 중입니다. 완료 후 다시 검색하세요.")
        if self.input_signature() != self._input_signature:
            replacement = type(self)(self.text_csv, self.metadata_csv, self.model_name)
            self.__dict__.update(replacement.__dict__)

    def search_files(self, query, top_k=TOP_K):
        """기존 반환 형식을 유지하면서 시간 조건을 적용한 의미 검색."""
        self.refresh()
        query = str(query).strip()
        if not query or top_k <= 0:
            return []

        time_info = analyze_time_query(query)
        semantic_query = time_info["semantic_query"] if time_info else query
        query_embedding = self.model.encode(
            ["query: " + semantic_query],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0]
        scores = self.document_embeddings @ query_embedding

        best_results = {}
        for index, score in enumerate(scores):
            info = self.chunk_info[index]
            file_id = info["file_id"]
            if time_info is not None:
                date = self.file_dates[file_id][time_info["field"]]
                if pd.isna(date) or not (time_info["start"] <= date < time_info["end"]):
                    continue
            if file_id not in best_results or score > best_results[file_id]["score"]:
                best_results[file_id] = {**info, "score": float(score)}

        ranked_results = sorted(
            best_results.values(), key=lambda result: result["score"], reverse=True
        )
        return ranked_results[:top_k]

    def get_related_files(self, file_id, top_n=3, include_same_folder=False):
        """file_relations.csv의 관계를 검색 결과와 별도로 반환한다."""
        self.refresh()
        allowed = {"references", "reference_candidate", "content_similar",
                   "semantic_related", "same_context"}
        if include_same_folder:
            allowed.add("same_folder")
        priority = {"references": 5, "reference_candidate": 4,
                    "semantic_related": 3, "content_similar": 3,
                    "same_context": 2, "same_folder": 1}
        candidates = [r for r in self.relations_by_source.get(file_id, [])
                      if r["relation_type"] in allowed]
        candidates.sort(key=lambda r: (priority.get(r["relation_type"], 0), r["weight"]),
                        reverse=True)
        unique = {}
        for candidate in candidates:
            unique.setdefault(candidate["target_file_id"], candidate)
        return list(unique.values())[:top_n]


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


def get_related_files(file_id, top_n=3, include_same_folder=False):
    """검색된 파일에 연결된 파일을 별도로 조회한다."""
    return get_engine().get_related_files(file_id, top_n, include_same_folder)


if __name__ == "__main__":
    results = search_files("SARIMA 예측 코드", top_k=5)
    for rank, result in enumerate(results, 1):
        print(f"{rank}. {result['filename']} ({result['file_id']}): {result['score']:.4f}")

