from pathlib import Path
import sys
import pandas as pd

# 1. 경로 설정
BASE_DIR = Path(__file__).resolve().parent
ROLE01_DIR = BASE_DIR.parent
PROJECT_DIR = ROLE01_DIR.parent
ROLE02_DIR = PROJECT_DIR / "Role02"

# 2. Role02의 time_classifier.py 불러오기
sys.path.insert(0, str(ROLE02_DIR))
from time_classifier import classify_time

# 3. CSV 경로
METADATA_CSV = ROLE01_DIR / "metadata.csv"
OUTPUT_CSV = ROLE01_DIR / "auto_time_results.csv"

# 2. 메타데이터 읽기
df = pd.read_csv(
    METADATA_CSV,
    dtype=str,
    keep_default_na=False,
    encoding="utf-8-sig"
)

results = []

# 3. 모든 파일의 시간 정보 분류
for _, row in df.iterrows():
    result = classify_time(
        modified_at=row["modified_at"],
        created_at=row["created_at"]
    )

    results.append({
        "file_id": row["file_id"],
        "filename": row["filename"],
        "activity_at": result.activity_at,
        "source": result.source,
        "year": result.year,
        "month": result.month,
        "year_month": result.year_month,
        "quarter": result.quarter,
        "half_year": result.half_year,
        "season": result.season,
        "needs_confirmation": result.needs_confirmation
    })

# 4. 결과 저장
result_df = pd.DataFrame(results)

result_df.to_csv(
    OUTPUT_CSV,
    index=False,
    encoding="utf-8-sig"
)

print("시간 자동 분류 완료!")
print("분류한 파일 수:", len(result_df))
print("저장 위치:", OUTPUT_CSV)
