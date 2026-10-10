#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from nfnotify_lab.replicates import (
    collect_replicates,
    infrastructure_summary,
    numeric_summary,
    proportion_summary,
    study_summary,
)


def _format(value: float | int | str | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def write_markdown(
    path: Path,
    detector_df: pd.DataFrame,
    numeric: pd.DataFrame,
    proportions: pd.DataFrame,
    summary: dict[str, object],
) -> None:
    lines = [
        "# Open5GS replicated failover study",
        "",
        (
            f"Valid independent lab instantiations: "
            f"{summary['valid_replicates']}/{summary['requested_replicates']}"
        ),
        "",
        "## Detector summary",
        "",
        "| Detector | Mean sample recall | SD | Mean FPR | Run detection | Median delay | Benign alert-free |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for detector, data in summary["detectors"].items():
        n = summary["valid_replicates"]
        lines.append(
            "| "
            + " | ".join(
                [
                    detector,
                    _format(data["mean_sample_recall"]),
                    _format(data["sd_sample_recall"]),
                    _format(data["mean_fpr"]),
                    _format(data["mean_attack_run_detection_rate"]),
                    _format(data["median_detection_delay"]),
                    f"{data['benign_alert_free_runs']}/{n}",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Wilson 95% intervals",
            "",
            "| Detector | Metric | Successes | n | Proportion | 95% CI |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in proportions.itertuples(index=False):
        lines.append(
            f"| {row.detector} | {row.metric} | {row.successes} | {row.n} | "
            f"{row.proportion:.4f} | "
            f"[{row.wilson_95_ci_low:.4f}, {row.wilson_95_ci_high:.4f}] |"
        )

    lines.extend(
        [
            "",
            "## Bootstrap dispersion",
            "",
            "Bootstrap CIs are percentile 95% intervals over independent replicate-level observations.",
            "With eight replicates these intervals are exploratory rather than asymptotic guarantees.",
            "",
        ]
    )
    for detector in detector_df["detector"].drop_duplicates():
        lines.append(f"### {detector}")
        lines.append("")
        subset = numeric.loc[numeric["detector"] == detector]
        lines.append(
            "| Metric | Mean ± SD | Median [IQR] | Range | Bootstrap mean 95% CI |"
        )
        lines.append("| --- | --- | --- | --- | --- |")
        for row in subset.itertuples(index=False):
            lines.append(
                f"| {row.metric} | {row.mean:.4f} ± {row.sd:.4f} | "
                f"{row.median:.4f} [{row.q1:.4f}, {row.q3:.4f}] | "
                f"[{row.min:.4f}, {row.max:.4f}] | "
                f"[{row.bootstrap_mean_ci_low:.4f}, "
                f"{row.bootstrap_mean_ci_high:.4f}] |"
            )
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--requested-runs", type=int, default=8)
    parser.add_argument("--min-runs", type=int, default=6)
    args = parser.parse_args()

    root = Path(args.root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    detector_df, infra_df = collect_replicates(root)
    valid_runs = int(infra_df["replicate_id"].nunique()) if len(infra_df) else 0
    if valid_runs < args.min_runs:
        raise SystemExit(
            f"only {valid_runs} valid replicated runs; minimum is {args.min_runs}"
        )

    numeric = numeric_summary(detector_df)
    infra_stats = infrastructure_summary(infra_df)
    proportions = proportion_summary(detector_df)
    summary = study_summary(
        detector_df,
        infra_df,
        requested_replicates=args.requested_runs,
    )

    detector_df.to_csv(out / "replicate-detector-metrics.csv", index=False)
    infra_df.to_csv(out / "replicate-infrastructure.csv", index=False)
    numeric.to_csv(out / "replicate-dispersion.csv", index=False)
    infra_stats.to_csv(out / "replicate-infrastructure-stats.csv", index=False)
    proportions.to_csv(out / "replicate-proportions.csv", index=False)
    (out / "replicate-study-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    write_markdown(
        out / "replicate-study-summary.md",
        detector_df,
        numeric,
        proportions,
        summary,
    )
    print(json.dumps(summary, indent=2))
    print(numeric.to_string(index=False))
    print(proportions.to_string(index=False))


if __name__ == "__main__":
    main()
