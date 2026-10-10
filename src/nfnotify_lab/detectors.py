from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import MODEL_FEATURES, model_matrix
from .patef import ProvenanceAwareTemporalEvidenceFusion, semantic_attack_support


@dataclass
class RuleDetector:
    """Deterministic semantic-consistency baseline."""

    def fit(self, x: pd.DataFrame, y: pd.Series | None = None) -> RuleDetector:
        return self

    def score_samples(self, x: pd.DataFrame) -> np.ndarray:
        d1 = x["delta_nrf_ausf"].fillna(0.0)
        d2 = x["delta_route"].fillna(0.0)
        d3 = x["delta_notify"].fillna(0.0)
        d4 = x["delta_time"].fillna(0.0)
        recovery_discount = 0.75 * x["recovery_active"].fillna(0.0)
        return (d1 + d2 + 1.5 * d3 + 0.75 * d4 - recovery_discount).to_numpy()


class IsolationForestDetector:
    """Unsupervised baseline fitted on benign training windows only."""

    def __init__(self, random_state: int = 0) -> None:
        self.pipe = Pipeline(
            [
                (
                    "imputer",
                    SimpleImputer(
                        strategy="constant",
                        fill_value=0.0,
                        add_indicator=True,
                        keep_empty_features=True,
                    ),
                ),
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
        matrix = model_matrix(x)
        benign = matrix.loc[np.asarray(y) == 0]
        self.pipe.fit(benign)
        return self

    def score_samples(self, x: pd.DataFrame) -> np.ndarray:
        matrix = model_matrix(x)
        transformed = self.pipe[:-1].transform(matrix)
        return -self.pipe.named_steps["model"].score_samples(transformed)


class ProvenanceAwareDetector:
    """Single-model provenance-aware baseline."""

    is_probability_score = True

    def __init__(self, random_state: int = 0) -> None:
        self.model = Pipeline(
            [
                (
                    "imputer",
                    SimpleImputer(
                        strategy="constant",
                        fill_value=0.0,
                        add_indicator=True,
                        keep_empty_features=True,
                    ),
                ),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        learning_rate=0.06,
                        max_iter=250,
                        max_leaf_nodes=15,
                        l2_regularization=1.0,
                        random_state=random_state,
                    ),
                ),
            ]
        )

    def fit(self, x: pd.DataFrame, y: pd.Series) -> ProvenanceAwareDetector:
        self.model.fit(model_matrix(x), y)
        return self

    def score_samples(self, x: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(model_matrix(x))[:, 1]



@dataclass
class SemanticGuardDetector:
    """Deterministic version of PA-TEF's domain-semantic evidence gate."""

    def fit(
        self, x: pd.DataFrame, y: pd.Series | None = None
    ) -> SemanticGuardDetector:
        return self

    def score_samples(self, x: pd.DataFrame) -> np.ndarray:
        return semantic_attack_support(x).to_numpy(dtype=float)


def detector_names() -> tuple[str, ...]:
    return ("rules", "semantic_guard", "isolation_forest", "provenance_aware", "patef")


def build_detector(name: str, random_state: int = 0):
    if name == "rules":
        return RuleDetector()
    if name == "semantic_guard":
        return SemanticGuardDetector()
    if name == "isolation_forest":
        return IsolationForestDetector(random_state=random_state)
    if name == "provenance_aware":
        return ProvenanceAwareDetector(random_state=random_state)
    if name == "patef":
        return ProvenanceAwareTemporalEvidenceFusion(random_state=random_state)
    raise ValueError(f"unknown detector: {name}; features={MODEL_FEATURES}")
