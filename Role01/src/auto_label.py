
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer

# 1. 데이터 불러오기
from paths import BASE_DIR

metadata = pd.read_csv(
    BASE_DIR / "metadata.csv",
    encoding="utf-8-sig"
)

extracted = pd.read_csv(
    BASE_DIR / "extracted_text.csv",
    encoding="utf-8-sig"
)

# 2. 필요한 데이터 결합
df = metadata.merge(
    extracted[["file_id", "extracted_text"]],
    on="file_id",
    how="left"
)

df = df.fillna("")

# 3. 기존 라벨과 신규 파일 구분
labeled = df[df["project"].str.strip() != ""].copy()
unlabeled = df[df["project"].str.strip() == ""].copy()

# 4. 모델 불러오기
model = SentenceTransformer("intfloat/multilingual-e5-small")

# 5. 임베딩에 사용할 텍스트 생성
def make_text(row):
    content = str(row["extracted_text"])[:3000]
    return f"passage: {row['filename']}\n{content}"

# 6. 기존 파일 임베딩
labeled_texts = [
    make_text(row)
    for _, row in labeled.iterrows()
]

labeled_vectors = model.encode(
    labeled_texts,
    normalize_embeddings=True,
    show_progress_bar=True
)

# 7. 라벨 없는 파일 분류
results = []

for _, row in unlabeled.iterrows():

    new_text = make_text(row)

    new_vector = model.encode(
        [new_text],
        normalize_embeddings=True
    )[0]

    # 코사인 유사도
    similarities = labeled_vectors @ new_vector

    # 가장 유사한 파일 3개
    top_indices = np.argsort(similarities)[-3:][::-1]

    # 프로젝트별 유사도 합산
    scores = {}

    for idx in top_indices:
        project = labeled.iloc[idx]["project"]
        similarity = float(similarities[idx])

        scores[project] = scores.get(project, 0) + similarity

    predicted_project = max(scores, key=scores.get)

    results.append({
        "file_id": row["file_id"],
        "filename": row["filename"],
        "predicted_project": predicted_project,
        "similarity": round(float(similarities[top_indices[0]]), 4)
    })

# 8. 예측 결과 저장
result_df = pd.DataFrame(results)

result_df.to_csv(
    BASE_DIR / "auto_label_results.csv",
    index=False,
    encoding="utf-8-sig"
)

print(result_df.to_string(index=False))