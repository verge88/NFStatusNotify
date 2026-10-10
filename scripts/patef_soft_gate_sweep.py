#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nfnotify_lab.evaluate import (
    _run_delay,
    _split_scenario_holdout,
    _threshold_at_fpr,
    split_by_run,
)
from nfnotify_lab.features import build_features
from nfnotify_lab.patef import (
    PA_TEF_NEUTRAL_SCORE,
    ProvenanceAwareTemporalEvidenceFusion,
    provenance_normalized_attack_gate,
)
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


def _metrics(frame: pd.DataFrame, scores: np.ndarray, threshold: float) -> dict:
    y = frame["attack_active"].to_numpy().astype(bool)
    pred = np.asarray(scores, dtype=float) >= threshold
    benign = ~y
    delay, detected, total = _run_delay(frame, np.asarray(scores), threshold)
    return {
        "false_positives": int(pred[benign].sum()) if benign.any() else 0,
        "benign_samples": int(benign.sum()),
        "true_positives": int(pred[y].sum()) if y.any() else 0,
        "attack_samples": int(y.sum()),
        "fpr": float(pred[benign].mean()) if benign.any() else float("nan"),
        "recall": float(pred[y].mean()) if y.any() else float("nan"),
        "median_detection_delay": delay,
        "detected_attack_runs": detected,
        "total_attack_runs": total,
    }


def _fit_learned(
    train: pd.DataFrame,
    cal: pd.DataFrame,
    random_state: int,
) -> ProvenanceAwareTemporalEvidenceFusion:
    model = ProvenanceAwareTemporalEvidenceFusion(
        random_state=random_state,
        use_decision_gate=False,
        include_consensus_meta=True,
    )
    model.fit(train, train["attack_active"])
    model.calibrate(cal, cal["attack_active"])
    return model


def _scores(
    model: ProvenanceAwareTemporalEvidenceFusion,
    frame: pd.DataFrame,
    single_steps: int,
    dual_steps: int,
) -> tuple[np.ndarray, np.ndarray]:
    learned = model.learned_scores(frame)
    gate = provenance_normalized_attack_gate(
        frame,
        single_source_steps=single_steps,
        dual_source_steps=dual_steps,
    ).to_numpy(dtype=float)
    hybrid = np.where(gate > 0.0, learned, PA_TEF_NEUTRAL_SCORE)
    return gate, hybrid


