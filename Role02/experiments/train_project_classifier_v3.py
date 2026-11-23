"""본문·description·파일명을 사용하는 프로젝트 분류기 v3 학습기."""

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
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import StratifiedKFold

from project_classifier_v3 import (
    CHUNK_CHARS,
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_DATA_CSV,
    DEFAULT_DESCRIPTION_CSV,
    MAX_CHUNKS,
    MODEL_NAME,
    VIEW_WEIGHTS,
    encode_file_texts,
    normalize_rows,
    row_to_file_text,
    score_embeddings,
)


RANDOM_STATE = 42
DEFAULT_CLASSIFIER_C = 10.0
DEFAULT_PROBABILITY_QUANTILE = 0.05
DEFAULT_CENTROID_QUANTILE = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="프로젝트 분류기 v3 학습 및 평가")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_CSV)
    parser.add_argument("--descriptions", type=Path, default=DEFAULT_DESCRIPTION_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--model-name", default=MODEL_NAME)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--classifier-c",
        type=float,
        default=DEFAULT_CLASSIFIER_C,
        help="로지스틱 분류기의 정규화 역강도(기본 10.0)",
    )
    parser.add_argument(
        "--probability-quantile",
        type=float,
        default=DEFAULT_PROBABILITY_QUANTILE,
        help="확률 기준을 정할 기존 프로젝트 하위 분위수(기본 0.05)",
    )
    parser.add_argument(
        "--centroid-quantile",
        type=float,
        default=DEFAULT_CENTROID_QUANTILE,
        help="중심 유사도 기준을 정할 기존 프로젝트 하위 분위수(기본 0.0)",
    )
    parser.add_argument("--rebuild-embeddings", action="store_true")
    parser.add_argument(
        "--evaluate-unlabeled-as-new",
        action="store_true",
        help="project가 빈 행을 실제 새 프로젝트 표본으로 간주해 추가 평가",
    )
    return parser.parse_args()


def load_data(data_path: Path, description_path: Path) -> pd.DataFrame:
    if not data_path.exists():
        raise FileNotFoundError(f"학습 CSV를 찾을 수 없습니다: {data_path}")
    frame = pd.read_csv(
        data_path, dtype=str, keep_default_na=False, encoding="utf-8-sig"
    )
    required = {"file_id", "filename", "extracted_text", "project"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"학습 CSV에 필요한 열이 없습니다: {sorted(missing)}")
    if "description" not in frame:
        frame["description"] = ""

    if description_path.exists():
        descriptions = pd.read_csv(
            description_path, dtype=str, keep_default_na=False, encoding="utf-8-sig"
        )
        if not {"file_id", "description"}.issubset(descriptions.columns):
            raise ValueError("description CSV에는 file_id와 description 열이 필요합니다.")
        description_map = descriptions.drop_duplicates("file_id").set_index("file_id")[
            "description"
        ]
        blank = frame["description"].str.strip().eq("")
        frame.loc[blank, "description"] = (
            frame.loc[blank, "file_id"].map(description_map).fillna("")
        )

    frame = frame[
        frame["file_id"].str.strip().ne("") & frame["filename"].str.strip().ne("")
    ].copy()
    return frame.drop_duplicates("file_id", keep="first").reset_index(drop=True)


def cache_path(frame: pd.DataFrame, model_name: str, output_dir: Path) -> Path:
    hasher = hashlib.sha256()
    hasher.update(model_name.encode())
    hasher.update(json.dumps(VIEW_WEIGHTS, sort_keys=True).encode())
    hasher.update(f"{CHUNK_CHARS}:{MAX_CHUNKS}".encode())
    for row in frame.to_dict("records"):
        for column in ("file_id", "filename", "extension", "description", "extracted_text"):
            value = str(row.get(column, "")).encode()
            hasher.update(len(value).to_bytes(8, "big"))
            hasher.update(value)
    directory = output_dir / "embedding_cache"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"features_{hasher.hexdigest()[:16]}.npy"


def build_classifier(classifier_c: float = DEFAULT_CLASSIFIER_C) -> LogisticRegression:
    return LogisticRegression(
        max_iter=4_000,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        C=classifier_c,
    )


def centroids_for(classes: np.ndarray, embeddings: np.ndarray, labels: np.ndarray) -> np.ndarray:
    return np.stack(
        [normalize_rows(embeddings[labels == label].mean(axis=0, keepdims=True))[0] for label in classes]
    )


