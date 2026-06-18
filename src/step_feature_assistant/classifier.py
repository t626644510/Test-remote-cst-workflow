"""Experimental feature scorer interface and scikit-learn implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

import joblib
import pandas as pd

from .ml_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, face_feature_row


class FeatureScorer(Protocol):
    """Stable interface for experimental geometry feature suggestions."""

    model_version: str

    def score_manifest(self, geometry_manifest: dict) -> dict:
        """Score every face without changing the rule-based feature graph."""


class SklearnFeatureScorer:
    """Load and execute the experimental scikit-learn baseline."""

    def __init__(self, model_path: Path, threshold: float = 0.35):
        self.bundle = joblib.load(model_path)
        self.threshold = threshold
        self.model_version = str(self.bundle.get("model_version", "experimental"))

    def score_manifest(self, geometry_manifest: dict) -> dict:
        project_id = Path(geometry_manifest.get("source_step", "project")).stem
        rows = [face_feature_row(geometry_manifest, face, project_id) for face in geometry_manifest.get("faces", [])]
        frame = pd.DataFrame(rows)
        probabilities = self.bundle["pipeline"].predict_proba(frame)
        classes = list(self.bundle["classes"])
        faces = []
        for row, values in zip(rows, probabilities):
            suggestions = [
                {
                    "type": feature_type,
                    "probability": float(probability),
                    "model_version": self.model_version,
                    "evidence": ["experimental logistic-regression baseline"],
                }
                for feature_type, probability in sorted(zip(classes, values), key=lambda item: item[1], reverse=True)
                if float(probability) >= self.threshold
            ]
            faces.append({"face_id": row["face_id"], "suggestions": suggestions})
        return {
            "schema_version": "0.1",
            "model_version": self.model_version,
            "experimental": True,
            "changes_rule_based_graph": False,
            "faces": faces,
        }