def _aggregate_holdout(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["variant", "single_source_steps", "dual_source_steps"]
    for key, group in detail.groupby(keys, sort=True):
        variant, single_steps, dual_steps = key
        benign = int(group["benign_samples"].sum())
        attack = int(group["attack_samples"].sum())
        fp = int(group["false_positives"].sum())
        tp = int(group["true_positives"].sum())
        attack_rows = group.loc[group["attack_samples"] > 0]
        finite_delay = attack_rows.loc[
            np.isfinite(attack_rows["median_detection_delay"]),
            "median_detection_delay",
        ]
        rows.append(
            {
                "variant": variant,
                "single_source_steps": int(single_steps),
                "dual_source_steps": int(dual_steps),
                "unseen_scenario_fpr": fp / benign if benign else float("nan"),
                "unseen_attack_recall": tp / attack if attack else float("nan"),
                "worst_scenario_fpr": float(group["fpr"].max()),
                "minimum_attack_scenario_recall": (
                    float(attack_rows["recall"].min())
                    if len(attack_rows)
                    else float("nan")
                ),
                "median_attack_scenario_delay": (
                    float(finite_delay.median())
                    if len(finite_delay)
                    else float("inf")
                ),
                "false_positives": fp,
                "benign_samples": benign,
                "true_positives": tp,
                "attack_samples": attack,
                "detected_attack_runs": int(
                    group["detected_attack_runs"].sum()
                ),
                "total_attack_runs": int(group["total_attack_runs"].sum()),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--seeds", type=int, default=60)
    parser.add_argument("--steps", type=int, default=90)
    parser.add_argument("--target-fpr", type=float, default=0.001)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--single", default="1,2,3,4,5,6,7")
    parser.add_argument("--dual", type=int, default=1)
    args = parser.parse_args()

    single_grid = tuple(
        int(value.strip()) for value in args.single.split(",") if value.strip()
    )
    if not single_grid or min(single_grid) < 1 or args.dual < 1:
        raise SystemExit("persistence steps must be positive")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    raw = simulate_dataset(
        DEFAULT_SCENARIOS,
        seeds=range(args.seeds),
        steps=args.steps,
    )
    features = build_features(raw)

    train, cal, test = split_by_run(features, random_state=args.random_state)
    run_model = _fit_learned(train, cal, args.random_state)
    run_rows = []

    for single_steps in single_grid:
        cal_gate, cal_hybrid = _scores(
            run_model, cal, single_steps, args.dual
        )
        test_gate, test_hybrid = _scores(
            run_model, test, single_steps, args.dual
        )
        for variant, cal_scores, test_scores in (
            ("gate_only", cal_gate, test_gate),
            ("hybrid", cal_hybrid, test_hybrid),
        ):
            threshold = _threshold_at_fpr(
                cal_scores,
                cal["attack_active"].to_numpy(),
                target_fpr=args.target_fpr,
            )
            run_rows.append(
                {
                    "variant": variant,
                    "single_source_steps": single_steps,
                    "dual_source_steps": args.dual,
                    "threshold": threshold,
                    **_metrics(test, test_scores, threshold),
                }
            )

    run_df = pd.DataFrame(run_rows)
    holdout_rows = []
    scenarios = sorted(features["scenario"].dropna().astype(str).unique())

    for scenario_index, heldout in enumerate(scenarios):
        train, cal, test = _split_scenario_holdout(
            features,
            heldout_scenario=heldout,
            random_state=args.random_state + 100 * scenario_index,
            calibration_fraction=0.25,
        )
        model = _fit_learned(
            train,
            cal,
            args.random_state + 1000 * scenario_index,
        )
        for single_steps in single_grid:
            cal_gate, cal_hybrid = _scores(
                model, cal, single_steps, args.dual
            )
            test_gate, test_hybrid = _scores(
                model, test, single_steps, args.dual
            )
            for variant, cal_scores, test_scores in (
                ("gate_only", cal_gate, test_gate),
                ("hybrid", cal_hybrid, test_hybrid),
            ):
                threshold = _threshold_at_fpr(
                    cal_scores,
                    cal["attack_active"].to_numpy(),
                    target_fpr=args.target_fpr,
                )
                holdout_rows.append(
                    {
                        "heldout_scenario": heldout,
                        "variant": variant,
                        "single_source_steps": single_steps,
                        "dual_source_steps": args.dual,
                        "threshold": threshold,
                        **_metrics(test, test_scores, threshold),
                    }
                )

    holdout_detail = pd.DataFrame(holdout_rows)
    holdout = _aggregate_holdout(holdout_detail)

    eligible = holdout.loc[
        (holdout["variant"] == "hybrid")
        & (holdout["unseen_scenario_fpr"] <= args.target_fpr)
        & (holdout["worst_scenario_fpr"] <= args.target_fpr)
    ].copy()
    candidate = None
    if len(eligible):
        best = eligible.sort_values(
            [
                "unseen_attack_recall",
                "median_attack_scenario_delay",
                "single_source_steps",
            ],
            ascending=[False, True, True],
        ).iloc[0]
        candidate = best.to_dict()

    paired = holdout.pivot(
        index=["single_source_steps", "dual_source_steps"],
        columns="variant",
        values=[
            "unseen_scenario_fpr",
            "unseen_attack_recall",
            "worst_scenario_fpr",
            "median_attack_scenario_delay",
        ],
    )
    paired.columns = ["_".join(col) for col in paired.columns]
    paired = paired.reset_index()
    paired["hybrid_recall_gain_over_gate"] = (
        paired["unseen_attack_recall_hybrid"]
        - paired["unseen_attack_recall_gate_only"]
    )
    paired["hybrid_fpr_delta_vs_gate"] = (
        paired["unseen_scenario_fpr_hybrid"]
        - paired["unseen_scenario_fpr_gate_only"]
    )

    run_df.to_csv(out / "soft-gate-run-split.csv", index=False)
    holdout_detail.to_csv(out / "soft-gate-holdout-detail.csv", index=False)
    holdout.to_csv(out / "soft-gate-holdout-summary.csv", index=False)
    paired.to_csv(out / "soft-gate-paired.csv", index=False)

    summary = {
        "development_only": True,
        "real_test_used_for_selection": False,
        "target_fpr": args.target_fpr,
        "single_source_grid": list(single_grid),
        "dual_source_steps": args.dual,
        "selected_hybrid_candidate": candidate,
        "reference_v2_single_source_steps": 7,
    }
    (out / "soft-gate-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print(json.dumps(summary, indent=2))
    print(holdout.to_string(index=False))
    print(paired.to_string(index=False))


if __name__ == "__main__":
    main()
