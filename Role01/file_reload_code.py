from pathlib import Path
from datetime import datetime
import pandas as pd
import re
import shutil

# 1. 경로 설정
DATA_DIR = Path("dataset/files")
METADATA_CSV = Path("metadata.csv")

# 이미지와 영상은 검색 대상에서 제외
EXCLUDED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".webp", ".mp4", ".avi", ".mov"
}

# 기본적으로 관리할 자동 수집 항목
AUTO_COLUMNS = [
    "file_id",
    "filename",
    "extension",
    "path",
    "size_bytes",
    "created_at",
    "modified_at",
]


# 2. 파일 경로 비교용 함수
def normalize_path(path):
    return str(Path(str(path)).expanduser().resolve())

# 3. 기존 CSV 읽기
if not DATA_DIR.is_dir():
    raise FileNotFoundError(
        f"검색 대상 폴더를 찾을 수 없어: {DATA_DIR.resolve()}"
    )

if METADATA_CSV.exists():
    old_df = pd.read_csv(
        METADATA_CSV,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig"
    )
else:
    old_df = pd.DataFrame(columns=AUTO_COLUMNS + ["project", "role"])

# 기존 CSV에 필수 열이 없으면 추가
for column in AUTO_COLUMNS:
    if column not in old_df.columns:
        old_df[column] = ""

if "path" not in old_df.columns:
    old_df["path"] = ""

# 기존 파일 경로로 기존 정보를 찾을 수 있게 준비
old_by_path = {}

for record in old_df.to_dict("records"):
    if record.get("path", "").strip():
        old_by_path[normalize_path(record["path"])] = record

# 4. 다음에 사용할 파일 ID 결정
existing_numbers = []

for file_id in old_df["file_id"]:
    match = re.fullmatch(r"F(\d+)", str(file_id).strip())
    if match:
        existing_numbers.append(int(match.group(1)))

next_id = max(existing_numbers, default=0) + 1


# 5. 폴더를 다시 확인하고 정보 갱신
records = []
new_count = 0

for file_path in sorted(DATA_DIR.rglob("*")):

    if not file_path.is_file():
        continue

    # Excel이 만드는 임시 파일 제외
    if file_path.name.startswith("~$"):
        continue

    extension = file_path.suffix.lower()

    # 이미지/영상 제외
    if extension in EXCLUDED_EXTENSIONS:
        continue

    absolute_path = normalize_path(file_path)

    # 파일 경로를 기준으로 기존 정보 확인
    old_record = old_by_path.get(absolute_path, {})
    record = old_record.copy()

    # 기존 ID가 있으면 유지, 새 파일이면 ID 부여
    if not record.get("file_id", "").strip():
        record["file_id"] = f"F{next_id:03d}"
        next_id += 1
        new_count += 1

    stat = file_path.stat()

    # 자동 수집 항목만 갱신
    record.update({
        "filename": file_path.name,
        "extension": extension,
        "path": absolute_path,
        "size_bytes": stat.st_size,
        "created_at": datetime.fromtimestamp(
            stat.st_ctime
        ).strftime("%Y-%m-%d %H:%M:%S"),
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime
        ).strftime("%Y-%m-%d %H:%M:%S"),
    })

    # 직접 입력한 project, role 등은 기존 값 유지
    records.append(record)


# 6. 기존 정보를 백업하고 저장
columns = list(dict.fromkeys(
    list(old_df.columns) + AUTO_COLUMNS
))

updated_df = pd.DataFrame(records, columns=columns)

if METADATA_CSV.exists():
    backup_name = (
        "metadata_backup_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + ".csv"
    )
    shutil.copy2(METADATA_CSV, backup_name)
    print(f"기존 CSV 백업: {backup_name}")

updated_df.to_csv(
    METADATA_CSV,
    index=False,
    encoding="utf-8-sig"
)

print(f"\n총 파일 수: {len(updated_df)}")
print(f"새로 추가한 파일 수: {new_count}")
print(f"저장 완료: {METADATA_CSV.resolve()}")