"""Role01/dataset/files -> Role01/metadata.csv 동기화.

실행: python file_reload_append_only.py
기존 메타데이터의 수동 라벨과 file_id를 경로 기준으로 보존합니다.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import re
import shutil
import struct
import unicodedata
import zipfile

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dataset" / "files"
RAW_DATA_DIR = BASE_DIR.parent / "data" / "raw"
METADATA_CSV = BASE_DIR / "metadata.csv"

EXCLUDED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".mp4", ".avi", ".mov"}
EXCLUDED_FILENAMES = {".DS_Store", ".Rhistory", "SOURCE.json", "LICENSE"}
COLUMNS = ["file_id", "filename", "extension", "path", "size_bytes", "created_at", "modified_at", "project", "role", "description"]


def norm(value):
    return unicodedata.normalize("NFC", str(value)).replace("\\", "/").strip().casefold()


def path_key(value):
    """절대/상대 경로 모두 dataset/files 아래 경로로 정규화."""
    path = norm(value)
    marker = "dataset/files/"
    pos = path.rfind(marker)
    if pos >= 0:
        return path[pos + len(marker):]
    return path.lstrip("./")


def timestamp(value):
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def filesystem_created_at(file_path):
    stat = file_path.stat()
    if hasattr(stat, "st_birthtime"):
        return timestamp(stat.st_birthtime)
    if os.name == "nt":
        return timestamp(stat.st_ctime)
    return ""


def ntfs_created_at(extra):
    """ZIP NTFS 확장 필드의 생성 시각(존재할 때만)."""
    offset = 0
    while offset + 4 <= len(extra):
        field_id, size = struct.unpack_from("<HH", extra, offset)
        offset += 4
        payload = extra[offset:offset + size]
        offset += size
        if field_id != 0x000A or len(payload) < 8:
            continue
        tag_offset = 4
        while tag_offset + 4 <= len(payload):
            tag, tag_size = struct.unpack_from("<HH", payload, tag_offset)
            tag_offset += 4
            tag_payload = payload[tag_offset:tag_offset + tag_size]
            tag_offset += tag_size
            if tag == 0x0001 and len(tag_payload) >= 24:
                # NTFS timestamp order: modified, accessed, created
                created = struct.unpack_from("<Q", tag_payload, 16)[0]
                unix_seconds = (created - 116444736000000000) / 10_000_000
                try:
                    return timestamp(unix_seconds)
                except (ValueError, OverflowError, OSError):
                    return ""
    return ""


def zip_member_name(info):
    name = info.filename
    if not (info.flag_bits & 0x800):
        raw = name.encode("cp437", errors="replace")
        for encoding in ("cp949", "utf-8"):
            try:
                name = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
    return unicodedata.normalize("NFC", name).replace("\\", "/")


def load_zip_creation_times():
    times = {}
    if not RAW_DATA_DIR.is_dir():
        return times
    for archive_path in sorted(RAW_DATA_DIR.glob("*.zip")):
        group = norm(archive_path.stem)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    created = ntfs_created_at(info.extra)
                    if not created:
                        continue
                    member = norm(zip_member_name(info)).strip("/")
                    if member.startswith(group + "/"):
                        member = member[len(group) + 1:]
                    key = group + "/" + member
                    times[key] = created
        except (OSError, zipfile.BadZipFile) as exc:
            print(f"[경고] ZIP 읽기 실패: {archive_path.name}: {exc}")
    return times


def main():
    print("실행 스크립트:", Path(__file__).resolve())
    print("탐색 폴더:", DATA_DIR.resolve())
    print("저장 CSV:", METADATA_CSV.resolve())
    if not DATA_DIR.is_dir():
        raise FileNotFoundError(f"탐색 폴더가 없습니다: {DATA_DIR}")

    if METADATA_CSV.exists():
        old_df = pd.read_csv(METADATA_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    else:
        old_df = pd.DataFrame(columns=COLUMNS)
    for col in COLUMNS:
        if col not in old_df.columns:
            old_df[col] = ""

    old_by_path = {}
    for record in old_df.to_dict("records"):
        key = path_key(record.get("path", ""))
        if not key:
            continue
        if key in old_by_path:
            raise ValueError(f"metadata.csv 중복 경로: {record['path']}")
        old_by_path[key] = record

    ids = [str(x).strip() for x in old_df["file_id"]]
    if any(not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("metadata.csv에 빈 file_id 또는 중복 file_id가 있습니다.")
    next_id = max([int(m.group(1)) for x in ids if (m := re.fullmatch(r"F(\d+)", x))] or [0]) + 1

    zip_times = load_zip_creation_times()
    files = sorted((p for p in DATA_DIR.rglob("*") if p.is_file()), key=lambda p: norm(p.relative_to(DATA_DIR)))
    print(f"발견한 전체 파일: {len(files)}개")

    records = []
    new_count = 0
    changed_count = 0
    excluded_count = 0
    seen_keys = set()
    for file_path in files:
        if file_path.name in EXCLUDED_FILENAMES or file_path.name.startswith("~$") or file_path.suffix.lower() in EXCLUDED_EXTENSIONS:
            excluded_count += 1
            continue

        rel = file_path.relative_to(DATA_DIR).as_posix()
        key = norm(rel)
        if key in seen_keys:
            raise ValueError(f"정규화 후 중복 파일 경로: {rel}")
        seen_keys.add(key)
        old = old_by_path.get(key)
        record = dict(old) if old else {col: "" for col in old_df.columns}
        if old is None:
            record["file_id"] = f"F{next_id:03d}"
            next_id += 1
            new_count += 1
            print(f"[신규] {record['file_id']} {rel}")

        stat = file_path.stat()
        created = (zip_times.get(key) or str(record.get("created_at", "")).strip()
                   or filesystem_created_at(file_path))
        new_data = {
            "filename": file_path.name,
            "extension": file_path.suffix.lower(),
            "path": file_path.relative_to(BASE_DIR).as_posix(),
            "size_bytes": str(stat.st_size),
            "created_at": created,
            "modified_at": timestamp(stat.st_mtime),
        }
        if old and any(str(record.get(k, "")) != str(v) for k, v in new_data.items()):
            changed_count += 1
        record.update(new_data)
        # project / role / description 및 그 밖의 기존 수동 열은 수정하지 않음
        records.append(record)

    if not records:
        raise RuntimeError("저장할 파일이 0개입니다. 기존 CSV를 보호하기 위해 저장하지 않습니다.")

    all_columns = list(dict.fromkeys(list(old_df.columns) + COLUMNS))
    updated = pd.DataFrame(records, columns=all_columns)

    # 기존 ID는 유지하고 CSV 행 순서만 F001, F002, ... 순서로 정렬
    id_numbers = updated["file_id"].str.extract(r"^F(\d+)$")[0]
    if id_numbers.isna().any():
        raise ValueError("F001 형식이 아닌 file_id가 있습니다. 저장을 중단합니다.")
    updated["_sort_id"] = id_numbers.astype(int)
    updated = updated.sort_values("_sort_id").drop(columns=["_sort_id"]).reset_index(drop=True)

    if updated["file_id"].duplicated().any():
        raise ValueError("생성 결과에 중복 file_id가 있습니다. 저장을 중단합니다.")

    # 원자적 저장: 임시 파일에 기록 후 교체
    temp_path = METADATA_CSV.with_name(METADATA_CSV.name + ".tmp")
    updated.to_csv(temp_path, index=False, encoding="utf-8-sig")
    try:
        if METADATA_CSV.exists():
            backup_path = BASE_DIR / f"metadata_backup_{datetime.now():%Y%m%d_%H%M%S_%f}.csv"
            shutil.copy2(METADATA_CSV, backup_path)
            print("백업:", backup_path.name)
        os.replace(temp_path, METADATA_CSV)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    print("\n=== 갱신 결과 ===")
    print("기존 CSV 행 수:", len(old_df))
    print("제외한 파일:", excluded_count)
    print("새로 등록한 파일:", new_count)
    print("기존 파일의 자동 항목 변경:", changed_count)
    print("최종 CSV 행 수:", len(updated))
    print("저장 완료:", METADATA_CSV.resolve())
    if new_count == 0:
        print("[안내] 새 파일이 0개입니다. 위 탐색 폴더에 새 파일이 실제로 있는지 확인하세요.")


if __name__ == "__main__":
    main()