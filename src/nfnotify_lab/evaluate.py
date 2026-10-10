from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

from .detectors import build_detector, detector_names


def _threshold_at_fpr(scores: np.ndarray, y: np.ndarray, target_fpr: float) -> float:
    benign = np.asarray(scores, dtype=float)[np.asarray(y) == 0]
    if benign.size == 0:
        raise ValueError("calibration set has no benign samples")

    for threshold in np.unique(benign):
        if float((benign >= threshold).mean()) <= target_fpr:
            return float(threshold)
    return float(np.nextafter(np.max(benign), np.inf))


def _safe_roc_auc(y: np.ndarray, scores: np.ndarray) -> float:
    return float(roc_auc_score(y, scores)) if len(np.unique(y)) == 2 else float("nan")


def _safe_pr_auc(y: np.ndarray, scores: np.ndarray) -> float:
    return (
        float(average_precision_score(y, scores))
        if np.asarray(y).sum() > 0
        else float("nan")
    )


def _run_delay(
    df: pd.DataFrame, scores: np.ndarray, threshold: float
) -> tuple[float, int, int]:
    tmp = df[["run_id", "t", "attack_start", "attack_active"]].copy()
    tmp["score"] = scores
    delays: list[float] = []
    total = 0
    detected = 0
    for _, group in tmp.groupby("run_id", sort=False):
        attack_start = int(group["attack_start"].iloc[0])
        if attack_start < 0:
            continue
        total += 1
        after = group[
            (group["t"] >= attack_start) & (group["score"] >= threshold)
        ]
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


def _fit_detector(name: str, train: pd.DataFrame, cal: pd.DataFrame, random_state: int):
    detector = build_detector(name, random_state=random_state)
    detector.fit(train, train["attack_active"])
    if hasattr(detector, "calibrate"):
        detector.calibrate(cal, cal["attack_active"])
    cal_scores = detector.score_samples(cal)
    return detector, cal_scores


def evaluate_all(
    feature_df: pd.DataFrame,
    target_fpr: float = 0.001,
    random_state: int = 0,
) -> pd.DataFrame:
    train, cal, test = split_by_run(feature_df, random_state=random_state)
    rows: list[dict[str, object]] = []

    for name in detector_names():
        detector, cal_scores = _fit_detector(name, train, cal, random_state)
        threshold = _threshold_at_fpr(
            cal_scores, cal["attack_active"].to_numpy(), target_fpr=target_fpr
        )

        test_scores = detector.score_samples(test)
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
                "roc_auc": _safe_roc_auc(y.astype(int), test_scores),
                "pr_auc": _safe_pr_auc(y.astype(int), test_scores),
                "median_detection_delay": delay,
                "detected_attack_runs": detected,
                "total_attack_runs": total,
            }
        )
    return pd.DataFrame(rows)


def evaluate_by_scenario(
    feature_df: pd.DataFrame,
    target_fpr: float = 0.001,
    random_state: int = 0,
) -> pd.DataFrame:
    train, cal, test = split_by_run(feature_df, random_state=random_state)
    rows: list[dict[str, object]] = []

    for name in detector_names():
        detector, cal_scores = _fit_detector(name, train, cal, random_state)
        threshold = _threshold_at_fpr(
            cal_scores, cal["attack_active"].to_numpy(), target_fpr=target_fpr
        )
        scored = test[
            ["run_id", "scenario", "t", "attack_start", "attack_active"]
        ].copy()
        scored["score"] = detector.score_samples(test)
        scored["pred"] = scored["score"] >= threshold

        for scenario, group in scored.groupby("scenario", sort=True):
            y = group["attack_active"].to_numpy().astype(bool)
            pred = group["pred"].to_numpy().astype(bool)
            benign = ~y
            delay, detected, total = _run_delay(
                group, group["score"].to_numpy(), threshold
            )
            rows.append(
                {
                    "detector": name,
                    "scenario": scenario,
                    "samples": len(group),
                    "fpr": float(pred[benign].mean()) if benign.any() else float("nan"),
                    "recall": float(pred[y].mean()) if y.any() else float("nan"),
                    "roc_auc": _safe_roc_auc(y.astype(int), group["score"].to_numpy()),
                    "pr_auc": _safe_pr_auc(y.astype(int), group["score"].to_numpy()),
                    "median_detection_delay": delay,
                    "detected_attack_runs": detected,
                    "total_attack_runs": total,
                }
            )
    return pd.DataFrame(rows)
