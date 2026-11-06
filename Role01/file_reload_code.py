
"""Role01/dataset/files -> Role01/metadata.csv 동기화.

실행: python file_reload_code.py

기능:
- 기존 파일의 file_id와 수동 라벨 보존
- 새 파일에만 새로운 file_id 부여
- 기존 파일 누락 시 저장 중단
- 변경 사항이 없으면 CSV 저장 생략
- 자동 백업 파일 생성하지 않음
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import re
import struct
import unicodedata
import zipfile

import pandas as pd


# 1. 기본 경로 설정
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dataset" / "files"
RAW_DATA_DIR = BASE_DIR.parent / "data" / "raw"
METADATA_CSV = BASE_DIR / "metadata.csv"

EXCLUDED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".webp", ".mp4", ".avi", ".mov"
}

EXCLUDED_FILENAMES = {
    ".DS_Store", ".Rhistory", "SOURCE.json", "LICENSE"
}

COLUMNS = [
    "file_id", "filename", "extension", "path",
    "size_bytes", "created_at", "modified_at",
    "project", "role", "description"
]


# 2. 경로 정규화
def norm(value):
    return (
        unicodedata.normalize("NFC", str(value))
        .replace("\\", "/")
        .strip()
        .casefold()
    )


def path_key(value):
    """기존 CSV의 경로를 dataset/files 기준으로 변환."""
    path = norm(value)
    marker = "dataset/files/"

    pos = path.rfind(marker)

    if pos >= 0:
        return path[pos + len(marker):]

    return path.lstrip("./")


# 3. 파일 생성일 및 수정일
def timestamp(value):
    return datetime.fromtimestamp(value).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def filesystem_created_at(file_path):
    stat = file_path.stat()

    if hasattr(stat, "st_birthtime"):
        return timestamp(stat.st_birthtime)

    if os.name == "nt":
        return timestamp(stat.st_ctime)

    return ""


# 4. ZIP 파일 내부의 NTFS 생성일 추출
def ntfs_created_at(extra):
    offset = 0

    while offset + 4 <= len(extra):
        field_id, size = struct.unpack_from(
            "<HH", extra, offset
        )
        offset += 4

        payload = extra[offset:offset + size]
        offset += size

        if field_id != 0x000A or len(payload) < 8:
            continue

        tag_offset = 4

        while tag_offset + 4 <= len(payload):
            tag, tag_size = struct.unpack_from(
                "<HH", payload, tag_offset
            )
            tag_offset += 4

            tag_payload = payload[
                tag_offset:tag_offset + tag_size
            ]
            tag_offset += tag_size

            if tag == 0x0001 and len(tag_payload) >= 24:
                created = struct.unpack_from(
                    "<Q", tag_payload, 16
                )[0]

                unix_seconds = (
                    created - 116444736000000000
                ) / 10_000_000

                try:
                    return timestamp(unix_seconds)
                except (
                    ValueError,
                    OverflowError,
                    OSError
                ):
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

    return (
        unicodedata.normalize("NFC", name)
        .replace("\\", "/")
    )


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

                    member = norm(
                        zip_member_name(info)
                    ).strip("/")

                    if member.startswith(group + "/"):
                        member = member[len(group) + 1:]

                    key = group + "/" + member
                    times[key] = created

        except (OSError, zipfile.BadZipFile) as exc:
            print(
                f"[경고] ZIP 읽기 실패: "
                f"{archive_path.name}: {exc}"
            )

    return times


# 5. 메타데이터 동기화
def main():
    print("실행 스크립트:", Path(__file__).resolve())
    print("탐색 폴더:", DATA_DIR.resolve())
    print("저장 CSV:", METADATA_CSV.resolve())

    if not DATA_DIR.is_dir():
        raise FileNotFoundError(
            f"탐색 폴더가 없습니다: {DATA_DIR}"
        )

    # 기존 메타데이터 읽기
    if METADATA_CSV.exists():
        old_df = pd.read_csv(
            METADATA_CSV,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig"
        )
    else:
        old_df = pd.DataFrame(columns=COLUMNS)

    for col in COLUMNS:
        if col not in old_df.columns:
            old_df[col] = ""

    # 기존 경로와 파일 ID 연결
    old_by_path = {}

    for record in old_df.to_dict("records"):
        key = path_key(record.get("path", ""))

        if not key:
            continue

        if key in old_by_path:
            raise ValueError(
                f"metadata.csv 중복 경로: {record['path']}"
            )

        old_by_path[key] = record

    # 기존 파일 ID 검사
    ids = [
        str(x).strip()
        for x in old_df["file_id"]
    ]

    if any(not x for x in ids):
        raise ValueError(
            "metadata.csv에 빈 file_id가 있습니다."
        )

    if len(ids) != len(set(ids)):
        raise ValueError(
            "metadata.csv에 중복 file_id가 있습니다."
        )

    # 기존 최대 번호 다음부터 신규 ID 부여
    numbers = []

    for file_id in ids:
        match = re.fullmatch(r"F(\d+)", file_id)

        if not match:
            raise ValueError(
                f"잘못된 file_id 형식: {file_id}"
            )

        numbers.append(int(match.group(1)))

    next_id = max(numbers, default=0) + 1

    # ZIP 생성일 정보
    zip_times = load_zip_creation_times()

    # 실제 파일 목록
    files = sorted(
        (
            p for p in DATA_DIR.rglob("*")
            if p.is_file()
        ),
        key=lambda p: norm(
            p.relative_to(DATA_DIR).as_posix()
        )
    )

    print(f"발견한 전체 파일: {len(files)}개")

    records = []
    new_count = 0
    changed_count = 0
    excluded_count = 0
    seen_keys = set()

    # 6. 파일별 메타데이터 생성
    for file_path in files:

        if (
            file_path.name in EXCLUDED_FILENAMES
            or file_path.name.startswith("~$")
            or file_path.suffix.lower()
            in EXCLUDED_EXTENSIONS
        ):
            excluded_count += 1
            continue

        rel = file_path.relative_to(
            DATA_DIR
        ).as_posix()

        key = norm(rel)

        if key in seen_keys:
            raise ValueError(
                f"정규화 후 중복 파일 경로: {rel}"
            )

        seen_keys.add(key)

        # 기존 파일이면 기존 데이터 사용
        old = old_by_path.get(key)

        if old:
            record = dict(old)
        else:
            record = {
                col: ""
                for col in old_df.columns
            }

            record["file_id"] = f"F{next_id:03d}"
            next_id += 1
            new_count += 1

            print(
                f"[신규] {record['file_id']} {rel}"
            )

        # 자동으로 갱신할 항목
        stat = file_path.stat()

        created = (
            zip_times.get(key)
            or str(
                record.get("created_at", "")
            ).strip()
            or filesystem_created_at(file_path)
        )

        new_data = {
            "filename": file_path.name,
            "extension": file_path.suffix.lower(),
            "path": file_path.relative_to(
                BASE_DIR
            ).as_posix(),
            "size_bytes": str(stat.st_size),
            "created_at": created,
            "modified_at": timestamp(stat.st_mtime),
        }

        # 기존 파일의 자동 항목 변경 확인
        if old and any(
            str(record.get(k, "")) != str(v)
            for k, v in new_data.items()
        ):
            changed_count += 1

        record.update(new_data)

        # 수동 라벨과 기존 file_id는 유지
        records.append(record)

    # 7. 기존 파일 누락 검사
    missing_keys = (
        set(old_by_path.keys()) - seen_keys
    )

    if missing_keys:
        print(
            "\n[경고] 기존 메타데이터에서 "
            "누락될 파일:"
        )

        for key in sorted(missing_keys):
            old = old_by_path[key]

            print(
                old["file_id"],
                old["filename"],
                old["path"]
            )

        raise RuntimeError(
            "기존 파일이 누락되어 CSV 저장을 중단합니다."
        )

    if not records:
        raise RuntimeError(
            "저장할 파일이 0개입니다. "
            "기존 CSV를 보호하기 위해 저장하지 않습니다."
        )

    # 8. 최종 데이터프레임 생성
    all_columns = list(
        dict.fromkeys(
            list(old_df.columns) + COLUMNS
        )
    )

    updated = pd.DataFrame(
        records,
        columns=all_columns
    )

    if updated["file_id"].duplicated().any():
        raise ValueError(
            "생성 결과에 중복 file_id가 있습니다."
        )

    # ID 숫자 기준 정렬 (ID 자체는 변경하지 않음)
    updated = updated.sort_values(
        by="file_id",
        key=lambda col: col.str.extract(
            r"(\d+)", expand=False
        ).astype(int)
    ).reset_index(drop=True)

    # 9. 변경 사항 확인
    # 기존 데이터와 완전히 같으면 저장하지 않음
    old_compare = old_df.reindex(
        columns=all_columns,
        fill_value=""
    ).reset_index(drop=True)

    if old_compare.equals(updated):
        print("\n[안내] 변경 사항이 없습니다.")
        print("metadata.csv를 다시 저장하지 않습니다.")
        print("백업 파일도 생성하지 않습니다.")
        return

    # 10. 원자적 저장
    # 임시 파일에 먼저 저장하고 교체
    temp_path = METADATA_CSV.with_name(
        METADATA_CSV.name + ".tmp"
    )

    try:
        updated.to_csv(
            temp_path,
            index=False,
            encoding="utf-8-sig"
        )

        os.replace(temp_path, METADATA_CSV)

    finally:
        if temp_path.exists():
            temp_path.unlink()

    # 11. 결과 출력
    print("\n=== 갱신 결과 ===")
    print("기존 CSV 행 수:", len(old_df))
    print("제외한 파일:", excluded_count)
    print("새로 등록한 파일:", new_count)
    print("기존 파일의 자동 항목 변경:", changed_count)
    print("최종 CSV 행 수:", len(updated))
    print("저장 완료:", METADATA_CSV.resolve())
    print("자동 백업 생성: 없음")

    if new_count == 0:
        print(
            "[안내] 새 파일이 0개입니다."
        )


if __name__ == "__main__":
    main()

