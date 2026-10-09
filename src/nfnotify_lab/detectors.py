from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import MODEL_FEATURES, model_matrix


@dataclass
class RuleDetector:
    """Deterministic semantic-consistency baseline."""

    def fit(self, x: pd.DataFrame, y: pd.Series | None = None) -> RuleDetector:
        return self

    def score_samples(self, x: pd.DataFrame) -> np.ndarray:
        z = x.copy()
        d1 = z["delta_nrf_ausf"].fillna(0.0)
        d2 = z["delta_route"].fillna(0.0)
        d3 = z["delta_notify"].fillna(0.0)
        d4 = z["delta_time"].fillna(0.0)
        # Context reduces severity for transient, known recovery conditions.
        recovery_discount = 0.75 * z["recovery_active"].fillna(0.0)
        return (d1 + d2 + 1.5 * d3 + 0.75 * d4 - recovery_discount).to_numpy()


class IsolationForestDetector:
    """Unsupervised baseline fitted on benign training windows only."""

    def __init__(self, random_state: int = 0) -> None:
        self.pipe = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                (
                    "model",
                    IsolationForest(
                        n_estimators=300,
                        contamination="auto",
                        random_state=random_state,
                        n_jobs=-1,
                    ),
                ),
            ]
        )

    def fit(self, x: pd.DataFrame, y: pd.Series) -> IsolationForestDetector:
        benign = x.loc[y.to_numpy() == 0]
        self.pipe.fit(benign)
        return self

    def score_samples(self, x: pd.DataFrame) -> np.ndarray:
        # sklearn gives higher values to normal points; invert for anomaly score.
        return -self.pipe.named_steps["model"].score_samples(
            self.pipe[:-1].transform(x)
        )


class ProvenanceAwareDetector:
    """Research model that explicitly consumes observation masks/provenance.

    This is a baseline implementation, not a claim of scientific novelty. It is
    deliberately structured so new provenance-aware objectives or calibration
    methods can replace the learner without changing the experiment harness.
    """

    def __init__(self, random_state: int = 0) -> None:
        self.model = HistGradientBoostingClassifier(
            learning_rate=0.06,
            max_iter=250,
            max_leaf_nodes=15,
            l2_regularization=1.0,
            random_state=random_state,
        )

    def fit(self, x: pd.DataFrame, y: pd.Series) -> ProvenanceAwareDetector:
        self.model.fit(model_matrix(x), y)
        return self

    def score_samples(self, x: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(model_matrix(x))[:, 1]


def detector_names() -> tuple[str, ...]:
    return ("rules", "isolation_forest", "provenance_aware")


def build_detector(name: str, random_state: int = 0):
    if name == "rules":
        return RuleDetector()
    if name == "isolation_forest":
        return IsolationForestDetector(random_state=random_state)
    if name == "provenance_aware":
        return ProvenanceAwareDetector(random_state=random_state)
    raise ValueError(f"unknown detector: {name}; features={MODEL_FEATURES}")
