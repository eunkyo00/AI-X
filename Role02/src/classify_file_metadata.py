"""새 파일의 작업 시간과 자료 유형을 한 번에 분류한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from classify_role import predict_role
from project_classifier import DEFAULT_DATA_CSV, FileText
from role_classifier import DEFAULT_MODEL_PATH, row_to_role_file_text
from time_classifier import classify_time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="새 파일 시간·자료 유형 자동 분류")
    parser.add_argument("--role-model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATA_CSV)
    parser.add_argument("--file-id")
    parser.add_argument("--filename")
    parser.add_argument("--path", default="")
    parser.add_argument("--extension", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--text", default="")
    parser.add_argument("--text-file", type=Path)
    parser.add_argument("--created-at", default="")
    parser.add_argument("--modified-at", default="")
    parser.add_argument("--activity-at", default="")
    parser.add_argument("--role-threshold", type=float)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_input(args: argparse.Namespace) -> tuple[FileText, dict[str, str]]:
    if args.file_id:
        df = pd.read_csv(args.csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        matches = df[df["file_id"].str.strip() == args.file_id.strip()]
        if matches.empty:
            raise ValueError(f"file_id를 찾을 수 없습니다: {args.file_id}")
        row = matches.iloc[0].to_dict()
        return row_to_role_file_text(row), {
            "path": str(row.get("path", "")),
            "description": str(row.get("description", "")),
            "created_at": str(row.get("created_at", "")),
            "modified_at": str(row.get("modified_at", "")),
            "activity_at": "",
        }

    if not args.filename:
        raise ValueError("--file-id 또는 --filename을 입력해야 합니다.")
    text = args.text
    if args.text_file:
        if not args.text_file.exists():
            raise FileNotFoundError(f"텍스트 파일을 찾을 수 없습니다: {args.text_file}")
        text = args.text_file.read_text(encoding="utf-8")
    record = FileText(
        filename=args.filename,
        extension=args.extension or Path(args.filename).suffix,
        description="",
        extracted_text=text,
    )
    return record, {
        "path": args.path,
        "description": args.description,
        "created_at": args.created_at,
        "modified_at": args.modified_at,
        "activity_at": args.activity_at,
    }


def main() -> None:
    args = parse_args()
    if not args.role_model.exists():
        raise FileNotFoundError(f"자료 유형 모델을 찾을 수 없습니다: {args.role_model}")
    record, context = load_input(args)
    role_result = predict_role(
        record,
        joblib.load(args.role_model),
        threshold=args.role_threshold,
    )
    time_result = classify_time(
        activity_at=context["activity_at"],
        modified_at=context["modified_at"],
        created_at=context["created_at"],
    )
    result = {
        "filename": record.filename,
        "time": time_result.to_dict(),
        "role": role_result,
        "needs_confirmation": (
            time_result.needs_confirmation or role_result["needs_confirmation"]
        ),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"파일명: {record.filename}")
    print(f"작업 월: {time_result.month_label}")
    print(f"자료 유형: {role_result['role']} ({role_result['confidence']:.2%})")
    print(f"사용자 확인 필요: {'예' if result['needs_confirmation'] else '아니요'}")


if __name__ == "__main__":
    main()
