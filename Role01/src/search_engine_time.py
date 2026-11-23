"""시간 조건 + 파일 단위 의미 검색 엔진.

기존 search_engine.py를 수정하지 않고 SearchEngine을 상속한다.
metadata.csv의 created_at / modified_at을 이용한다.
"""
from datetime import datetime, timedelta
from calendar import monthrange
import re

import pandas as pd

from search_engine import SearchEngine, TOP_K


def parse_datetime(value):
    """2026-10-02 14:53:20, 2026.4.10 18:31 등의 날짜를 처리한다."""
    value = str(value).strip()
    if not value:
        return None
    # 구분자를 통일해 pandas의 혼합 형식 추론 문제를 피한다.
    value = re.sub(r"(?<=\d)\.(?=\d)", "-", value)
    try:
        result = pd.to_datetime(value, errors="coerce")
        if pd.isna(result):
            return None
        return result.to_pydatetime().replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        return None


def month_start(year, month):
    return datetime(year, month, 1)


def shift_month(year, month, delta):
    month_index = year * 12 + month - 1 + delta
    return month_start(month_index // 12, month_index % 12 + 1)


def parse_time_query(query, now=None):
    """시간 조건을 분석해 (의미검색어, 조건)으로 반환한다.

    조건은 {column, start, end} 형태이며 start <= 날짜 < end로 비교한다.
    지원하지 않는 시간 표현은 일반 의미 검색어로 남긴다.
    """
    now = now or datetime.now()
    text = str(query).strip()
    column = "created_at" if re.search(r"(생성|만든|만들어진|작성|저장한|생긴)", text) else "modified_at"

    start = end = None
    matched = None

    # 정확한 연월일: 2026년 9월 12일
    pattern_day = r"(?<!\d)(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"
    m = re.search(pattern_day, text)
    if m:
        try:
            start = datetime(int(m[1]), int(m[2]), int(m[3]))
            end = start + timedelta(days=1)
            matched = m.group()
        except ValueError:
            pass

    # 연월: 2026년 9월
    if start is None:
        m = re.search(r"(?<!\d)(\d{4})\s*년\s*(\d{1,2})\s*월", text)
        if m:
            try:
                start = month_start(int(m[1]), int(m[2]))
                end = shift_month(start.year, start.month, 1)
                matched = m.group()
            except ValueError:
                pass

    # 상대적 월은 달력 기준: 지난달 = 전월 1일~이번달 1일
    if start is None:
        relative_months = {"이번 달": 0, "이번달": 0, "지난 달": -1, "지난달": -1,
                           "저번 달": -1, "저번달": -1, "지지난달": -2}
        for phrase in sorted(relative_months, key=len, reverse=True):
            if phrase in text:
                start = shift_month(now.year, now.month, relative_months[phrase])
                end = shift_month(start.year, start.month, 1)
                matched = phrase
                break

    # 최근 N일/주일: 현재 시각 기준 이전 N일
    if start is None:
        m = re.search(r"(?:최근|지난)\s*(\d+)\s*(일|주일|주|개월)\s*(?:동안|간)?", text)
        if m:
            n = int(m[1])
            unit = m[2]
            if 0 < n <= 3650:
                if unit == "개월":
                    base = shift_month(now.year, now.month, -n)
                    day = min(now.day, monthrange(base.year, base.month)[1])
                    start = base.replace(day=day, hour=now.hour, minute=now.minute, second=now.second)
                else:
                    start = now - timedelta(days=n * (7 if unit in ("주", "주일") else 1))
                end = now + timedelta(microseconds=1)
                matched = m.group()

    if start is None:
        for phrase, days in (("어제", 1), ("오늘", 0)):
            if phrase in text:
                start = datetime(now.year, now.month, now.day) - timedelta(days=days)
                end = start + timedelta(days=1)
                matched = phrase
                break

    # '최근에 수정한' 등은 기본적으로 최근 30일로 처리
    if start is None and re.search(r"최근(?:에)?", text):
        start = now - timedelta(days=30)
        end = now + timedelta(microseconds=1)
        matched = re.search(r"최근(?:에)?", text).group()

    if start is None:
        return text, None

    # 시간 표현과 날짜를 가리키는 동사만 제거해 의미 검색어를 남긴다.
    semantic = text.replace(matched, " ", 1)
    semantic = re.sub(r"(수정한|수정된|수정했던|만든|만들어진|생성한|생성된|작성한|저장한|편집한|작업한)", " ", semantic)
    semantic = re.sub(r"\s+", " ", semantic).strip()
    return semantic, {"column": column, "start": start, "end": end}


class TimeSearchEngine(SearchEngine):
    """기존 의미 검색 결과 전체에 시간 조건을 적용한다."""

    def search_files(self, query, top_k=TOP_K, now=None):
        if not str(query).strip() or top_k <= 0:
            return []
        semantic_query, time_filter = parse_time_query(query, now=now)
        if time_filter is None:
            return super().search_files(query, top_k=top_k)

        # 모든 파일의 유사도를 계산한 다음 시간 필터를 적용해야
        # 의미 검색 Top 5 바깥에 있던 정답도 찾을 수 있다.
        search_query = semantic_query if semantic_query else query
        all_results = super().search_files(search_query, top_k=len(self.df))

        date_column = time_filter["column"]
        if date_column not in self.df.columns:
            raise ValueError(f"metadata.csv에 '{date_column}' 열이 없습니다.")

        dates = {}
        for _, row in self.df.iterrows():
            dates[str(row["file_id"])] = parse_datetime(row[date_column])

        filtered = []
        for result in all_results:
            file_date = dates.get(str(result["file_id"]))
            if file_date is None:
                continue
            if time_filter["start"] <= file_date < time_filter["end"]:
                result = dict(result)
                result[date_column] = file_date.strftime("%Y-%m-%d %H:%M:%S")
                filtered.append(result)
                if len(filtered) >= top_k:
                    break
        return filtered


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = TimeSearchEngine()
    return _engine


def search_files(query, top_k=TOP_K):
    return get_engine().search_files(query, top_k=top_k)


if __name__ == "__main__":
    engine = get_engine()
    print("\n시간 기반 검색 테스트 (종료: q)")
    while True:
        query = input("검색어: ").strip()
        if query.lower() in ("q", "quit", "exit"):
            break
        semantic, condition = parse_time_query(query)
        if condition:
            print(f"시간 조건: {condition['column']} / {condition['start']} ~ {condition['end']}")
            print(f"의미 검색어: {semantic or '(원본 검색어 사용)'}")
        results = engine.search_files(query)
        if not results:
            print("조건에 맞는 파일이 없습니다.")
        for rank, result in enumerate(results, 1):
            print(f"{rank}. {result['filename']} ({result['file_id']}): {result['score']:.4f}")
