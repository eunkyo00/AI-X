"""학습된 자료 유형 분류기로 새 파일의 role을 예측한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sentence_transformers import SentenceTransformer

from project_classifier import DEFAULT_DATA_CSV, FileText, encode_file_texts
from role_classifier import DEFAULT_MODEL_PATH, recognize_role_by_rule, row_to_role_file_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="새 파일 자료 유형 분류")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATA_CSV)
    parser.add_argument("--file-id")
    parser.add_argument("--filename")
    parser.add_argument("--extension", default="")
    parser.add_argument("--text", default="")
    parser.add_argument("--text-file", type=Path)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_record(args: argparse.Namespace) -> FileText:
    if args.file_id:
        df = pd.read_csv(args.csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        matches = df[df["file_id"].str.strip() == args.file_id.strip()]
        if matches.empty:
            raise ValueError(f"file_id를 찾을 수 없습니다: {args.file_id}")
        return row_to_role_file_text(matches.iloc[0].to_dict())

    if not args.filename:
        raise ValueError("--file-id 또는 --filename을 입력해야 합니다.")
    text = args.text
    if args.text_file:
        if not args.text_file.exists():
            raise FileNotFoundError(f"텍스트 파일을 찾을 수 없습니다: {args.text_file}")
        text = args.text_file.read_text(encoding="utf-8")
    return FileText(
        filename=args.filename,
        extension=args.extension or Path(args.filename).suffix,
        extracted_text=text,
        description="",
    )


def predict_role(record: FileText, artifact: dict, threshold: float | None = None) -> dict:
    rule = recognize_role_by_rule(record)
    if rule is not None:
        role, source = rule
        return {
            "filename": record.filename,
            "role": role,
            "closest_role": role,
            "confidence": 0.99,
            "confirmation_threshold": 0.0,
            "needs_confirmation": False,
            "method": "rule",
            "source": source,
            "top3": [{"role": role, "confidence": 0.99}],
        }

    classifier = artifact["classifier"]
    confirmation_threshold = (
        float(threshold)
        if threshold is not None
        else float(artifact["confirmation_threshold"])
    )
    model = SentenceTransformer(artifact["model_name"])
    embedding = encode_file_texts(
        model,
        [record],
        chunk_chars=int(artifact["chunk_chars"]),
        max_chunks=int(artifact["max_chunks"]),
        show_progress_bar=False,
    )
    probabilities = classifier.predict_proba(embedding)[0]
    order = probabilities.argsort()[::-1]
    best = int(order[0])
    confidence = float(probabilities[best])
    role = str(classifier.classes_[best])
    return {
        "filename": record.filename,
        "role": role if confidence >= confirmation_threshold else "미분류",
        "closest_role": role,
        "confidence": round(confidence, 4),
        "confirmation_threshold": round(confirmation_threshold, 4),
        "needs_confirmation": confidence < confirmation_threshold,
        "method": "embedding_classifier",
        "source": "e5+logistic_regression",
        "top3": [
            {
                "role": str(classifier.classes_[int(index)]),
                "confidence": round(float(probabilities[int(index)]), 4),
            }
            for index in order[:3]
        ],
    }


def main() -> None:
    args = parse_args()
    if not args.model.exists():
        raise FileNotFoundError(
            f"학습 모델을 찾을 수 없습니다: {args.model}\n"
            "먼저 python train_role_classifier.py 를 실행하세요."
        )
    if args.threshold is not None and not 0 <= args.threshold <= 1:
        raise ValueError("--threshold는 0 이상 1 이하여야 합니다.")
    result = predict_role(load_record(args), joblib.load(args.model), args.threshold)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"파일명: {result['filename']}")
    print(f"예측 자료 유형: {result['role']}")
    print(f"가장 가까운 유형: {result['closest_role']}")
    print(f"신뢰도: {result['confidence']:.2%}")
    print(f"사용자 확인 기준: {result['confirmation_threshold']:.2%}")
    if result["needs_confirmation"]:
        print("판정: 신뢰도가 낮아 사용자의 확인이 필요합니다.")
    print("상위 예측:")
    for item in result["top3"]:
        print(f"  - {item['role']}: {item['confidence']:.2%}")


if __name__ == "__main__":
    main()
