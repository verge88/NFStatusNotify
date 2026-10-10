#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DETECTORS = (
    "consensus_guard",
    "patef_gate_only",
    "patef_learned_only",
    "patef",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()

    root = Path(args.root)
    metrics = pd.read_csv(root / "metrics.csv").set_index("detector")
    holdout = pd.read_csv(root / "scenario-holdout-summary.csv").set_index("detector")

    missing = [name for name in DETECTORS if name not in metrics.index]
    if missing:
        raise SystemExit(f"missing detector metrics: {missing}")
    missing = [name for name in DETECTORS if name not in holdout.index]
    if missing:
        raise SystemExit(f"missing holdout metrics: {missing}")

    rows = []
    for name in DETECTORS:
        m = metrics.loc[name]
        h = holdout.loc[name]
        rows.append(
            {
                "detector": name,
                "run_fpr": float(m["fpr"]),
                "run_recall": float(m["recall_at_target_fpr"]),
                "run_delay": float(m["median_detection_delay"]),
                "holdout_fpr": float(h["unseen_scenario_fpr"]),
                "holdout_recall": float(h["unseen_attack_recall"]),
                "holdout_worst_fpr": float(h["worst_scenario_fpr"]),
                "holdout_min_attack_recall": float(
                    h["minimum_attack_scenario_recall"]
                ),
                "holdout_delay": float(h["median_attack_scenario_delay"]),
                "detected_attack_runs": int(h["detected_attack_runs"]),
                "total_attack_runs": int(h["total_attack_runs"]),
            }
        )
    table = pd.DataFrame(rows).set_index("detector")

    gate = table.loc["patef_gate_only"]
    learned = table.loc["patef_learned_only"]
    full = table.loc["patef"]

    report = {
        "comparison": table.reset_index().to_dict(orient="records"),
        "incremental_learned_value_over_gate": {
            "run_recall_delta": float(full["run_recall"] - gate["run_recall"]),
            "run_fpr_delta": float(full["run_fpr"] - gate["run_fpr"]),
            "run_delay_delta": float(full["run_delay"] - gate["run_delay"]),
            "holdout_recall_delta": float(
                full["holdout_recall"] - gate["holdout_recall"]
            ),
            "holdout_fpr_delta": float(
                full["holdout_fpr"] - gate["holdout_fpr"]
            ),
            "holdout_delay_delta": float(
                full["holdout_delay"] - gate["holdout_delay"]
            ),
        },
        "incremental_gate_value_over_learned_only": {
            "run_recall_delta": float(full["run_recall"] - learned["run_recall"]),
            "run_fpr_delta": float(full["run_fpr"] - learned["run_fpr"]),
            "run_delay_delta": float(full["run_delay"] - learned["run_delay"]),
            "holdout_recall_delta": float(
                full["holdout_recall"] - learned["holdout_recall"]
            ),
            "holdout_fpr_delta": float(
                full["holdout_fpr"] - learned["holdout_fpr"]
            ),
            "holdout_delay_delta": float(
                full["holdout_delay"] - learned["holdout_delay"]
            ),
        },
        "gate_and_full_have_identical_classification_metrics": bool(
            full["run_recall"] == gate["run_recall"]
            and full["run_fpr"] == gate["run_fpr"]
            and full["holdout_recall"] == gate["holdout_recall"]
            and full["holdout_fpr"] == gate["holdout_fpr"]
            and full["holdout_delay"] == gate["holdout_delay"]
        ),
    }

    (root / "patef-v2-causal-ablation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    table.reset_index().to_csv(root / "patef-v2-causal-ablation.csv", index=False)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
