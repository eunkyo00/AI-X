import pandas as pd

df = pd.read_csv(
    "extracted_text.csv",
    encoding="utf-8-sig",
    keep_default_na=False
)

failed_ids = [
    "F019", "F020", "F021", "F022", "F023",
    "F024", "F030", "F036", "F040", "F043",
    "F045", "F046", "F048"
]

result = df[df["file_id"].isin(failed_ids)].copy()

print("\n=== 검색 실패 R 파일 분석 ===\n")

for _, row in result.iterrows():
    text = str(row["extracted_text"])

    print(f"파일 ID: {row['file_id']}")
    print(f"파일명: {row['filename']}")
    print(f"추출 상태: {row['extraction_status']}")
    print(f"글자 수: {row['char_count']}")
    print(f"코드 줄 수: {len(text.splitlines())}")
    print("-" * 45)

print(f"\n확인된 파일 수: {len(result)}/{len(failed_ids)}")