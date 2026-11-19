from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

from refresh_search import load_index

BASE_DIR = Path(__file__).resolve().parent
INDEX_DIR = BASE_DIR / "search_index"
OUTPUT_CSV = BASE_DIR / "file_relations_v3.csv"

TOP_K = 5
THRESHOLD = 0.80

# 1. 기존 검색 인덱스 불러오기
info, embeddings = load_index(INDEX_DIR)

# 2. 파일 ID별 임베딩 모으기
groups = defaultdict(list)
filenames = {}

for chunk, vector in zip(info["chunks"], embeddings):
    file_id = chunk["file_id"]

    groups[file_id].append(vector)
    filenames[file_id] = chunk["filename"]

# 3. 파일별 대표 벡터 계산
file_ids = list(groups.keys())
file_vectors = []

for file_id in file_ids:
    vector = np.mean(groups[file_id], axis=0)

    # L2 정규화
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm

    file_vectors.append(vector)

file_vectors = np.array(file_vectors)

# 4. 파일 간 코사인 유사도 계산
similarity = file_vectors @ file_vectors.T

# 5. 관련 파일 TOP 5 추출
relations = []

for i, source_id in enumerate(file_ids):
    candidates = []

    for j, target_id in enumerate(file_ids):
        if i == j:
            continue

        score = float(similarity[i, j])

        if score >= THRESHOLD:
            candidates.append((target_id, score))

    candidates.sort(key=lambda x: x[1], reverse=True)

    for target_id, score in candidates[:TOP_K]:
        relations.append({
            "source_file_id": source_id,
            "target_file_id": target_id,
            "source_filename": filenames[source_id],
            "target_filename": filenames[target_id],
            "relation_type": "semantic_related",
            "weight": round(score, 4),
            "evidence": f"E5 임베딩 유사도: {score:.4f}"
        })

# 6. 결과 저장
columns = [
    "source_file_id",
    "target_file_id",
    "source_filename",
    "target_filename",
    "relation_type",
    "weight",
    "evidence"
]

result = pd.DataFrame(relations, columns=columns)
result.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

print(f"전체 파일: {len(file_ids)}개")
print(f"관련 파일 관계: {len(result)}개")
print(f"저장 완료: {OUTPUT_CSV}")