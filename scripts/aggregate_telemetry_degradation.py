#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nfnotify_lab.replicates import bootstrap_interval, wilson_interval


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--requested-runs", type=int, default=4)
    parser.add_argument("--min-runs", type=int, default=3)
    args = parser.parse_args()

    paths = sorted(Path(args.root).rglob("telemetry-degradation-matrix.csv"))
    if not paths:
        raise SystemExit("no telemetry-degradation-matrix.csv files found")

    frames = [pd.read_csv(path) for path in paths]
    data = pd.concat(frames, ignore_index=True)
    valid_runs = int(data["replicate_id"].nunique())
    if valid_runs < args.min_runs:
        raise SystemExit(
            f"only {valid_runs} valid degradation runs; minimum is {args.min_runs}"
        )

    rows: list[dict[str, object]] = []
    for (variant, detector), group in data.groupby(
        ["variant", "detector"], sort=True
    ):
        alert_free = group["benign_run_alert_free"].astype(bool)
        successes = int(alert_free.sum())
        total = int(len(alert_free))
        wilson_low, wilson_high = wilson_interval(successes, total)
        alert_rates = group["alert_rate"].astype(float).to_numpy()
        max_risks = group["max_risk"].astype(float).to_numpy()
        alert_ci = bootstrap_interval(alert_rates, statistic="mean")
        risk_ci = bootstrap_interval(max_risks, statistic="mean")

        rows.append(
            {
                "variant": variant,
                "detector": detector,
                "runs": total,
                "alert_free_runs": successes,
                "runs_with_alerts": total - successes,
                "alert_free_proportion": successes / total,
                "alert_free_wilson_95_low": wilson_low,
                "alert_free_wilson_95_high": wilson_high,
                "mean_alert_rate": float(np.mean(alert_rates)),
                "sd_alert_rate": (
                    float(np.std(alert_rates, ddof=1)) if total > 1 else 0.0
                ),
                "max_alert_rate": float(np.max(alert_rates)),
                "bootstrap_mean_alert_rate_ci_low": alert_ci[0],
                "bootstrap_mean_alert_rate_ci_high": alert_ci[1],
                "mean_max_risk": float(np.mean(max_risks)),
                "sd_max_risk": (
                    float(np.std(max_risks, ddof=1)) if total > 1 else 0.0
                ),
                "max_max_risk": float(np.max(max_risks)),
                "bootstrap_mean_max_risk_ci_low": risk_ci[0],
                "bootstrap_mean_max_risk_ci_high": risk_ci[1],
            }
        )

    aggregate = pd.DataFrame(rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data.to_csv(out / "telemetry-degradation-replicates.csv", index=False)
    aggregate.to_csv(out / "telemetry-degradation-aggregate.csv", index=False)

    consensus = aggregate.loc[aggregate["detector"] == "consensus_guard"].copy()
    worst = consensus.sort_values(
        ["runs_with_alerts", "mean_alert_rate", "mean_max_risk"],
        ascending=False,
    ).iloc[0]
    summary = {
        "requested_runs": args.requested_runs,
        "valid_runs": valid_runs,
        "variants": int(data["variant"].nunique()),
        "detectors": sorted(data["detector"].unique().tolist()),
        "consensus_guard_all_cases_alert_free": bool(
            (consensus["runs_with_alerts"] == 0).all()
        ),
        "consensus_guard_worst_variant": {
            "variant": str(worst["variant"]),
            "runs_with_alerts": int(worst["runs_with_alerts"]),
            "mean_alert_rate": float(worst["mean_alert_rate"]),
            "max_max_risk": float(worst["max_max_risk"]),
        },
    }
    (out / "telemetry-degradation-study.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print(aggregate.to_string(index=False))


if __name__ == "__main__":
    main()
