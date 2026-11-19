from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

from refresh_search import load_index

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR.parent

TOP_K = 5
THRESHOLD = 0.55

# 1. 데이터 불러오기
def read_csv(path):
    return pd.read_csv(
        path, dtype=str, keep_default_na=False,
        encoding="utf-8-sig"
    )


metadata = read_csv(BASE_DIR / "metadata.csv")
classification = read_csv(
    ROOT / "Role02/metadata_classification_generated.csv"
)
references = read_csv(
    ROOT / "Role03/output/relations.csv"
)

info, embeddings = load_index(BASE_DIR / "search_index")

metadata = metadata.drop_duplicates("file_id")
classification = classification.drop_duplicates("file_id")

files = metadata.set_index("file_id").to_dict("index")
classes = classification.set_index("file_id").to_dict("index")


# 2. 수동 분류 및 AI 자동 분류 반영
def confirmed_label(manual, predicted, confirmation):
    if manual.strip():
        return manual.strip()

    if confirmation.strip().lower() in ("false", "0", "no"):
        return predicted.strip()

    return ""


for file_id, row in files.items():
    cls = classes.get(file_id, {})

    row["project"] = confirmed_label(
        row.get("project", "") or cls.get("manual_project", ""),
        cls.get("predicted_project", ""),
        cls.get("project_needs_confirmation", "")
    )

    row["role"] = confirmed_label(
        row.get("role", "") or cls.get("manual_role", ""),
        cls.get("predicted_role", ""),
        cls.get("role_needs_confirmation", "")
    )

    row["activity_at"] = pd.to_datetime(
        cls.get("activity_at", "") or row.get("modified_at", ""),
        errors="coerce"
    )

    path = row.get("path", "").replace("\\", "/")
    row["folder"] = str(Path(path).parent).casefold()


# 3. 기존 임베딩으로 파일 대표 벡터 생성
groups = defaultdict(list)

for chunk, vector in zip(info["chunks"], embeddings):
    groups[chunk["file_id"]].append(vector)

file_ids = list(files.keys())
vectors = {}

for file_id, chunks in groups.items():
    vector = np.mean(chunks, axis=0)
    norm = np.linalg.norm(vector)

    if norm > 0:
        vectors[file_id] = vector / norm


# 4. Role 연관성 규칙
role_groups = [
    {"강의자료", "실습 예제", "분석 예제", "코드"},
    {"과제 안내", "과제 실습", "코드", "실습 풀이"},
    {"단원 안내", "강의자료", "실습 예제"},
    {"코드", "실습 데이터", "분석 입력 데이터",
     "시각화 입력 데이터", "전처리 입력 데이터",
     "지역 조회 데이터", "실행 안내"},
    {"실습 시작 틀", "실습 풀이", "실습 데이터"},
    {"실습 예제", "실습 데이터"},
    {"분석 예제", "분석 입력 데이터"},
    {"실행 안내", "실습 시작 틀"}
]


def role_similarity(a, b):
    if not a or not b:
        return 0.0

    if a == b:
        return 0.5

    for group in role_groups:
        if a in group and b in group:
            return 1.0

    return 0.0


# 5. 작업 시간 연관성
def time_similarity(a, b):
    if pd.isna(a) or pd.isna(b):
        return 0.0

    days = abs((a - b).total_seconds()) / 86400

    if days <= 1:
        return 1.0
    if days <= 7:
        return 0.7
    if days <= 30:
        return 0.3

    return 0.0


# 6. Role03 직접 참조 관계
direct_refs = defaultdict(list)

for _, row in references.iterrows():
    if row["status"] != "resolved":
        continue

    source = row["source_id"]
    target = row["target_id"]

    if source == target:
        continue

    if source not in files or target not in files:
        continue

    path = row["reference_path"]

    direct_refs[(source, target)].append(
        f"파일 참조: {path}"
    )

    direct_refs[(target, source)].append(
        f"이 파일을 참조하는 자료: {path}"
    )


# 7. 모든 파일의 복합 관련성 계산
relations = []

for source_id in file_ids:
    source = files[source_id]
    candidates = []

    for target_id in file_ids:
        if source_id == target_id:
            continue

        target = files[target_id]
        reasons = []

        # 의미적 유사도
        semantic = 0.0

        if source_id in vectors and target_id in vectors:
            semantic = float(
                vectors[source_id] @ vectors[target_id]
            )
            semantic = float(np.clip(semantic, 0, 1))

            reasons.append(f"E5 유사도 {semantic:.4f}")

        # 동일 프로젝트
        project = float(
            bool(source["project"])
            and source["project"] == target["project"]
        )

        if project:
            reasons.append("동일 프로젝트")

        # Role 연관성
        role = role_similarity(
            source["role"], target["role"]
        )

        if role == 1.0:
            reasons.append("상호 보완적인 파일 역할")
        elif role == 0.5:
            reasons.append("동일 파일 역할")

        # 작업 시간
        time = time_similarity(
            source["activity_at"],
            target["activity_at"]
        )

        if time >= 0.7:
            reasons.append("작업 시기가 가까움")

        # 폴더
        folder = float(
            source["folder"] not in ("", ".")
            and source["folder"] == target["folder"]
        )

        if folder:
            reasons.append("동일 폴더")

        # 복합 관련성 점수
        score = (
            0.50 * semantic
            + 0.20 * project
            + 0.15 * role
            + 0.10 * time
            + 0.05 * folder
        )

        # 직접 참조 여부
        direct = (source_id, target_id) in direct_refs

        if direct:
            reasons = direct_refs[
                (source_id, target_id)
            ] + reasons

        if not direct and score < THRESHOLD:
            continue

        candidates.append({
            "source_file_id": source_id,
            "target_file_id": target_id,
            "source_filename": source["filename"],
            "target_filename": target["filename"],
            "relation_type": (
                "direct_reference" if direct
                else "context_related"
            ),
            "weight": score,
            "semantic_score": round(semantic, 4),
            "project_score": project,
            "role_score": role,
            "time_score": time,
            "folder_score": folder,
            "direct_reference": direct,
            "evidence": " / ".join(dict.fromkeys(reasons))
        })

    # 직접 참조 우선, 이후 복합 관련성 순서
    candidates.sort(
        key=lambda x: (
            x["direct_reference"], x["weight"]
        ),
        reverse=True
    )

    relations.extend(candidates[:TOP_K])


# 8. 결과 저장
columns = [
    "source_file_id", "target_file_id",
    "source_filename", "target_filename",
    "relation_type", "weight", "semantic_score",
    "project_score", "role_score", "time_score",
    "folder_score", "direct_reference", "evidence"
]

result = pd.DataFrame(relations, columns=columns)
result["weight"] = result["weight"].round(4)

output = BASE_DIR / "file_relations_v4.csv"
result.to_csv(output, index=False, encoding="utf-8-sig")

print(f"전체 파일: {len(files)}개")
print(f"임베딩 보유 파일: {len(vectors)}개")
print(f"관련 파일 관계: {len(result)}개")
print(result["relation_type"].value_counts())
print(f"저장 완료: {output}")