import pandas as pd

metadata = pd.read_csv(
    "metadata.csv", dtype=str, keep_default_na=False,
    encoding="utf-8-sig"
)

extracted = pd.read_csv(
    "extracted_text.csv", dtype=str, keep_default_na=False,
    encoding="utf-8-sig"
)

df = pd.read_csv(
    "extracted_text.csv",
    encoding="utf-8-sig",
    dtype=str,
    keep_default_na=False
)

missing_ids = [
    "F001", "F016", "F088",
    "F095", "F104", "F105",
    "F108", "F153", "F156"
]

for fid in missing_ids:
    m = metadata[
        metadata["file_id"].str.strip() == fid
    ]
    e = extracted[
        extracted["file_id"].str.strip() == fid
    ]

    print(f"\n[{fid}]")

    if m.empty:
        print("metadata.csv: 없음")
    else:
        print("파일명:", m.iloc[0]["filename"])

    if e.empty:
        print("원인: extracted_text.csv에 없음")
    else:
        lengths = e["extracted_text"].str.strip().str.len()
        print("추출 텍스트 길이:", lengths.tolist())

        if (lengths == 0).all():
            print("원인: 추출 텍스트가 비어 있음")
        else:
            print("텍스트 존재: 검색 색인 생성 과정 확인 필요\n")

result = df[df["file_id"].isin(missing_ids)]

print(
    result[
        ["file_id", "filename", "char_count", "extraction_status"]
    ].to_string(index=False)
)