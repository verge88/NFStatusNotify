#!/usr/bin/env python3
"""Post-hoc diagnostic ONLY: fairer partial-source rule on exposed test views.

Not the precommitted Stage-6 H1/H2 analysis and not a new heldout validation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nfnotify_lab.available_consensus import available_source_consensus_support
from nfnotify_lab.consensus import consensus_attack_support
from nfnotify_lab.residual_freshness import availability_mask, make_view
from nfnotify_lab.simulator import simulate_dataset
from stage6_residual_study import CHALLENGE_SCENARIOS, SEEDS_TEST, STEPS, VIEWS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = simulate_dataset(CHALLENGE_SCENARIOS, SEEDS_TEST, STEPS)
    rows = []
    for view in VIEWS:
        frame = make_view(raw, view)
        mask = availability_mask(frame)
        reference = consensus_attack_support(frame).to_numpy(float) > 0
        stronger = available_source_consensus_support(frame).to_numpy(float) > 0
        assert not np.any(reference & ~stronger)
        for scenario in CHALLENGE_SCENARIOS:
            selected = frame["scenario"].eq(scenario.name).to_numpy()
            subset = frame.loc[selected]
            for name, pred in (
                ("consensus_guard", reference[selected]),
                ("available_source_consensus_posthoc", stronger[selected]),
            ):
                y = subset["attack_active"].to_numpy(bool)
                benign = ~y
                rows.append({
                    "view": view,
                    "arm": name,
                    "scenario": scenario.name,
                    "mask_groups": ";".join(sorted(set(mask[selected]))),
                    "benign_samples": int(benign.sum()),
                    "attack_samples": int(y.sum()),
                    "fp": int(pred[benign].sum()),
                    "tp": int(pred[y].sum()),
                    "fpr": float(pred[benign].mean()) if benign.any() else None,
                    "recall": float(pred[y].mean()) if y.any() else None,
                })
    detail = pd.DataFrame(rows)
    summary = []
    for (view, arm), g in detail.groupby(["view", "arm"]):
        benign = int(g["benign_samples"].sum())
        active = int(g["attack_samples"].sum())
        summary.append({
            "view": view, "arm": arm,
            "benign_samples": benign,
            "attack_samples": active,
            "fp": int(g["fp"].sum()),
            "tp": int(g["tp"].sum()),
            "fpr": float(g["fp"].sum() / benign),
            "recall": float(g["tp"].sum() / active),
        })
    summary_df = pd.DataFrame(summary)
    detail.to_csv(out / "available-baseline-by-scenario.csv", index=False)
    summary_df.to_csv(out / "available-baseline-summary.csv", index=False)
    (out / "available-baseline-decision.json").write_text(
        json.dumps({
            "exploratory_after_stage6_test_inspection": True,
            "new_independent_test_data": False,
            "changes_preregistered_h1_h2_h3": False,
            "baseline_extension": "eight-step single available NRF-correlated source",
            "fpr_target": 0.001,
            "claim_of_ml_superiority_authorized": False,
        }, indent=2), encoding="utf-8"
    )
    print(summary_df.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
