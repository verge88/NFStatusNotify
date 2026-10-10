#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nfnotify_lab.detectors import build_detector
from nfnotify_lab.evaluate import _threshold_at_fpr, split_by_run
from nfnotify_lab.features import build_features
from nfnotify_lab.schema import validate_observations
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset
from nfnotify_lab.telemetry_degradation import (
    DEGRADATION_VARIANTS,
    apply_degradation,
)


DETECTORS = ("semantic_guard", "consensus_guard", "patef")


def fit_detectors(
    *,
    target_fpr: float,
    random_state: int,
    training_seeds: int,
    steps: int,
):
    synthetic = simulate_dataset(
        DEFAULT_SCENARIOS,
        seeds=range(training_seeds),
        steps=steps,
    )
    training_features = build_features(synthetic)
    train, cal, _ = split_by_run(training_features, random_state=random_state)

    fitted = {}
    for name in DETECTORS:
        detector = build_detector(name, random_state=random_state)
        detector.fit(train, train["attack_active"])
        if hasattr(detector, "calibrate"):
            detector.calibrate(cal, cal["attack_active"])
        cal_scores = detector.score_samples(cal)
        threshold = _threshold_at_fpr(
            cal_scores,
            cal["attack_active"].to_numpy(),
            target_fpr=target_fpr,
        )
        fitted[name] = (detector, float(threshold))
    return fitted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--replicate-id", type=int, default=0)
    parser.add_argument("--target-fpr", type=float, default=0.001)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--training-seeds", type=int, default=60)
    parser.add_argument("--steps", type=int, default=90)
    args = parser.parse_args()

    raw = validate_observations(pd.read_csv(args.observations))
    if raw["attack_active"].astype(int).any():
        raise SystemExit("telemetry-degradation matrix requires a benign real trace")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    views = out / "views"
    views.mkdir(exist_ok=True)

    fitted = fit_detectors(
        target_fpr=args.target_fpr,
        random_state=args.random_state,
        training_seeds=args.training_seeds,
        steps=args.steps,
    )

    rows: list[dict[str, object]] = []
    for variant in DEGRADATION_VARIANTS:
        degraded = validate_observations(apply_degradation(raw, variant))
        features = build_features(degraded)

        variant_dir = views / variant
        variant_dir.mkdir(exist_ok=True)
        degraded.to_csv(variant_dir / "observations.csv", index=False)
        features.to_csv(variant_dir / "features.csv", index=False)

        for detector_name, (detector, threshold) in fitted.items():
            scores = np.asarray(detector.score_samples(features), dtype=float)
            alerts = scores >= threshold
            alert_count = int(alerts.sum())
            first_alert_t = (
                int(features.loc[alerts, "t"].iloc[0]) if alert_count else None
            )
            rows.append(
                {
                    "replicate_id": args.replicate_id,
                    "variant": variant,
                    "detector": detector_name,
                    "rows": int(len(features)),
                    "alerts": alert_count,
                    "alert_rate": float(alerts.mean()),
                    "benign_run_alert_free": bool(alert_count == 0),
                    "threshold": threshold,
                    "max_risk": float(scores.max()) if len(scores) else float("nan"),
                    "median_risk": (
                        float(np.median(scores)) if len(scores) else float("nan")
                    ),
                    "first_alert_t": first_alert_t,
                    "mean_m_nrf": float(features["m_nrf"].mean()),
                    "mean_m_ausf": float(features["m_ausf"].mean()),
                    "mean_m_route": float(features["m_route"].mean()),
                    "mean_m_notify": float(features["m_notify"].mean()),
                }
            )

    result = pd.DataFrame(rows).sort_values(
        ["variant", "detector"]
    ).reset_index(drop=True)
    result.to_csv(out / "telemetry-degradation-matrix.csv", index=False)

    summary = {
        "replicate_id": args.replicate_id,
        "variants": list(DEGRADATION_VARIANTS),
        "detectors": list(DETECTORS),
        "target_fpr": args.target_fpr,
        "all_benign": True,
        "total_detector_variant_cases": int(len(result)),
        "cases_with_alerts": int((result["alerts"] > 0).sum()),
    }
    (out / "telemetry-degradation-summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
