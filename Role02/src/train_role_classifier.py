"""extracted_text.csv로 자료 유형(role) 분류기를 학습하고 평가한다."""

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
    DEFAULT_DATA_CSV,
    MAX_CHUNKS,
    MODEL_NAME,
    encode_file_texts,
)
from role_classifier import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_MODEL_PATH,
    ROLE_NORMALIZATION,
    normalize_role,
    recognize_role_by_rule,
    row_to_role_file_text,
)


RANDOM_STATE = 42


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="자료 유형 분류기 학습 및 평가")
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
    required = {"file_id", "filename", "extracted_text", "role"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"학습 CSV에 필요한 열이 없습니다: {sorted(missing)}")

    df = df[
        df["file_id"].str.strip().ne("")
        & df["filename"].str.strip().ne("")
        & df["role"].str.strip().ne("")
    ].copy()
    df["canonical_role"] = df["role"].map(normalize_role)
    unknown_roles = sorted(df.loc[df["canonical_role"].eq(""), "role"].unique())
    if unknown_roles:
        raise ValueError(f"정규화 규칙에 없는 role이 있습니다: {unknown_roles}")
    return df.drop_duplicates(subset=["file_id"], keep="first").reset_index(drop=True)


def embedding_cache_path(df: pd.DataFrame, model_name: str, output_dir: Path) -> Path:
    hasher = hashlib.sha256()
    hasher.update(model_name.encode("utf-8"))
    hasher.update(str(CHUNK_CHARS).encode("ascii"))
    hasher.update(str(MAX_CHUNKS).encode("ascii"))
    hasher.update(b"role-input-without-description-v1")
    for _, row in df.iterrows():
        for column in ("file_id", "filename", "extension", "extracted_text"):
            value = str(row.get(column, "")).encode("utf-8")
            hasher.update(len(value).to_bytes(8, "big"))
            hasher.update(value)
    cache_dir = output_dir / "embedding_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"role_embeddings_{hasher.hexdigest()[:16]}.npy"


