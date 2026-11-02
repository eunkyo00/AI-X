"""파일 시각을 검색에 사용할 연·월 단위 시간 정보로 변환한다."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeResult:
    activity_at: str
    source: str
    year: int | None
    month: int | None
    year_month: str
    month_label: str
    quarter: str
    half_year: str
    season: str
    needs_confirmation: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace(".", "-").replace("/", "-")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        match = re.match(
            r"^(\d{4})-(\d{1,2})-(\d{1,2})"
            r"(?:[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?$",
            normalized,
        )
        if not match:
            return None
        parts = [int(value or 0) for value in match.groups()]
        try:
            return datetime(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])
        except ValueError:
            return None


def _season(month: int) -> str:
    if month in (3, 4, 5):
        return "봄"
    if month in (6, 7, 8):
        return "여름"
    if month in (9, 10, 11):
        return "가을"
    return "겨울"


def classify_time(
    *,
    activity_at: str = "",
    modified_at: str = "",
    created_at: str = "",
) -> TimeResult:
    """명시 시각 > 수정 시각 > 생성 시각 순으로 작업 시점을 선택한다.

    일반적으로 파일의 생성 시각은 다운로드·복사 시점일 수 있어, 사용자가
    실제로 작업한 달을 찾을 때는 수정 시각을 우선한다.
    """
    candidates = (
        ("activity_at", activity_at),
        ("modified_at", modified_at),
        ("created_at", created_at),
    )
    for source, value in candidates:
        parsed = parse_datetime(value)
        if parsed is None:
            continue
        month = parsed.month
        return TimeResult(
            activity_at=parsed.isoformat(sep=" ", timespec="seconds"),
            source=source,
            year=parsed.year,
            month=month,
            year_month=f"{parsed.year:04d}-{month:02d}",
            month_label=f"{parsed.year}년 {month}월",
            quarter=f"{(month - 1) // 3 + 1}분기",
            half_year="상반기" if month <= 6 else "하반기",
            season=_season(month),
            needs_confirmation=False,
        )

    return TimeResult(
        activity_at="",
        source="none",
        year=None,
        month=None,
        year_month="",
        month_label="미분류",
        quarter="",
        half_year="",
        season="",
        needs_confirmation=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="파일 작업 시점 분류")
    parser.add_argument("--activity-at", default="")
    parser.add_argument("--modified-at", default="")
    parser.add_argument("--created-at", default="")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = classify_time(
        activity_at=args.activity_at,
        modified_at=args.modified_at,
        created_at=args.created_at,
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    print(f"작업 시점: {result.activity_at or '미분류'}")
    print(f"월 분류: {result.month_label}")
    if result.year is not None:
        print(f"분기: {result.quarter}")
        print(f"반기: {result.half_year}")
        print(f"계절: {result.season}")
    print(f"기준 시각: {result.source}")


if __name__ == "__main__":
    main()
