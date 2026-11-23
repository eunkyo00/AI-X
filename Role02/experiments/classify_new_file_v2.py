"""학습된 프로젝트 분류기로 새 파일의 과목을 예측한다.

기존 CSV 행 시험:
    python classify_new_file.py --file-id F001

새 파일의 추출 텍스트 시험:
    python classify_new_file.py --filename new.pdf --text-file new.txt
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sentence_transformers import SentenceTransformer

from project_classifier_v2 import (
    DEFAULT_DATA_CSV,
    DEFAULT_ARTIFACT_DIR,
    FileText,
    encode_file_texts,
    row_to_file_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="새 파일 프로젝트 분류")
    parser.add_argument(
       "--model",
       type=Path,
       default=DEFAULT_ARTIFACT_DIR.parent
       / "project_classifier_artifacts_v2"
       / "project_classifier_v2.joblib",
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_DATA_CSV)
    parser.add_argument("--file-id", help="CSV에서 시험할 file_id")
    parser.add_argument("--filename", help="새 파일명")
    parser.add_argument("--extension", default="", help="새 파일 확장자")
    parser.add_argument("--description", default="", help="새 파일 설명")
    parser.add_argument("--text", default="", help="추출한 텍스트를 직접 입력")
    parser.add_argument("--text-file", type=Path, help="추출 텍스트가 저장된 UTF-8 파일")
    parser.add_argument("--threshold", type=float, help="새 과목 판정 기준(0~1)")
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    return parser.parse_args()


def load_record(args: argparse.Namespace) -> FileText:
    if args.file_id:
        if not args.csv.exists():
            raise FileNotFoundError(f"CSV를 찾을 수 없습니다: {args.csv}")
        df = pd.read_csv(args.csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if "file_id" not in df.columns:
            raise ValueError("CSV에 file_id 열이 없습니다.")
        matches = df[df["file_id"].str.strip() == args.file_id.strip()]
        if matches.empty:
            raise ValueError(f"file_id를 찾을 수 없습니다: {args.file_id}")
        return row_to_file_text(matches.iloc[0].to_dict())

    text = args.text
    if args.text_file:
        if not args.text_file.exists():
            raise FileNotFoundError(f"텍스트 파일을 찾을 수 없습니다: {args.text_file}")
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
            "먼저 python train_project_classifier.py 를 실행하세요."
        )
    if args.threshold is not None and not 0 <= args.threshold <= 1:
        raise ValueError("--threshold는 0 이상 1 이하여야 합니다.")

    artifact = joblib.load(args.model)
    classifier = artifact["classifier"]
    threshold = (
        args.threshold
        if args.threshold is not None
        else float(artifact["unknown_threshold"])
    )
    record = load_record(args)

    embedding_model = SentenceTransformer(artifact["model_name"])
    embedding = encode_file_texts(
        embedding_model,
        [record],
        chunk_chars=int(artifact["chunk_chars"]),
        max_chunks=int(artifact["max_chunks"]),
        show_progress_bar=False,
    )
    probabilities = classifier.predict_proba(embedding)[0]
    order = probabilities.argsort()[::-1]
    best_index = int(order[0])
    best_project = str(classifier.classes_[best_index])
    confidence = float(probabilities[best_index])
    predicted_project = best_project if confidence >= threshold else "새 과목"

    result = {
        "filename": record.filename,
        "project": predicted_project,
        "closest_existing_project": best_project,
        "confidence": round(confidence, 4),
        "unknown_threshold": round(threshold, 4),
        "needs_confirmation": confidence < threshold,
        "top3": [
            {
                "project": str(classifier.classes_[int(index)]),
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
    print(f"새 과목 판정 기준: {result['unknown_threshold']:.2%}")
    if result["needs_confirmation"]:
        print("판정: 신뢰도가 낮아 사용자의 과목명 확인이 필요합니다.")
    print("상위 예측:")
    for item in result["top3"]:
        print(f"  - {item['project']}: {item['confidence']:.2%}")


if __name__ == "__main__":
    main()
