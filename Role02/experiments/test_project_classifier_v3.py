from __future__ import annotations

import unittest
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_classifier_v3 import normalize_rows, score_embeddings, select_text_chunks


class FakeClassifier:
    classes_ = np.array(["A", "B"])

    def predict_proba(self, embeddings: np.ndarray) -> np.ndarray:
        return np.array([[0.8, 0.2], [0.55, 0.45]], dtype=np.float32)


class ProjectClassifierV3Test(unittest.TestCase):
    def test_normalize_rows(self) -> None:
        actual = normalize_rows(np.array([[3.0, 4.0], [0.0, 0.0]]))
        np.testing.assert_allclose(actual[0], [0.6, 0.8])
        np.testing.assert_allclose(actual[1], [0.0, 0.0])

    def test_chunks_cover_document(self) -> None:
        text = "".join(chr(0xAC00 + index) for index in range(200))
        chunks = select_text_chunks(text, chunk_chars=20, max_chunks=3)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(text.startswith(chunks[0]))
        self.assertTrue(text.endswith(chunks[-1]))

    def test_open_set_checks_reject_ambiguous_file(self) -> None:
        artifact = {
            "classifier": FakeClassifier(),
            "class_centroids": np.array([[1.0, 0.0], [0.0, 1.0]]),
            "open_set_thresholds": {
                "confidence": 0.6,
                "probability_margin": 0.2,
                "centroid_similarity": 0.7,
                "centroid_margin": 0.2,
            },
        }
        scores = score_embeddings(
            artifact,
            np.array([[1.0, 0.0], [0.8, 0.6]], dtype=np.float32),
        )
        self.assertEqual(scores["predicted_project"].tolist(), ["A", "새 과목"])
        self.assertEqual(scores["accepted_as_existing"].tolist(), [True, False])

if __name__ == "__main__":
    unittest.main()
