#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from nfnotify_lab.control import summarize_external_replay


DETECTORS = ("semantic_guard", "consensus_guard", "patef")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()

    root = Path(args.root)
    evidence = json.loads((root / "evidence-summary.json").read_text())
    meta = json.loads((root / "failover-meta.json").read_text())
    counter_obs = pd.read_csv(root / "counterfactual-observations.csv")

    a = evidence["udm_a"]
    b = evidence["udm_b"]
    assert evidence["baseline_nrf"] == [a], evidence
    assert evidence["baseline_ausf"] == [a], evidence
    assert evidence["baseline_route"] == [a], evidence
    assert evidence["failover_nrf"] == [b], evidence
    assert evidence["failover_ausf"] == [b], evidence
    assert evidence["failover_route"] == [b], evidence
    assert evidence["recovery_nrf"] == [a], evidence
    assert evidence["recovery_ausf"] == [a], evidence
    assert evidence["recovery_route"] == [a], evidence
    assert counter_obs["attack_active"].astype(bool).any()

    result: dict[str, object] = {
        "replicate_id": int(meta.get("replicate_id", 0)),
        "target_fpr": None,
    }
    for detector in DETECTORS:
        counter_summary = json.loads(
            (
                root
                / "counterfactual"
                / f"control-summary-{detector}.json"
            ).read_text()
        )
        scores = pd.read_csv(
            root / "counterfactual" / f"control-scores-{detector}.csv"
        )
        result[detector] = summarize_external_replay(
            detector,
            counter_obs,
            scores,
            counter_summary,
        )
        if result["target_fpr"] is None:
            result["target_fpr"] = float(counter_summary["target_fpr"])

    result["any_detector_meets_external_target"] = any(
        bool(result[name]["meets_external_target"]) for name in DETECTORS
    )
    result["any_detector_meets_run_detection_target"] = any(
        bool(result[name]["meets_run_detection_target"]) for name in DETECTORS
    )

    (root / "counterfactual-result.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
