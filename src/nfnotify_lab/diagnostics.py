from __future__ import annotations

import numpy as np
import pandas as pd

from .detectors import detector_names
from .evaluate import _fit_detector, _threshold_at_fpr, split_by_run


def calibration_diagnostics(
    feature_df: pd.DataFrame,
    target_fpr: float = 0.001,
    random_state: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Describe whether calibration score ties make the target FPR attainable."""
    train, cal, _ = split_by_run(feature_df, random_state=random_state)
    summary_rows: list[dict[str, object]] = []
    tie_rows: list[dict[str, object]] = []

    for name in detector_names():
        _, scores = _fit_detector(name, train, cal, random_state)
        threshold = _threshold_at_fpr(
            scores,
            cal["attack_active"].to_numpy(),
            target_fpr=target_fpr,
        )

        scored = cal[["scenario", "attack_active"]].copy().reset_index(drop=True)
        scored["score"] = np.asarray(scores, dtype=float)
        benign = scored.loc[scored["attack_active"].to_numpy() == 0].copy()
        if benign.empty:
            continue

        benign_scores = benign["score"].to_numpy(dtype=float)
        max_score = float(np.max(benign_scores))
        max_mask = np.isclose(
            benign_scores,
            max_score,
            rtol=0.0,
            atol=max(1e-12, abs(max_score) * 1e-12),
        )
        max_tie_count = int(max_mask.sum())
        benign_samples = int(len(benign))
        fp_budget = float(target_fpr * benign_samples)

        summary_rows.append(
            {
                "detector": name,
                "target_fpr": target_fpr,
                "benign_samples": benign_samples,
                "calibration_threshold": float(threshold),
                "benign_max_score": max_score,
                "threshold_above_benign_max": bool(threshold > max_score),
                "unique_benign_scores": int(np.unique(benign_scores).size),
                "max_score_tie_count": max_tie_count,
                "max_score_tie_rate": max_tie_count / benign_samples,
                "allowed_false_positive_budget": fp_budget,
                "max_score_tie_exceeds_budget": bool(max_tie_count > fp_budget),
                "benign_score_q99": float(np.quantile(benign_scores, 0.99)),
                "benign_score_q999": float(np.quantile(benign_scores, 0.999)),
            }
        )

        tied = benign.loc[max_mask]
        for scenario, group in tied.groupby("scenario", sort=True):
            scenario_benign = int((benign["scenario"] == scenario).sum())
            count = int(len(group))
            tie_rows.append(
                {
                    "detector": name,
                    "scenario": scenario,
                    "benign_max_score": max_score,
                    "scenario_benign_samples": scenario_benign,
                    "max_score_ties": count,
                    "max_score_tie_rate_within_scenario": (
                        count / scenario_benign if scenario_benign else float("nan")
                    ),
                    "share_of_all_max_score_ties": count / max_tie_count,
                }
            )

    return pd.DataFrame(summary_rows), pd.DataFrame(tie_rows)


def generalization_risk_register(
    holdout: pd.DataFrame,
    target_fpr: float = 0.001,
) -> pd.DataFrame:
    """Rank held-out scenarios by low-FPR generalization failure."""
    out = holdout.copy()
    out = out.loc[out["benign_samples"] > 0].copy()
    out["target_fpr"] = target_fpr
    out["fpr_excess"] = out["fpr"] - target_fpr
    out["exceeds_target_fpr"] = out["fpr"] > target_fpr
    out["fpr_ratio_to_target"] = out["fpr"] / target_fpr
    columns = [
        "detector",
        "heldout_scenario",
        "target_fpr",
        "fpr",
        "fpr_excess",
        "fpr_ratio_to_target",
        "exceeds_target_fpr",
        "false_positives",
        "benign_samples",
        "recall",
        "attack_samples",
        "threshold",
    ]
    return out[columns].sort_values(
        ["exceeds_target_fpr", "fpr", "detector", "heldout_scenario"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)
