from pathlib import Path
from datetime import datetime
import pandas as pd
import os
import re
import shutil
import struct
import unicodedata
import zipfile
from paths import path_key

# 1. 경로 설정
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "dataset/files"
RAW_DATA_DIR = SCRIPT_DIR.parent / "data/raw"
METADATA_CSV = SCRIPT_DIR / "metadata.csv"

# 이미지와 영상은 검색 대상에서 제외
EXCLUDED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".webp", ".mp4", ".avi", ".mov"
}

EXCLUDED_FILENAMES = {
    ".DS_Store",
    ".Rhistory",
    "SOURCE.json",
    "LICENSE",
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
    return path_key(path)


def format_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def filesystem_created_at(file_path):
    """현재 파일시스템이 실제 생성 시각을 제공할 때만 반환한다."""
    stat = file_path.stat()

    # macOS: st_birthtime이 파일 생성 시각이다.
    if hasattr(stat, "st_birthtime"):
        return format_timestamp(stat.st_birthtime)

    # Windows: st_ctime이 파일 생성 시각이다.
    if os.name == "nt":
        return format_timestamp(stat.st_ctime)

    # Linux 등에서는 st_ctime이 생성 시각이 아니므로 사용하지 않는다.
    return ""


def decode_zip_name(name, utf8_flag):
    if utf8_flag:
        return unicodedata.normalize("NFC", name)

    raw_name = name.encode("cp437")
    for encoding in ("cp949", "utf-8"):
        try:
            return unicodedata.normalize("NFC", raw_name.decode(encoding))
        except UnicodeDecodeError:
            continue
    return unicodedata.normalize("NFC", name)


def ntfs_created_at(extra):
    """ZIP의 NTFS 확장 정보에 보존된 생성 시각을 읽는다."""
    offset = 0
    while offset + 4 <= len(extra):
        field_id, field_size = struct.unpack_from("<HH", extra, offset)
        offset += 4
        payload = extra[offset:offset + field_size]
        offset += field_size

        if field_id != 0x000A or len(payload) < 8:
            continue

        tag_offset = 4
        while tag_offset + 4 <= len(payload):
            tag, tag_size = struct.unpack_from("<HH", payload, tag_offset)
            tag_offset += 4
            tag_payload = payload[tag_offset:tag_offset + tag_size]
            tag_offset += tag_size

            if tag == 0x0001 and len(tag_payload) >= 24:
                _, _, created = struct.unpack_from("<QQQ", tag_payload)
                unix_timestamp = (
                    created - 116444736000000000
                ) / 10_000_000
                return format_timestamp(unix_timestamp)

    return ""


def load_raw_created_times():
    """data/raw의 ZIP이 보존한 파일별 생성 시각을 경로별로 불러온다."""
    created_by_key = {}
    if not RAW_DATA_DIR.is_dir():
        return created_by_key

    groups = {unicodedata.normalize("NFC", folder.name)
              for folder in DATA_DIR.iterdir() if folder.is_dir()}
    for archive_path in sorted(RAW_DATA_DIR.glob("*.zip")):
        group = unicodedata.normalize("NFC", archive_path.stem)
        if group not in groups:
            continue

        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue

                created_at = ntfs_created_at(info.extra)
                if not created_at:
                    continue

                member = decode_zip_name(
                    info.filename,
                    bool(info.flag_bits & 0x800),
                ).replace("\\", "/")
                parts = [part for part in member.split("/") if part]
                if parts and unicodedata.normalize("NFC", parts[0]) == group:
                    parts = parts[1:]

                relative_path = unicodedata.normalize("NFC", "/".join(parts))
                filename = unicodedata.normalize("NFC", Path(member).name)
                created_by_key[(group, relative_path)] = created_at
                created_by_key.setdefault((group, filename), created_at)

    return created_by_key


RAW_CREATED_AT = load_raw_created_times()

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
    old_df = pd.DataFrame(columns=AUTO_COLUMNS + ["project", "role", "description"])

# 기존 CSV에 필수 열이 없으면 추가
for column in AUTO_COLUMNS + ["project", "role", "description"]:
    if column not in old_df.columns:
        old_df[column] = ""

if "path" not in old_df.columns:
    old_df["path"] = ""

# 기존 파일 경로로 기존 정보를 찾을 수 있게 준비
old_by_path = {}

for record in old_df.to_dict("records"):
    if record.get("path", "").strip():
        key = normalize_path(record["path"])
        if key in old_by_path:
            raise ValueError(f"중복된 파일 경로: {record['path']}")
        old_by_path[key] = record

ids = [str(value).strip() for value in old_df["file_id"]]
if any(not value for value in ids) or len(ids) != len(set(ids)):
    raise ValueError("기존 metadata.csv에 빈 ID 또는 중복 ID가 있습니다.")

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

    if file_path.name in EXCLUDED_FILENAMES:
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
    for column in old_df.columns:
        record.setdefault(column, "")

    # 기존 ID가 있으면 유지, 새 파일이면 ID 부여
    if not record.get("file_id", "").strip():
        record["file_id"] = f"F{next_id:03d}"
        next_id += 1
        new_count += 1

    stat = file_path.stat()
    relative_path = file_path.relative_to(DATA_DIR)
    group = unicodedata.normalize("NFC", relative_path.parts[0])
    path_in_group = unicodedata.normalize(
        "NFC",
        "/".join(relative_path.parts[1:]),
    )
    filename = unicodedata.normalize("NFC", file_path.name)

    raw_created_at = (
        RAW_CREATED_AT.get((group, path_in_group))
        or RAW_CREATED_AT.get((group, filename))
    )
    existing_created_at = str(record.get("created_at", "")).strip()
    created_at = (
        raw_created_at
        or existing_created_at
        or filesystem_created_at(file_path)
    )

    stored_path = record.get("path", "").strip()
    if not stored_path:
        stored_path = file_path.relative_to(SCRIPT_DIR).as_posix()

    # 자동 수집 항목만 갱신
    record.update({
        "filename": file_path.name,
        "extension": extension,
        "path": file_path.relative_to(SCRIPT_DIR).as_posix(),
        "size_bytes": stat.st_size,
        "created_at": created_at,
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
    backup_name = SCRIPT_DIR / (
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
