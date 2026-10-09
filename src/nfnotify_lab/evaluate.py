from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from .detectors import build_detector, detector_names


@dataclass(frozen=True)
class EvaluationResult:
    detector: str
    threshold: float
    fpr: float
    recall: float
    median_detection_delay: float
    detected_attack_runs: int
    total_attack_runs: int


def _threshold_at_fpr(scores: np.ndarray, y: np.ndarray, target_fpr: float) -> float:
    benign = np.asarray(scores, dtype=float)[np.asarray(y) == 0]
    if benign.size == 0:
        raise ValueError("calibration set has no benign samples")

    # Pick the lowest observed threshold whose empirical calibration FPR does
    # not exceed the target. If score ties make even the maximum too frequent,
    # move just above the maximum, yielding zero calibration false positives.
    for threshold in np.unique(benign):
        if float((benign >= threshold).mean()) <= target_fpr:
            return float(threshold)
    return float(np.nextafter(np.max(benign), np.inf))


def _run_delay(
    df: pd.DataFrame, scores: np.ndarray, threshold: float
) -> tuple[float, int, int]:
    tmp = df[["run_id", "t", "attack_start", "attack_active"]].copy()
    tmp["score"] = scores
    delays: list[float] = []
    total = 0
    detected = 0
    for _, g in tmp.groupby("run_id", sort=False):
        attack_start = int(g["attack_start"].iloc[0])
        if attack_start < 0:
            continue
        total += 1
        after = g[(g["t"] >= attack_start) & (g["score"] >= threshold)]
        if len(after):
            detected += 1
            first_t = int(after.iloc[0]["t"])
            delays.append(float(first_t - attack_start))
    return (float(np.median(delays)) if delays else float("inf"), detected, total)


def split_by_run(df: pd.DataFrame, random_state: int = 0):
    groups = df["run_id"]
    first = GroupShuffleSplit(n_splits=1, test_size=0.4, random_state=random_state)
    train_idx, hold_idx = next(first.split(df, groups=groups))
    hold = df.iloc[hold_idx]
    second = GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=random_state + 1)
    cal_local, test_local = next(second.split(hold, groups=hold["run_id"]))
    return df.iloc[train_idx], hold.iloc[cal_local], hold.iloc[test_local]


def evaluate_all(
    feature_df: pd.DataFrame,
    target_fpr: float = 0.001,
    random_state: int = 0,
) -> pd.DataFrame:
    train, cal, test = split_by_run(feature_df, random_state=random_state)
    rows: list[dict[str, object]] = []

    feature_cols = [
        c
        for c in feature_df.columns
        if c.startswith("delta_")
        or c.startswith("m_")
        or c.startswith("prov_")
        or c in {"recovery_active", "obs_fraction"}
    ]

    for name in detector_names():
        det = build_detector(name, random_state=random_state)
        det.fit(train[feature_cols], train["attack_active"])
        cal_scores = det.score_samples(cal[feature_cols])
        threshold = _threshold_at_fpr(
            cal_scores, cal["attack_active"].to_numpy(), target_fpr=target_fpr
        )

        test_scores = det.score_samples(test[feature_cols])
        pred = test_scores >= threshold
        y = test["attack_active"].to_numpy().astype(bool)
        benign = ~y
        fpr = float(pred[benign].mean()) if benign.any() else float("nan")
        recall = float(pred[y].mean()) if y.any() else float("nan")
        delay, detected, total = _run_delay(test, test_scores, threshold)

        rows.append(
            {
                "detector": name,
                "threshold": threshold,
                "fpr": fpr,
                "recall_at_target_fpr": recall,
                "median_detection_delay": delay,
                "detected_attack_runs": detected,
                "total_attack_runs": total,
            }
        )
    return pd.DataFrame(rows)
