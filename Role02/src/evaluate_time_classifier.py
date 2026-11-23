"""metadata.csv 전체의 시간 분류 결과와 파싱 성공률을 저장한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from time_classifier import classify_time


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_METADATA = BASE_DIR.parent / "Role01" / "metadata.csv"
DEFAULT_OUTPUT_DIR = BASE_DIR / "time_classifier_artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="메타데이터 시간 분류 점검")
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata = pd.read_csv(
        args.metadata, dtype=str, keep_default_na=False, encoding="utf-8-sig"
    )
    rows = []
    for row in metadata.to_dict("records"):
        result = classify_time(
            modified_at=row.get("modified_at", ""),
            created_at=row.get("created_at", ""),
        )
        rows.append(
            {
                "file_id": row.get("file_id", ""),
                "filename": row.get("filename", ""),
                "project": row.get("project", ""),
                "created_at": row.get("created_at", ""),
                "modified_at": row.get("modified_at", ""),
                **result.to_dict(),
            }
        )

    results = pd.DataFrame(rows)
    classified = results["year_month"].astype(str).str.strip().ne("")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(
        args.output_dir / "time_classifier_results.csv",
        index=False,
        encoding="utf-8-sig",
    )
    summary = {
        "file_count": int(len(results)),
        "classified_count": int(classified.sum()),
        "unclassified_count": int((~classified).sum()),
        "classification_coverage": round(float(classified.mean()), 6),
        "source_counts": results["source"].value_counts().to_dict(),
        "rule": "activity_at > modified_at > created_at",
    }
    (args.output_dir / "time_classifier_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