def main() -> None:
    args = parse_args()
    if args.classifier_c <= 0:
        raise ValueError("--classifier-c는 0보다 커야 합니다.")
    for name, value in (
        ("--probability-quantile", args.probability_quantile),
        ("--centroid-quantile", args.centroid_quantile),
    ):
        if not 0 <= value < 0.5:
            raise ValueError(f"{name}은 0 이상 0.5 미만이어야 합니다.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame = load_data(args.data, args.descriptions)
    labeled = frame["project"].str.strip().ne("").to_numpy()
    training = frame.loc[labeled].reset_index(drop=True)
    labels = training["project"].to_numpy()
    class_counts = training["project"].value_counts().sort_index()
    folds = min(args.folds, int(class_counts.min()))
    if len(class_counts) < 2 or folds < 2:
        raise ValueError("2개 이상의 프로젝트와 프로젝트별 2개 이상의 파일이 필요합니다.")

    print(f"학습 파일 {len(training)}개, 프로젝트 {len(class_counts)}개")
    features_path = cache_path(frame, args.model_name, args.output_dir)
    if features_path.exists() and not args.rebuild_embeddings:
        print(f"임베딩 캐시 사용: {features_path.name}")
        all_features = np.load(features_path, allow_pickle=False)
    else:
        print(f"임베딩 모델 로드: {args.model_name}")
        model = SentenceTransformer(args.model_name)
        all_features = encode_file_texts(
            model,
            [row_to_file_text(row) for row in frame.to_dict("records")],
            batch_size=args.batch_size,
        )
        np.save(features_path, all_features)
    if len(all_features) != len(frame):
        raise ValueError("임베딩 캐시와 CSV의 파일 수가 다릅니다.")
    features = all_features[labeled]

    classes = np.unique(labels)
    row_count = len(training)
    oof_probabilities = np.zeros((row_count, len(classes)), dtype=np.float32)
    oof_centroid_project = np.empty(row_count, dtype=object)
    oof_centroid_similarity = np.zeros(row_count, dtype=np.float32)
    oof_centroid_margin = np.zeros(row_count, dtype=np.float32)
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=RANDOM_STATE)

    for train_indices, validation_indices in cv.split(features, labels):
        classifier = build_classifier(args.classifier_c)
        classifier.fit(features[train_indices], labels[train_indices])
        probabilities = classifier.predict_proba(features[validation_indices])
        oof_probabilities[validation_indices] = probabilities
        centroids = centroids_for(
            classifier.classes_, features[train_indices], labels[train_indices]
        )
        similarities = features[validation_indices] @ centroids.T
        order = np.argsort(similarities, axis=1)[:, ::-1]
        rows = np.arange(len(validation_indices))
        oof_centroid_project[validation_indices] = classifier.classes_[order[:, 0]]
        oof_centroid_similarity[validation_indices] = similarities[rows, order[:, 0]]
        oof_centroid_margin[validation_indices] = (
            similarities[rows, order[:, 0]] - similarities[rows, order[:, 1]]
        )

    probability_order = np.argsort(oof_probabilities, axis=1)[:, ::-1]
    rows = np.arange(row_count)
    oof_prediction = classes[probability_order[:, 0]]
    oof_confidence = oof_probabilities[rows, probability_order[:, 0]]
    oof_probability_margin = (
        oof_confidence - oof_probabilities[rows, probability_order[:, 1]]
    )
    correct = oof_prediction == labels
    agreement = oof_prediction == oof_centroid_project
    calibration = correct & agreement
    if not calibration.any():
        raise RuntimeError("새 프로젝트 판정 기준을 계산할 올바른 검증 예측이 없습니다.")

    probability_quantile = args.probability_quantile
    centroid_quantile = args.centroid_quantile
    thresholds = {
        "confidence": float(
            np.quantile(oof_confidence[calibration], probability_quantile)
        ),
        "probability_margin": float(
            np.quantile(oof_probability_margin[calibration], probability_quantile)
        ),
        "centroid_similarity": float(
            np.quantile(oof_centroid_similarity[calibration], centroid_quantile)
        ),
        "centroid_margin": float(
            np.quantile(oof_centroid_margin[calibration], centroid_quantile)
        ),
    }
    oof_accepted = (
        agreement
        & (oof_confidence >= thresholds["confidence"])
        & (oof_probability_margin >= thresholds["probability_margin"])
        & (oof_centroid_similarity >= thresholds["centroid_similarity"])
        & (oof_centroid_margin >= thresholds["centroid_margin"])
    )

    final_classifier = build_classifier(args.classifier_c)
    final_classifier.fit(features, labels)
    class_centroids = centroids_for(final_classifier.classes_, features, labels)
    artifact = {
        "version": "3.1",
        "classifier": final_classifier,
        "class_centroids": class_centroids,
        "model_name": args.model_name,
        "chunk_chars": CHUNK_CHARS,
        "max_chunks": MAX_CHUNKS,
        "view_weights": VIEW_WEIGHTS,
        "open_set_thresholds": thresholds,
        "classifier_c": args.classifier_c,
        "open_set_quantiles": {
            "probability": probability_quantile,
            "centroid": centroid_quantile,
        },
        "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "training_file_count": len(training),
        "project_counts": class_counts.to_dict(),
    }
    model_path = args.output_dir / "project_classifier_v3.joblib"
    joblib.dump(artifact, model_path)

    evaluation = training[["file_id", "filename", "project"]].rename(
        columns={"project": "actual_project"}
    )
    evaluation["predicted_existing_project"] = oof_prediction
    evaluation["predicted_project"] = np.where(
        oof_accepted, oof_prediction, "새 과목"
    )
    evaluation["confidence"] = oof_confidence.round(6)
    evaluation["probability_margin"] = oof_probability_margin.round(6)
    evaluation["centroid_similarity"] = oof_centroid_similarity.round(6)
    evaluation["centroid_margin"] = oof_centroid_margin.round(6)
    evaluation["centroid_project"] = oof_centroid_project
    evaluation["accepted_as_existing"] = oof_accepted
    evaluation["failed_checks"] = [
        ";".join(
            name
            for name, passed in (
                ("model_agreement", agreement[index]),
                ("confidence", oof_confidence[index] >= thresholds["confidence"]),
                (
                    "probability_margin",
                    oof_probability_margin[index]
                    >= thresholds["probability_margin"],
                ),
                (
                    "centroid_similarity",
                    oof_centroid_similarity[index]
                    >= thresholds["centroid_similarity"],
                ),
                (
                    "centroid_margin",
                    oof_centroid_margin[index] >= thresholds["centroid_margin"],
                ),
            )
            if not passed
        )
        for index in range(row_count)
    ]
    evaluation.to_csv(
        args.output_dir / "project_classifier_evaluation.csv",
        index=False,
        encoding="utf-8-sig",
    )

    accuracy = float(accuracy_score(labels, oof_prediction))
    macro_f1 = float(f1_score(labels, oof_prediction, average="macro"))
    metrics = {
        "file_count": len(training),
        "project_count": len(classes),
        "folds": folds,
        "closed_set_accuracy": accuracy,
        "closed_set_macro_f1": macro_f1,
        "mean_known_project_confidence": float(oof_confidence.mean()),
        "median_known_project_confidence": float(np.median(oof_confidence)),
        "known_project_acceptance_rate": float(oof_accepted.mean()),
        "classifier_c": args.classifier_c,
        "open_set_quantiles": {
            "probability": probability_quantile,
            "centroid": centroid_quantile,
        },
        "open_set_thresholds": thresholds,
        "class_counts": class_counts.to_dict(),
        "classification_report": classification_report(
            labels, oof_prediction, output_dict=True, zero_division=0
        ),
    }
    if args.evaluate_unlabeled_as_new and (~labeled).any():
        unknown_frame = frame.loc[~labeled].reset_index(drop=True)
        unknown_scores = score_embeddings(artifact, all_features[~labeled])
        unknown_evaluation = unknown_frame[["file_id", "filename", "path"]].copy()
        for name, values in unknown_scores.items():
            if name != "probabilities":
                unknown_evaluation[name] = values
        new_recall = float(
            np.mean(unknown_scores["predicted_project"] == "새 과목")
        )
        unknown_evaluation.to_csv(
            args.output_dir / "new_project_evaluation.csv",
            index=False,
            encoding="utf-8-sig",
        )
        metrics["unlabeled_evaluation"] = {
            "assumption": "project가 빈 모든 행은 기존 학습 프로젝트와 다른 새 프로젝트",
            "file_count": len(unknown_frame),
            "new_project_recall": new_recall,
            "false_existing_assignments": int(
                np.sum(unknown_scores["predicted_project"] != "새 과목")
            ),
        }

    (args.output_dir / "project_classifier_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"모델 저장: {model_path}")


if __name__ == "__main__":
    main()
