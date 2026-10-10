#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from nfnotify_lab.control import summarize_external_replay


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
    observations = pd.read_csv(root / "counterfactual-observations.csv")
    rows = []
    benign = {}

    for name in DETECTORS:
        real_summary = json.loads(
            (root / "real" / f"control-summary-{name}.json").read_text()
        )
        counter_summary = json.loads(
            (root / "counterfactual" / f"control-summary-{name}.json").read_text()
        )
        scores = pd.read_csv(
            root / "counterfactual" / f"control-scores-{name}.csv"
        )
        result = summarize_external_replay(
            name,
            observations,
            scores,
            counter_summary,
        )
        rows.append(result)
        benign[name] = {
            "alerts": int(real_summary["alerts"]),
            "threshold": float(real_summary["threshold"]),
            "max_risk": float(real_summary["max_risk"]),
        }

    table = pd.DataFrame(rows).set_index("detector")
    gate = table.loc["patef_gate_only"]
    learned = table.loc["patef_learned_only"]
    full = table.loc["patef"]

    report = {
        "benign_real": benign,
        "counterfactual": table.reset_index().to_dict(orient="records"),
        "incremental_learned_value_over_gate": {
            "recall_delta": float(full["recall"] - gate["recall"]),
            "fpr_delta": float(full["fpr"] - gate["fpr"]),
            "delay_delta": (
                None
                if pd.isna(full["median_detection_delay"])
                or pd.isna(gate["median_detection_delay"])
                else float(
                    full["median_detection_delay"]
                    - gate["median_detection_delay"]
                )
            ),
        },
        "incremental_gate_value_over_learned_only": {
            "recall_delta": float(full["recall"] - learned["recall"]),
            "fpr_delta": float(full["fpr"] - learned["fpr"]),
        },
        "gate_and_full_identical_on_real_counterfactual": bool(
            full["recall"] == gate["recall"]
            and full["fpr"] == gate["fpr"]
            and full["median_detection_delay"] == gate["median_detection_delay"]
        ),
    }

    (root / "patef-v2-real-causal-ablation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    table.reset_index().to_csv(
        root / "patef-v2-real-causal-ablation.csv", index=False
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
