"""extracted_text.csv로 프로젝트(과목) 분류기를 학습하고 평가한다.

실행 예시:
    python train_project_classifier.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from project_classifier import (
    CHUNK_CHARS,
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_DATA_CSV,
    DEFAULT_MODEL_PATH,
    MAX_CHUNKS,
    MODEL_NAME,
    encode_file_texts,
    row_to_file_text,
)


RANDOM_STATE = 42


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="프로젝트 분류기 학습 및 평가")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_CSV)
    parser.add_argument("--model-name", default=MODEL_NAME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--rebuild-embeddings", action="store_true")
    return parser.parse_args()


def load_training_data(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"학습 CSV를 찾을 수 없습니다: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = {"file_id", "filename", "extracted_text", "project"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"학습 CSV에 필요한 열이 없습니다: {sorted(missing)}")

    df = df[
        df["file_id"].str.strip().ne("")
        & df["filename"].str.strip().ne("")
        & df["project"].str.strip().ne("")
    ].copy()
    df = df.drop_duplicates(subset=["file_id"], keep="first").reset_index(drop=True)
    if df.empty:
        raise ValueError("학습할 파일이 없습니다.")

    counts = df["project"].value_counts()
    if len(counts) < 2:
        raise ValueError("프로젝트 라벨이 최소 2종류 필요합니다.")
    return df


def embedding_cache_path(
    df: pd.DataFrame,
    model_name: str,
    output_dir: Path,
) -> Path:
    hasher = hashlib.sha256()
    hasher.update(model_name.encode("utf-8"))
    hasher.update(str(CHUNK_CHARS).encode("ascii"))
    hasher.update(str(MAX_CHUNKS).encode("ascii"))
    for _, row in df.iterrows():
        for column in ("file_id", "filename", "extension", "description", "extracted_text"):
            value = str(row.get(column, "")).encode("utf-8")
            hasher.update(len(value).to_bytes(8, "big"))
            hasher.update(value)
    cache_dir = output_dir / "embedding_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"file_embeddings_{hasher.hexdigest()[:16]}.npy"


def choose_unknown_threshold(confidences: np.ndarray, correct: np.ndarray) -> float:
    """정답을 맞힌 검증 샘플 신뢰도의 하위 5%를 초기 기준으로 사용한다.

    현재 데이터에는 실제 새 과목 표본이 없으므로 이 값은 확정 기준이 아니라
    알려진 파일 대부분을 통과시키기 위한 보수적인 시작점이다.
    """
    correct_confidences = confidences[correct]
    if len(correct_confidences) == 0:
        return 0.30
    threshold = float(np.quantile(correct_confidences, 0.05))
    return round(float(np.clip(threshold, 0.25, 0.40)), 4)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    df = load_training_data(args.data)
    class_counts = df["project"].value_counts().sort_index()
    smallest_class = int(class_counts.min())
    folds = min(args.folds, smallest_class)
    if folds < 2:
        raise ValueError("교차검증을 위해 각 프로젝트에 최소 2개 파일이 필요합니다.")

    print(f"학습 파일 수: {len(df)}")
    print(f"프로젝트 수: {df['project'].nunique()}")
    print("프로젝트별 파일 수:")
    print(class_counts.to_string())

    cache_path = embedding_cache_path(df, args.model_name, args.output_dir)
    if cache_path.exists() and not args.rebuild_embeddings:
        print(f"저장된 파일 임베딩 불러오는 중: {cache_path.name}")
        embeddings = np.load(cache_path, allow_pickle=False)
        if embeddings.shape[0] != len(df):
            raise ValueError("임베딩 캐시의 파일 수가 학습 데이터와 맞지 않습니다.")
    else:
        print(f"임베딩 모델 불러오는 중: {args.model_name}")
        embedding_model = SentenceTransformer(args.model_name)
        records = [row_to_file_text(row) for row in df.to_dict("records")]
        print("파일 임베딩 생성 중...")
        embeddings = encode_file_texts(
            embedding_model,
            records,
            batch_size=args.batch_size,
        )
        np.save(cache_path, embeddings)
        print(f"파일 임베딩 저장 완료: {cache_path}")

    labels = df["project"].to_numpy()
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=RANDOM_STATE)
    base_classifier = LogisticRegression(
        max_iter=3_000,
        class_weight="balanced",
        random_state=RANDOM_STATE,
    )

    print(f"{folds}겹 교차검증 시작...")
    probabilities = cross_val_predict(
        base_classifier,
        embeddings,
        labels,
        cv=cv,
        method="predict_proba",
        n_jobs=1,
    )
    classes = np.unique(labels)
    predictions = classes[np.argmax(probabilities, axis=1)]
    confidences = probabilities.max(axis=1)
    correct = predictions == labels

    accuracy = float(accuracy_score(labels, predictions))
    macro_f1 = float(f1_score(labels, predictions, average="macro"))
    threshold = choose_unknown_threshold(confidences, correct)
    known_acceptance_rate = float(np.mean(confidences >= threshold))
    report = classification_report(
        labels,
        predictions,
        labels=classes,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(labels, predictions, labels=classes)

    final_classifier = LogisticRegression(
        max_iter=3_000,
        class_weight="balanced",
        random_state=RANDOM_STATE,
    )
    final_classifier.fit(embeddings, labels)

    model_path = args.output_dir / DEFAULT_MODEL_PATH.name
    joblib.dump(
        {
            "classifier": final_classifier,
            "model_name": args.model_name,
            "chunk_chars": CHUNK_CHARS,
            "max_chunks": MAX_CHUNKS,
            "unknown_threshold": threshold,
            "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "training_file_count": len(df),
            "project_counts": class_counts.to_dict(),
        },
        model_path,
    )

    prediction_path = args.output_dir / "project_classifier_evaluation.csv"
    evaluation = df[["file_id", "filename", "project"]].copy()
    evaluation = evaluation.rename(columns={"project": "actual_project"})
    evaluation["predicted_project"] = predictions
    evaluation["confidence"] = np.round(confidences, 4)
    evaluation["correct"] = correct
    evaluation.to_csv(prediction_path, index=False, encoding="utf-8-sig")

    confusion_path = args.output_dir / "project_classifier_confusion_matrix.csv"
    pd.DataFrame(matrix, index=classes, columns=classes).to_csv(
        confusion_path,
        encoding="utf-8-sig",
    )

    metrics_path = args.output_dir / "project_classifier_metrics.json"
    metrics = {
        "file_count": len(df),
        "project_count": int(len(classes)),
        "folds": folds,
        "accuracy": round(accuracy, 6),
        "macro_f1": round(macro_f1, 6),
        "unknown_threshold": threshold,
        "known_validation_acceptance_rate": round(known_acceptance_rate, 6),
        "unknown_threshold_note": (
            "실제 새 과목 검증 데이터가 없어, 정답을 맞힌 교차검증 신뢰도의 "
            "하위 5%를 초기 기준으로 사용함"
        ),
        "class_counts": class_counts.to_dict(),
        "classification_report": report,
    }
    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("프로젝트 분류기 평가 결과")
    print("=" * 60)
    print(f"교차검증 정확도: {accuracy:.2%}")
    print(f"교차검증 Macro F1: {macro_f1:.2%}")
    print(f"새 과목 판정 기준 신뢰도: {threshold:.2%}")
    print(f"기존 과목 검증 파일 통과율: {known_acceptance_rate:.2%}")
    print(f"모델 저장: {model_path}")
    print(f"평가 결과 저장: {prediction_path}")
    print(f"혼동행렬 저장: {confusion_path}")
    print(f"평가지표 저장: {metrics_path}")


if __name__ == "__main__":
    main()

