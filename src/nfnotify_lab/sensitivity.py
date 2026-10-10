from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .consensus import consensus_attack_support
from .evaluate import (
    _run_delay,
    _split_scenario_holdout,
    _threshold_at_fpr,
    split_by_run,
)


@dataclass(frozen=True)
class ConsensusGrid:
    single_source_steps: tuple[int, ...] = (4, 6, 8, 10, 12, 16)
    dual_source_steps: tuple[int, ...] = (1, 2, 3, 4)


def _metrics(
    frame: pd.DataFrame,
    scores: np.ndarray,
    threshold: float,
) -> dict[str, float | int]:
    y = frame["attack_active"].to_numpy().astype(bool)
    pred = np.asarray(scores) >= threshold
    benign = ~y
    fpr = float(pred[benign].mean()) if benign.any() else float("nan")
    recall = float(pred[y].mean()) if y.any() else float("nan")
    delay, detected, total = _run_delay(frame, np.asarray(scores), threshold)
    return {
        "fpr": fpr,
        "recall": recall,
        "median_detection_delay": delay,
        "detected_attack_runs": detected,
        "total_attack_runs": total,
        "false_positives": int(pred[benign].sum()) if benign.any() else 0,
        "benign_samples": int(benign.sum()),
        "true_positives": int(pred[y].sum()) if y.any() else 0,
        "attack_samples": int(y.sum()),
    }


def evaluate_consensus_grid(
    feature_df: pd.DataFrame,
    *,
    target_fpr: float = 0.001,
    random_state: int = 42,
    grid: ConsensusGrid = ConsensusGrid(),
    calibration_fraction: float = 0.25,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate persistence settings on development data only.

    Returns:
      run_split: ordinary run-disjoint train/cal/test metrics.
      scenario_holdout: pooled scenario-disjoint metrics where each scenario is
      absent from both training and threshold calibration.

    The detector itself is deterministic and has no fit stage, but threshold
    calibration remains independent of the test rows.
    """
    train, cal, test = split_by_run(feature_df, random_state=random_state)
    del train  # retained conceptually for split symmetry; detector has no fit stage.

    run_rows: list[dict[str, object]] = []
    holdout_rows: list[dict[str, object]] = []

    for single_steps in grid.single_source_steps:
        for dual_steps in grid.dual_source_steps:
            cal_scores = consensus_attack_support(
                cal,
                single_source_steps=single_steps,
                dual_source_steps=dual_steps,
            ).to_numpy()
            threshold = _threshold_at_fpr(
                cal_scores,
                cal["attack_active"].to_numpy(),
                target_fpr=target_fpr,
            )
            test_scores = consensus_attack_support(
                test,
                single_source_steps=single_steps,
                dual_source_steps=dual_steps,
            ).to_numpy()
            metrics = _metrics(test, test_scores, threshold)
            run_rows.append(
                {
                    "single_source_steps": single_steps,
                    "dual_source_steps": dual_steps,
                    "target_fpr": target_fpr,
                    "threshold": threshold,
                    "is_reference_2_12": (
                        single_steps == 12 and dual_steps == 2
                    ),
                    **metrics,
                }
            )

            fold_rows: list[dict[str, object]] = []
            scenarios = sorted(feature_df["scenario"].dropna().astype(str).unique())
            for scenario_index, heldout in enumerate(scenarios):
                _, fold_cal, fold_test = _split_scenario_holdout(
                    feature_df,
                    heldout_scenario=heldout,
                    random_state=random_state + 100 * scenario_index,
                    calibration_fraction=calibration_fraction,
                )
                fold_cal_scores = consensus_attack_support(
                    fold_cal,
                    single_source_steps=single_steps,
                    dual_source_steps=dual_steps,
                ).to_numpy()
                fold_threshold = _threshold_at_fpr(
                    fold_cal_scores,
                    fold_cal["attack_active"].to_numpy(),
                    target_fpr=target_fpr,
                )
                fold_scores = consensus_attack_support(
                    fold_test,
                    single_source_steps=single_steps,
                    dual_source_steps=dual_steps,
                ).to_numpy()
                fold_metric = _metrics(fold_test, fold_scores, fold_threshold)
                fold_rows.append(
                    {
                        "heldout_scenario": heldout,
                        "threshold": fold_threshold,
                        **fold_metric,
                    }
                )

            fold_df = pd.DataFrame(fold_rows)
            benign_samples = int(fold_df["benign_samples"].sum())
            false_positives = int(fold_df["false_positives"].sum())
            attack_samples = int(fold_df["attack_samples"].sum())
            true_positives = int(fold_df["true_positives"].sum())
            attack_rows = fold_df.loc[fold_df["attack_samples"] > 0]
            finite_delays = attack_rows.loc[
                np.isfinite(attack_rows["median_detection_delay"]),
                "median_detection_delay",
            ]

            holdout_rows.append(
                {
                    "single_source_steps": single_steps,
                    "dual_source_steps": dual_steps,
                    "target_fpr": target_fpr,
                    "is_reference_2_12": (
                        single_steps == 12 and dual_steps == 2
                    ),
                    "unseen_scenario_fpr": (
                        false_positives / benign_samples
                        if benign_samples
                        else float("nan")
                    ),
                    "unseen_attack_recall": (
                        true_positives / attack_samples
                        if attack_samples
                        else float("nan")
                    ),
                    "worst_scenario_fpr": float(fold_df["fpr"].max()),
                    "minimum_attack_scenario_recall": (
                        float(attack_rows["recall"].min())
                        if len(attack_rows)
                        else float("nan")
                    ),
                    "median_attack_scenario_delay": (
                        float(finite_delays.median())
                        if len(finite_delays)
                        else float("inf")
                    ),
                    "detected_attack_runs": int(
                        fold_df["detected_attack_runs"].sum()
                    ),
                    "total_attack_runs": int(
                        fold_df["total_attack_runs"].sum()
                    ),
                    "false_positives": false_positives,
                    "benign_samples": benign_samples,
                    "true_positives": true_positives,
                    "attack_samples": attack_samples,
                }
            )

    return pd.DataFrame(run_rows), pd.DataFrame(holdout_rows)


def pareto_frontier(holdout: pd.DataFrame) -> pd.DataFrame:
    """Return non-dominated settings for FPR, recall and detection delay."""
    rows: list[pd.Series] = []
    for idx, candidate in holdout.iterrows():
        dominated = False
        for other_idx, other in holdout.iterrows():
            if idx == other_idx:
                continue
            no_worse = (
                other["unseen_scenario_fpr"] <= candidate["unseen_scenario_fpr"]
                and other["unseen_attack_recall"] >= candidate["unseen_attack_recall"]
                and other["median_attack_scenario_delay"]
                <= candidate["median_attack_scenario_delay"]
            )
            strictly_better = (
                other["unseen_scenario_fpr"] < candidate["unseen_scenario_fpr"]
                or other["unseen_attack_recall"] > candidate["unseen_attack_recall"]
                or other["median_attack_scenario_delay"]
                < candidate["median_attack_scenario_delay"]
            )
            if no_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            rows.append(candidate)

    if not rows:
        return holdout.iloc[0:0].copy()
    return pd.DataFrame(rows).reset_index(drop=True)
