from pathlib import Path
import pymupdf
import pandas as pd

df = pd.read_csv(
    "extracted_text.csv",
    dtype=str,
    keep_default_na=False,
    encoding="utf-8-sig"
)

target_ids = ["F095", "F104", "F105", "F108"]

for fid in target_ids:
    row = df[df["file_id"] == fid].iloc[0]
    path = Path(row["path"])

    print(f"\n[{fid}] {path.name}")

    with pymupdf.open(path) as pdf:
        print("전체 페이지:", len(pdf))

        for i, page in enumerate(pdf):
            if i >= 3:
                break

            text = page.get_text()
            images = page.get_images(full=True)

            print(
                f"페이지 {i+1}: "
                f"텍스트 {len(text)}자, "
                f"이미지 {len(images)}개"
            )
