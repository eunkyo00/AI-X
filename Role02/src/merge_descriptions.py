from pathlib import Path
import pandas as pd

# 1. 파일 경로
role02_dir = Path(__file__).resolve().parent
project_dir = role02_dir.parent

original_path = project_dir / "Role01" / "metadata.csv"
generated_path = role02_dir / "metadata_description_progress.csv"
output_path = role02_dir / "metadata_description_merged.csv"

# 2. CSV 읽기
original = pd.read_csv(
    original_path, dtype=str, keep_default_na=False
)

generated = pd.read_csv(
    generated_path, dtype=str, keep_default_na=False
)

# 3. 파일 ID를 기준으로 생성된 설명 연결
description_map = generated.set_index("file_id")["description"].to_dict()

# 원본 복사
result = original.copy(deep=True)

filled_count = 0

# 4. 원본 description이 비어 있을 때만 채우기
for index, row in result.iterrows():

    file_id = row["file_id"]

    # 기존 설명은 절대 수정하지 않음
    if row["description"].strip():
        continue

    new_description = description_map.get(file_id, "")

    if new_description.strip():
        result.at[index, "description"] = new_description
        filled_count += 1

# 5. 기존 데이터 보존 검증
for col in original.columns:
    if col != "description":
        assert result[col].equals(original[col])

original_filled = original["description"].str.strip() != ""

assert result.loc[original_filled, "description"].equals(
    original.loc[original_filled, "description"]
)

# 6. 별도 CSV로 저장
result.to_csv(
    output_path,
    index=False,
    encoding="utf-8-sig"
)

print("병합 완료!")
print("새로 채운 description:", filled_count)
print("남은 빈 description:",
      result["description"].str.strip().eq("").sum())
print("저장 위치:", output_path)