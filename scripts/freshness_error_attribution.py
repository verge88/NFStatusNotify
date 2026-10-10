#!/usr/bin/env python3
"""Post-hoc diagnostic only: attribute oracle-alignment false alarms by scenario."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nfnotify_lab.detectors import build_detector
from nfnotify_lab.evaluate import _split_scenario_holdout, _threshold_at_fpr
from nfnotify_lab.features import build_features
from nfnotify_lab.freshness import attach_acquisition_times, aligned_features, observed_view
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset

VIEWS = ("route_lag4", "both_lag2", "route_lag8", "route_jitter2_6")
FEATURES = (
    "state_conflict_persist",
    "single_source_conflict_persist",
    "dual_source_conflict_persist",
    "delta_route",
    "delta_nrf_ausf",
    "recent_nrf_update_seen_12",
    "recent_nrf_endpoint_changed_12",
    "recovery_active",
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    args = p.parse_args()
    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    train_data = build_features(simulate_dataset(DEFAULT_SCENARIOS, range(60), 90))
    test_data = simulate_dataset(DEFAULT_SCENARIOS, range(100, 140), 90)
    details = []
    alarms = []
    for fold, heldout in enumerate(sorted(train_data["scenario"].unique())):
        _, cal, _ = _split_scenario_holdout(
            train_data, heldout, 42 + 100 * fold, 0.25
        )
        detector = build_detector("patef_gate_only")
        threshold = _threshold_at_fpr(
            detector.score_samples(cal), cal["attack_active"].to_numpy(), 0.001
        )
        raw = test_data.loc[test_data["scenario"] == heldout]
        timed = attach_acquisition_times(raw)
        for view in VIEWS:
            observed = observed_view(timed, view)
            frame_unaligned = build_features(observed)
            frame_aligned = aligned_features(observed)
            benign = ~frame_unaligned["attack_active"].astype(bool)
            predicted = {}
            for alignment, frame in (
                ("unaligned", frame_unaligned),
                ("aligned", frame_aligned),
            ):
                scores = np.asarray(detector.score_samples(frame), dtype=float)
                predicted[alignment] = scores >= threshold
                mask = benign & predicted[alignment]
                details.append({
                    "view": view,
                    "scenario": heldout,
                    "alignment": alignment,
                    "fp": int(mask.sum()),
                    "benign_samples": int(benign.sum()),
                    "threshold": float(threshold),
                })
                for idx in frame.index[mask]:
                    evidence = {
                        k: (
                            float(frame.loc[idx, k])
                            if pd.notna(frame.loc[idx, k])
                            else None
                        )
                        for k in FEATURES
                    }
                    alarms.append({
                        "view": view,
                        "heldout_scenario": heldout,
                        "alignment": alignment,
                        "run_id": frame.loc[idx, "run_id"],
                        "t": int(frame.loc[idx, "t"]),
                        "route_origin_t": (
                            float(observed.loc[idx, "route_origin_t"])
                            if pd.notna(observed.loc[idx, "route_origin_t"]) else None
                        ),
                        "nrf_origin_t": (
                            float(observed.loc[idx, "nrf_origin_t"])
                            if pd.notna(observed.loc[idx, "nrf_origin_t"]) else None
                        ),
                        **evidence,
                    })
            assert predicted["unaligned"].shape == predicted["aligned"].shape
        print(f"diagnosed scenario: {heldout}", flush=True)

    frame = pd.DataFrame(details)
    incidents = pd.DataFrame(alarms)
    frame.to_csv(dest / "false-alarm-by-scenario.csv", index=False)
    incidents.to_csv(dest / "false-alarm-points.csv", index=False)
    summary = (
        frame.groupby(["view", "alignment"], sort=False)["fp"]
        .sum().reset_index().to_dict("records")
    )
    top = (
        frame.loc[frame["fp"] > 0]
        .sort_values(["view", "alignment", "fp"], ascending=[True, True, False])
        .to_dict("records")
    )
    outcome = {
        "post_hoc": True,
        "uses_prior_frozen_test_scenarios": True,
        "purpose": "diagnose locked negative result, not tune/choose model",
        "counts": summary,
        "affected_scenarios": top,
    }
    (dest / "error-attribution.json").write_text(
        json.dumps(outcome, indent=2), encoding="utf-8"
    )
    print(json.dumps(outcome, indent=2), flush=True)


if __name__ == "__main__":
    main()