def choose_confirmation_threshold(confidences: np.ndarray, correct: np.ndarray) -> float:
    correct_confidences = confidences[correct]
    if len(correct_confidences) == 0:
        return 0.40
    threshold = float(np.quantile(correct_confidences, 0.05))
    return round(float(np.clip(threshold, 0.25, 0.60)), 4)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = load_training_data(args.data)
    counts = df["canonical_role"].value_counts().sort_index()
    folds = min(args.folds, int(counts.min()))
    if folds < 2:
        raise ValueError("교차검증을 위해 각 자료 유형에 최소 2개 파일이 필요합니다.")

    print(f"학습 파일 수: {len(df)}")
    print(f"통합 자료 유형 수: {len(counts)}")
    print(counts.to_string())

    cache_path = embedding_cache_path(df, args.model_name, args.output_dir)
    if cache_path.exists() and not args.rebuild_embeddings:
        print(f"저장된 파일 임베딩 불러오는 중: {cache_path.name}")
        embeddings = np.load(cache_path, allow_pickle=False)
    else:
        print(f"임베딩 모델 불러오는 중: {args.model_name}")
        model = SentenceTransformer(args.model_name)
        records = [row_to_role_file_text(row) for row in df.to_dict("records")]
        embeddings = encode_file_texts(model, records, batch_size=args.batch_size)
        np.save(cache_path, embeddings)
        print(f"파일 임베딩 저장 완료: {cache_path}")

    if embeddings.shape[0] != len(df):
        raise ValueError("임베딩 수와 학습 파일 수가 다릅니다.")

    labels = df["canonical_role"].to_numpy()
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=RANDOM_STATE)
    base_classifier = LogisticRegression(
        max_iter=3_000,
        class_weight="balanced",
        random_state=RANDOM_STATE,
    )
    probabilities = cross_val_predict(
        base_classifier,
        embeddings,
        labels,
        cv=cv,
        method="predict_proba",
        n_jobs=1,
    )
    classes = np.unique(labels)
    model_predictions = classes[np.argmax(probabilities, axis=1)]
    model_confidences = probabilities.max(axis=1)
    predictions = model_predictions.copy()
    confidences = model_confidences.copy()
    methods = np.full(len(df), "embedding_classifier", dtype=object)
    for index, row in enumerate(df.to_dict("records")):
        rule = recognize_role_by_rule(row_to_role_file_text(row))
        if rule is not None:
            predictions[index] = rule[0]
            confidences[index] = 0.99
            methods[index] = rule[1]

    model_correct = model_predictions == labels
    correct = predictions == labels
    model_accuracy = float(accuracy_score(labels, model_predictions))
    model_macro_f1 = float(f1_score(labels, model_predictions, average="macro"))
    accuracy = float(accuracy_score(labels, predictions))
    macro_f1 = float(f1_score(labels, predictions, average="macro"))
    threshold = choose_confirmation_threshold(model_confidences, model_correct)
    accepted = confidences >= threshold
    accepted_accuracy = float(np.mean(correct[accepted])) if np.any(accepted) else 0.0
    accepted_coverage = float(np.mean(accepted))

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
            "confirmation_threshold": threshold,
            "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "training_file_count": len(df),
            "role_counts": counts.to_dict(),
            "role_normalization": ROLE_NORMALIZATION,
            "description_used": False,
        },
        model_path,
    )

    evaluation = df[["file_id", "filename", "role", "canonical_role"]].copy()
    evaluation = evaluation.rename(
        columns={"role": "original_role", "canonical_role": "actual_role"}
    )
    evaluation["predicted_role"] = predictions
    evaluation["confidence"] = np.round(confidences, 4)
    evaluation["method"] = methods
    evaluation["correct"] = correct
    evaluation.to_csv(
        args.output_dir / "role_classifier_evaluation.csv",
        index=False,
        encoding="utf-8-sig",
    )
    matrix = confusion_matrix(labels, predictions, labels=classes)
    pd.DataFrame(matrix, index=classes, columns=classes).to_csv(
        args.output_dir / "role_classifier_confusion_matrix.csv",
        encoding="utf-8-sig",
    )
    report = classification_report(
        labels,
        predictions,
        labels=classes,
        output_dict=True,
        zero_division=0,
    )
    metrics = {
        "file_count": len(df),
        "role_count": int(len(classes)),
        "folds": folds,
        "accuracy": round(accuracy, 6),
        "macro_f1": round(macro_f1, 6),
        "embedding_only_accuracy": round(model_accuracy, 6),
        "embedding_only_macro_f1": round(model_macro_f1, 6),
        "confirmation_threshold": threshold,
        "accepted_accuracy": round(accepted_accuracy, 6),
        "accepted_coverage": round(accepted_coverage, 6),
        "class_counts": counts.to_dict(),
        "classification_report": report,
        "evaluation_note": (
            "수동 description의 role 표현으로 인한 데이터 누출을 막기 위해 "
            "파일명·확장자·추출 본문만 사용함"
        ),
    }
    (args.output_dir / "role_classifier_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 56)
    print("자료 유형 분류기 평가 결과")
    print("=" * 56)
    print(f"임베딩 단독 정확도: {model_accuracy:.2%}")
    print(f"임베딩 단독 Macro F1: {model_macro_f1:.2%}")
    print(f"규칙+임베딩 정확도: {accuracy:.2%}")
    print(f"규칙+임베딩 Macro F1: {macro_f1:.2%}")
    print(f"사용자 확인 기준: {threshold:.2%}")
    print(f"자동 확정 범위: {accepted_coverage:.2%}")
    print(f"자동 확정 정확도: {accepted_accuracy:.2%}")
    print(f"모델 저장: {model_path}")


if __name__ == "__main__":
    main()
