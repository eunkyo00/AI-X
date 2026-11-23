
from pathlib import Path
import pandas as pd
import description_generator as dg

# 1. 테스트 폴더 설정
project = Path(__file__).resolve().parent.parent
test_dir = project / "Role02" / "test_output"
test_dir.mkdir(exist_ok=True)

# 2. 기존 데이터 읽기
metadata = dg.read_csv(dg.METADATA_PATH)
extracted = dg.read_csv(dg.TEXT_PATH)

# 3. 테스트 파일 1개 추가
new_id = "TEST_NEW_001"

assert new_id not in metadata["file_id"].values
assert new_id not in extracted["file_id"].values

new_row = {col: "" for col in metadata.columns}
new_row["file_id"] = new_id
new_row["filename"] = "student_score_analysis.py"
new_row["description"] = ""

metadata = pd.concat(
    [metadata, pd.DataFrame([new_row])],
    ignore_index=True
)

new_text = {col: "" for col in extracted.columns}
new_text["file_id"] = new_id
new_text["extracted_text"] = """
import pandas as pd

df = pd.read_csv("student_scores.csv")
print(df.describe())
print("평균:", df["score"].mean())
"""

extracted = pd.concat(
    [extracted, pd.DataFrame([new_text])],
    ignore_index=True
)

# 4. 테스트 결과 저장 경로로 변경
dg.OUTPUT_PATH = test_dir / "metadata_description_generated.csv"

# 5. 기존 description 재사용
result = dg.merge_existing_descriptions(metadata)
before = result.copy(deep=True)

# 6. 빈 description만 생성
result = dg.fill_descriptions(result, extracted)

# 7. 기존 데이터가 유지되었는지 검사
assert len(result) == len(metadata)
assert result.loc[
    result["file_id"] != new_id, "description"
].equals(
    before.loc[
        before["file_id"] != new_id, "description"
    ]
)

# 8. 신규 파일 description 확인
new_description = result.loc[
    result["file_id"] == new_id, "description"
].iloc[0]

assert new_description.strip(), "신규 description 생성 실패"

# 9. 테스트 결과 저장
dg.save_result(result)

print("\n통합 테스트 성공!")
print("전체 파일:", len(result))
print("신규 description:", new_description)
print("저장 위치:", dg.OUTPUT_PATH)
