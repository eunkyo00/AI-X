"""프로젝트 분류기 v3로 파일 하나를 자동 분류한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sentence_transformers import SentenceTransformer

from project_classifier_v3 import (
    DEFAULT_DATA_CSV,
    DEFAULT_DESCRIPTION_CSV,
    DEFAULT_MODEL_PATH,
    FileText,
    encode_file_texts,
    row_to_file_text,
    score_embeddings,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="새 파일 프로젝트 자동 분류 v3")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATA_CSV)
    parser.add_argument("--descriptions", type=Path, default=DEFAULT_DESCRIPTION_CSV)
    parser.add_argument("--file-id", help="CSV에서 시험할 file_id")
    parser.add_argument("--filename", help="새 파일명")
    parser.add_argument("--extension", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--text", default="")
    parser.add_argument("--text-file", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_record(args: argparse.Namespace) -> FileText:
    if args.file_id:
        frame = pd.read_csv(
            args.csv, dtype=str, keep_default_na=False, encoding="utf-8-sig"
        )
        matches = frame[frame["file_id"].str.strip() == args.file_id.strip()]
        if matches.empty:
            raise ValueError(f"file_id를 찾을 수 없습니다: {args.file_id}")
        row = matches.iloc[0].to_dict()
        if not str(row.get("description", "")).strip() and args.descriptions.exists():
            descriptions = pd.read_csv(
                args.descriptions,
                dtype=str,
                keep_default_na=False,
                encoding="utf-8-sig",
            )
            description = descriptions.loc[
                descriptions["file_id"].str.strip() == args.file_id.strip(),
                "description",
            ]
            if not description.empty:
                row["description"] = description.iloc[0]
        return row_to_file_text(row)

    text = args.text
    if args.text_file:
        text = args.text_file.read_text(encoding="utf-8")
    if not args.filename:
        raise ValueError("--file-id 또는 --filename을 입력해야 합니다.")
    if not text.strip() and not args.description.strip():
        raise ValueError("--text, --text-file 또는 --description 중 하나가 필요합니다.")
    return FileText(
        filename=args.filename,
        extension=args.extension or Path(args.filename).suffix,
        description=args.description,
        extracted_text=text,
    )


def main() -> None:
    args = parse_args()
    if not args.model.exists():
        raise FileNotFoundError(
            f"학습 모델을 찾을 수 없습니다: {args.model}\n"
            "먼저 python train_project_classifier_v3.py 를 실행하세요."
        )
    artifact = joblib.load(args.model)
    record = load_record(args)
    model = SentenceTransformer(artifact["model_name"])
    embedding = encode_file_texts(
        model,
        [record],
        chunk_chars=int(artifact["chunk_chars"]),
        max_chunks=int(artifact["max_chunks"]),
        view_weights=artifact["view_weights"],
        show_progress_bar=False,
    )
    scores = score_embeddings(artifact, embedding)
    probabilities = scores.pop("probabilities")[0]
    failed_checks = [
        name.removeprefix("check_")
        for name, values in scores.items()
        if name.startswith("check_") and not bool(values[0])
    ]
    order = probabilities.argsort()[::-1]
    result = {
        "filename": record.filename,
        "project": str(scores["predicted_project"][0]),
        "is_new_project": not bool(scores["accepted_as_existing"][0]),
        "closest_existing_project": str(scores["closest_existing_project"][0]),
        "confidence": round(float(scores["confidence"][0]), 4),
        "probability_margin": round(float(scores["probability_margin"][0]), 4),
        "centroid_similarity": round(float(scores["centroid_similarity"][0]), 4),
        "centroid_margin": round(float(scores["centroid_margin"][0]), 4),
        "failed_checks": failed_checks,
        "top3": [
            {
                "project": str(artifact["classifier"].classes_[int(index)]),
                "confidence": round(float(probabilities[int(index)]), 4),
            }
            for index in order[:3]
        ],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"파일명: {result['filename']}")
    print(f"예측 프로젝트: {result['project']}")
    print(f"가장 가까운 기존 프로젝트: {result['closest_existing_project']}")
    print(f"신뢰도: {result['confidence']:.2%}")
    if result["is_new_project"]:
        print("판정: 기존 프로젝트와 충분히 가깝지 않아 새 과목으로 자동 분리")


if __name__ == "__main__":
    main()
