#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from nfnotify_lab.replicates import bootstrap_interval, wilson_interval


def _finite(values: pd.Series) -> np.ndarray:
    return pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)


def _metric_summary(values: pd.Series) -> dict[str, object]:
    arr = _finite(values)
    if not len(arr):
        return {
            "n": 0,
            "mean": None,
            "sd": None,
            "median": None,
            "min": None,
            "max": None,
            "bootstrap_mean_95_ci": [None, None],
        }
    low, high = bootstrap_interval(arr, statistic="mean")
    return {
        "n": int(len(arr)),
        "mean": float(np.mean(arr)),
        "sd": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "median": float(np.median(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "bootstrap_mean_95_ci": [float(low), float(high)],
    }


def _proportion(successes: int, total: int) -> dict[str, object]:
    low, high = wilson_interval(successes, total)
    return {
        "successes": successes,
        "n": total,
        "proportion": successes / total if total else None,
        "wilson_95_ci": [float(low), float(high)],
    }


def _exact_one_sided_sign_p(wins: int, non_ties: int) -> float | None:
    if non_ties <= 0:
        return None
    numerator = sum(math.comb(non_ties, k) for k in range(wins, non_ties + 1))
    return float(numerator / (2**non_ties))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--requested-runs", type=int, default=8)
    parser.add_argument("--min-runs", type=int, default=6)
    args = parser.parse_args()

    paths = sorted(Path(args.root).rglob("frozen-candidate-validation.json"))
    if not paths:
        raise SystemExit("no frozen-candidate-validation.json files found")

    rows: list[dict[str, object]] = []
    hashes: set[str] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        hashes.add(str(payload["candidate_config_sha256"]))
        ref = payload["reference"]
        cand = payload["candidate"]
        ref_cf = ref["counterfactual"]
        cand_cf = cand["counterfactual"]
        rows.append(
            {
                "replicate_id": int(payload["replicate_id"]),
                "config_sha256": payload["candidate_config_sha256"],
                "reference_recall": float(ref_cf["recall"]),
                "candidate_recall": float(cand_cf["recall"]),
                "reference_fpr": float(ref_cf["fpr"]),
                "candidate_fpr": float(cand_cf["fpr"]),
                "reference_delay": (
                    float(ref_cf["median_detection_delay"])
                    if ref_cf["median_detection_delay"] is not None
                    else np.nan
                ),
                "candidate_delay": (
                    float(cand_cf["median_detection_delay"])
                    if cand_cf["median_detection_delay"] is not None
                    else np.nan
                ),
                "reference_detected_run": bool(
                    ref_cf["detected_attack_runs"] == ref_cf["total_attack_runs"]
                    and ref_cf["total_attack_runs"] > 0
                ),
                "candidate_detected_run": bool(
                    cand_cf["detected_attack_runs"] == cand_cf["total_attack_runs"]
                    and cand_cf["total_attack_runs"] > 0
                ),
                "reference_strict_target": bool(ref_cf["meets_external_target"]),
                "candidate_strict_target": bool(cand_cf["meets_external_target"]),
                "reference_benign_alert_free": bool(ref["real_benign_alert_free"]),
                "candidate_benign_alert_free": bool(cand["real_benign_alert_free"]),
                "delta_recall": float(payload["paired_delta"]["sample_recall"]),
                "delta_fpr": float(payload["paired_delta"]["fpr"]),
                "delta_delay": (
                    float(payload["paired_delta"]["median_detection_delay"])
                    if payload["paired_delta"]["median_detection_delay"] is not None
                    else np.nan
                ),
                "delta_benign_alerts": int(
                    payload["paired_delta"]["real_benign_alerts"]
                ),
            }
        )

    data = pd.DataFrame(rows).sort_values("replicate_id").reset_index(drop=True)
    valid_runs = int(data["replicate_id"].nunique())
    if valid_runs < args.min_runs:
        raise SystemExit(
            f"only {valid_runs} valid candidate-validation runs; "
            f"minimum is {args.min_runs}"
        )
    if len(hashes) != 1:
        raise SystemExit(f"multiple candidate config hashes observed: {sorted(hashes)}")

    recall_wins = int((data["delta_recall"] > 0).sum())
    recall_losses = int((data["delta_recall"] < 0).sum())
    recall_non_ties = recall_wins + recall_losses
    delay_wins = int((data["delta_delay"] < 0).sum())
    delay_losses = int((data["delta_delay"] > 0).sum())
    delay_non_ties = delay_wins + delay_losses

    summary = {
        "requested_runs": args.requested_runs,
        "valid_runs": valid_runs,
        "candidate_config_sha256": next(iter(hashes)),
        "reference": {
            "recall": _metric_summary(data["reference_recall"]),
            "fpr": _metric_summary(data["reference_fpr"]),
            "delay": _metric_summary(data["reference_delay"]),
            "attack_run_detection": _proportion(
                int(data["reference_detected_run"].sum()), valid_runs
            ),
            "strict_external_target": _proportion(
                int(data["reference_strict_target"].sum()), valid_runs
            ),
            "benign_alert_free": _proportion(
                int(data["reference_benign_alert_free"].sum()), valid_runs
            ),
        },
        "candidate": {
            "recall": _metric_summary(data["candidate_recall"]),
            "fpr": _metric_summary(data["candidate_fpr"]),
            "delay": _metric_summary(data["candidate_delay"]),
            "attack_run_detection": _proportion(
                int(data["candidate_detected_run"].sum()), valid_runs
            ),
            "strict_external_target": _proportion(
                int(data["candidate_strict_target"].sum()), valid_runs
            ),
            "benign_alert_free": _proportion(
                int(data["candidate_benign_alert_free"].sum()), valid_runs
            ),
        },
        "paired": {
            "delta_recall": _metric_summary(data["delta_recall"]),
            "delta_fpr": _metric_summary(data["delta_fpr"]),
            "delta_delay": _metric_summary(data["delta_delay"]),
            "candidate_recall_wins": recall_wins,
            "candidate_recall_losses": recall_losses,
            "candidate_recall_ties": int(valid_runs - recall_non_ties),
            "recall_win_rate_wilson_95": (
                _proportion(recall_wins, recall_non_ties)
                if recall_non_ties
                else None
            ),
            "recall_exact_one_sided_sign_p": _exact_one_sided_sign_p(
                recall_wins, recall_non_ties
            ),
            "candidate_delay_wins": delay_wins,
            "candidate_delay_losses": delay_losses,
            "candidate_delay_ties": int(valid_runs - delay_non_ties),
            "delay_win_rate_wilson_95": (
                _proportion(delay_wins, delay_non_ties)
                if delay_non_ties
                else None
            ),
            "delay_exact_one_sided_sign_p": _exact_one_sided_sign_p(
                delay_wins, delay_non_ties
            ),
        },
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data.to_csv(out / "frozen-candidate-replicates.csv", index=False)
    (out / "frozen-candidate-summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Frozen consensus candidate validation",
        "",
        f"Valid fresh Open5GS runs: {valid_runs}/{args.requested_runs}",
        f"Candidate config SHA256: {next(iter(hashes))}",
        "",
        "## Reference 2/12 vs candidate 1/8",
        "",
        "| Metric | Reference 2/12 | Candidate 1/8 | Paired delta (candidate-reference) |",
        "| --- | ---: | ---: | ---: |",
        (
            f"| Mean sample recall | "
            f"{summary['reference']['recall']['mean']:.4f} | "
            f"{summary['candidate']['recall']['mean']:.4f} | "
            f"{summary['paired']['delta_recall']['mean']:.4f} |"
        ),
        (
            f"| Mean FPR | "
            f"{summary['reference']['fpr']['mean']:.4f} | "
            f"{summary['candidate']['fpr']['mean']:.4f} | "
            f"{summary['paired']['delta_fpr']['mean']:.4f} |"
        ),
        (
            f"| Median delay | "
            f"{summary['reference']['delay']['median']} | "
            f"{summary['candidate']['delay']['median']} | "
            f"{summary['paired']['delta_delay']['median']} |"
        ),
        (
            f"| Attack-run detection | "
            f"{summary['reference']['attack_run_detection']['successes']}/{valid_runs} | "
            f"{summary['candidate']['attack_run_detection']['successes']}/{valid_runs} | — |"
        ),
        (
            f"| Strict sample-level target | "
            f"{summary['reference']['strict_external_target']['successes']}/{valid_runs} | "
            f"{summary['candidate']['strict_external_target']['successes']}/{valid_runs} | — |"
        ),
        (
            f"| Benign alert-free | "
            f"{summary['reference']['benign_alert_free']['successes']}/{valid_runs} | "
            f"{summary['candidate']['benign_alert_free']['successes']}/{valid_runs} | — |"
        ),
        "",
        (
            "Paired sign tests are reported descriptively because n is small "
            "and the counterfactual construction is deterministic conditional "
            "on each real trace."
        ),
        "",
        (
            f"Recall wins/losses/ties: {recall_wins}/"
            f"{recall_losses}/{valid_runs - recall_non_ties}; "
            f"one-sided exact sign p="
            f"{summary['paired']['recall_exact_one_sided_sign_p']}"
        ),
        (
            f"Delay wins/losses/ties: {delay_wins}/"
            f"{delay_losses}/{valid_runs - delay_non_ties}; "
            f"one-sided exact sign p="
            f"{summary['paired']['delay_exact_one_sided_sign_p']}"
        ),
    ]
    (out / "frozen-candidate-summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print(data.to_string(index=False))


if __name__ == "__main__":
    main()
