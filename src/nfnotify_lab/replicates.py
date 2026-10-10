from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


DETECTORS = ("semantic_guard", "consensus_guard", "patef")
DEFAULT_METRICS = (
    "recall",
    "fpr",
    "attack_run_detection_rate",
    "median_detection_delay",
    "real_benign_alerts",
    "max_risk",
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _tsv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return max(0, len(lines) - 1)


def collect_replicates(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collect detector and infrastructure rows from replicated lab artifacts."""
    detector_rows: list[dict[str, object]] = []
    infra_rows: list[dict[str, object]] = []

    for result_path in sorted(root.rglob("counterfactual-result.json")):
        run_root = result_path.parent
        result = _read_json(result_path)
        meta_path = run_root / "failover-meta.json"
        evidence_path = run_root / "evidence-summary.json"
        if not meta_path.exists() or not evidence_path.exists():
            continue

        meta = _read_json(meta_path)
        evidence = _read_json(evidence_path)
        replicate_id = int(meta.get("replicate_id", len(infra_rows)))
        phase = meta.get("phase_epochs", {})
        baseline_start = float(phase.get("baseline_start", float("nan")))
        failover_start = float(phase.get("failover_start", float("nan")))
        recovery_start = float(phase.get("recovery_start", float("nan")))
        experiment_end = float(phase.get("experiment_end", float("nan")))

        infra_rows.append(
            {
                "replicate_id": replicate_id,
                "udm_a_instance_id": meta.get("udm_a_instance_id"),
                "udm_b_instance_id": meta.get("udm_b_instance_id"),
                "cache_events": len(evidence.get("cache_events", [])),
                "notification_frames": _tsv_rows(run_root / "notifications.tsv"),
                "route_frames": _tsv_rows(run_root / "routes.tsv"),
                "failover_duration_s": recovery_start - failover_start,
                "recovery_duration_s": experiment_end - recovery_start,
                "total_experiment_duration_s": experiment_end - baseline_start,
            }
        )

        for detector in DETECTORS:
            if detector not in result:
                continue
            metrics = result[detector]
            real_path = run_root / "real" / f"control-summary-{detector}.json"
            real_summary = _read_json(real_path) if real_path.exists() else {}
            detector_rows.append(
                {
                    "replicate_id": replicate_id,
                    "detector": detector,
                    "attack_samples": int(metrics["attack_samples"]),
                    "attack_alerts": int(metrics["attack_alerts"]),
                    "benign_samples": int(metrics["benign_samples"]),
                    "benign_alerts": int(metrics["benign_alerts"]),
                    "recall": float(metrics["recall"]),
                    "fpr": float(metrics["fpr"]),
                    "threshold": float(metrics["threshold"]),
                    "max_risk": float(metrics["max_risk"]),
                    "detected_attack_runs": int(metrics["detected_attack_runs"]),
                    "total_attack_runs": int(metrics["total_attack_runs"]),
                    "attack_run_detection_rate": float(
                        metrics["attack_run_detection_rate"]
                    ),
                    "median_detection_delay": (
                        float(metrics["median_detection_delay"])
                        if metrics.get("median_detection_delay") is not None
                        else float("nan")
                    ),
                    "meets_external_target": bool(
                        metrics["meets_external_target"]
                    ),
                    "meets_run_detection_target": bool(
                        metrics["meets_run_detection_target"]
                    ),
                    "real_benign_alerts": int(real_summary.get("alerts", 0)),
                    "real_max_risk": float(real_summary.get("max_risk", 0.0)),
                }
            )

    detector_df = pd.DataFrame(detector_rows)
    infra_df = pd.DataFrame(infra_rows)
    if len(detector_df):
        detector_df = detector_df.sort_values(
            ["replicate_id", "detector"]
        ).reset_index(drop=True)
    if len(infra_df):
        infra_df = infra_df.sort_values("replicate_id").reset_index(drop=True)
    return detector_df, infra_df


def bootstrap_interval(
    values: np.ndarray,
    *,
    statistic: str = "mean",
    confidence: float = 0.95,
    resamples: int = 10000,
    random_state: int = 20261010,
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan"), float("nan")
    if values.size == 1:
        value = float(values[0])
        return value, value

    rng = np.random.default_rng(random_state)
    draws = rng.choice(values, size=(resamples, values.size), replace=True)
    if statistic == "mean":
        stats = draws.mean(axis=1)
    elif statistic == "median":
        stats = np.median(draws, axis=1)
    else:
        raise ValueError(f"unsupported statistic: {statistic}")

    alpha = 1.0 - confidence
    low, high = np.quantile(stats, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(low), float(high)


def wilson_interval(
    successes: int,
    total: int,
    *,
    z: float = 1.959963984540054,
) -> tuple[float, float]:
    if total <= 0:
        return float("nan"), float("nan")
    p = successes / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = (p + z2 / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt((p * (1.0 - p) / total) + z2 / (4.0 * total * total))
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def numeric_summary(
    detector_df: pd.DataFrame,
    metrics: tuple[str, ...] = DEFAULT_METRICS,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for detector, group in detector_df.groupby("detector", sort=False):
        for metric in metrics:
            values = pd.to_numeric(group[metric], errors="coerce").dropna().to_numpy()
            if not len(values):
                continue
            mean_ci = bootstrap_interval(values, statistic="mean")
            median_ci = bootstrap_interval(values, statistic="median")
            q1, q3 = np.quantile(values, [0.25, 0.75])
            rows.append(
                {
                    "detector": detector,
                    "metric": metric,
                    "n": int(len(values)),
                    "mean": float(np.mean(values)),
                    "sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                    "median": float(np.median(values)),
                    "q1": float(q1),
                    "q3": float(q3),
                    "iqr": float(q3 - q1),
                    "min": float(np.min(values)),
                    "max": float(np.max(values)),
                    "bootstrap_mean_ci_low": mean_ci[0],
                    "bootstrap_mean_ci_high": mean_ci[1],
                    "bootstrap_median_ci_low": median_ci[0],
                    "bootstrap_median_ci_high": median_ci[1],
                }
            )
    return pd.DataFrame(rows)


def infrastructure_summary(infra_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    metrics = (
        "cache_events",
        "notification_frames",
        "route_frames",
        "failover_duration_s",
        "recovery_duration_s",
        "total_experiment_duration_s",
    )
    for metric in metrics:
        values = pd.to_numeric(infra_df[metric], errors="coerce").dropna().to_numpy()
        if not len(values):
            continue
        mean_ci = bootstrap_interval(values, statistic="mean")
        q1, q3 = np.quantile(values, [0.25, 0.75])
        rows.append(
            {
                "metric": metric,
                "n": int(len(values)),
                "mean": float(np.mean(values)),
                "sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "median": float(np.median(values)),
                "q1": float(q1),
                "q3": float(q3),
                "iqr": float(q3 - q1),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "bootstrap_mean_ci_low": mean_ci[0],
                "bootstrap_mean_ci_high": mean_ci[1],
            }
        )
    return pd.DataFrame(rows)


def proportion_summary(detector_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for detector, group in detector_df.groupby("detector", sort=False):
        checks = {
            "attack_run_detected": group["detected_attack_runs"].astype(int)
            == group["total_attack_runs"].astype(int),
            "real_benign_alert_free": group["real_benign_alerts"].astype(int) == 0,
            "strict_external_target_met": group["meets_external_target"].astype(bool),
            "run_detection_target_met": group["meets_run_detection_target"].astype(bool),
        }
        for metric, success_mask in checks.items():
            total = int(len(success_mask))
            successes = int(success_mask.sum())
            low, high = wilson_interval(successes, total)
            rows.append(
                {
                    "detector": detector,
                    "metric": metric,
                    "successes": successes,
                    "n": total,
                    "proportion": successes / total if total else float("nan"),
                    "wilson_95_ci_low": low,
                    "wilson_95_ci_high": high,
                }
            )
    return pd.DataFrame(rows)


def study_summary(
    detector_df: pd.DataFrame,
    infra_df: pd.DataFrame,
    *,
    requested_replicates: int,
) -> dict[str, object]:
    valid_ids = sorted(set(infra_df["replicate_id"].astype(int))) if len(infra_df) else []
    payload: dict[str, object] = {
        "requested_replicates": requested_replicates,
        "valid_replicates": len(valid_ids),
        "replicate_ids": valid_ids,
        "detectors": {},
    }
    for detector, group in detector_df.groupby("detector", sort=False):
        payload["detectors"][detector] = {
            "mean_sample_recall": float(group["recall"].mean()),
            "sd_sample_recall": float(group["recall"].std(ddof=1))
            if len(group) > 1
            else 0.0,
            "median_sample_recall": float(group["recall"].median()),
            "mean_fpr": float(group["fpr"].mean()),
            "mean_attack_run_detection_rate": float(
                group["attack_run_detection_rate"].mean()
            ),
            "median_detection_delay": float(
                group["median_detection_delay"].dropna().median()
            )
            if group["median_detection_delay"].notna().any()
            else None,
            "benign_alert_free_runs": int((group["real_benign_alerts"] == 0).sum()),
            "strict_external_target_runs": int(group["meets_external_target"].sum()),
            "run_detection_target_runs": int(
                group["meets_run_detection_target"].sum()
            ),
        }
    return payload
