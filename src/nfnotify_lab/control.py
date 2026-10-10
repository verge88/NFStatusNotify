from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .detectors import build_detector
from .evaluate import _threshold_at_fpr, split_by_run
from .features import build_features
from .simulator import DEFAULT_SCENARIOS, simulate_dataset


CONTROL_DETECTORS = (
    "semantic_guard",
    "consensus_guard",
    "patef_gate_only",
    "patef_learned_only",
    "patef",
)


def _external_report(detector, control_features: pd.DataFrame) -> pd.DataFrame:
    if hasattr(detector, "risk_report"):
        return detector.risk_report(control_features)

    report = pd.DataFrame(index=control_features.index)
    report["risk_score"] = detector.score_samples(control_features)
    if "evidence_coverage" in control_features.columns:
        report["confidence"] = control_features["evidence_coverage"].fillna(0.0)
    else:
        report["confidence"] = control_features["obs_fraction"].fillna(0.0)
    report["dominant_evidence"] = "deterministic_semantic_support"
    return report


def summarize_external_replay(
    detector_name: str,
    observations: pd.DataFrame,
    scores: pd.DataFrame,
    summary: dict[str, object],
) -> dict[str, object]:
    """Summarize per-sample and per-run detection on an external replay.

    The strict sample-level target is preserved for comparability. Run-level
    detection and delay are reported separately so persistence-based detectors
    are not misinterpreted as missing an entire episode when they intentionally
    wait for repeated evidence.
    """
    if len(observations) != len(scores):
        raise ValueError("observations and scores must have identical row counts")
    if "attack_active" not in observations or "alert" not in scores:
        raise ValueError("external replay requires attack_active and alert columns")

    attack = observations["attack_active"].astype(bool).to_numpy()
    alerts = scores["alert"].astype(bool).to_numpy()
    benign = ~attack
    attack_alerts = int(alerts[attack].sum())
    benign_alerts = int(alerts[benign].sum())
    recall = float(alerts[attack].mean()) if attack.any() else float("nan")
    fpr = float(alerts[benign].mean()) if benign.any() else float("nan")

    tmp = pd.DataFrame(
        {
            "run_id": (
                observations["run_id"].astype(str).to_numpy()
                if "run_id" in observations
                else ["external-run"] * len(observations)
            ),
            "t": observations["t"].to_numpy(),
            "attack_active": attack,
            "alert": alerts,
        }
    )
    if "attack_start" in observations:
        tmp["attack_start"] = observations["attack_start"].to_numpy()
    else:
        tmp["attack_start"] = -1

    delays: list[float] = []
    total_attack_runs = 0
    detected_attack_runs = 0
    for _, group in tmp.groupby("run_id", sort=False):
        active = group.loc[group["attack_active"]]
        if active.empty:
            continue
        total_attack_runs += 1

        declared = pd.to_numeric(group["attack_start"], errors="coerce")
        declared = declared.loc[declared >= 0]
        attack_start = (
            float(declared.iloc[0])
            if len(declared)
            else float(active["t"].min())
        )
        after = group.loc[(group["t"] >= attack_start) & group["alert"]]
        if len(after):
            detected_attack_runs += 1
            delays.append(float(after.iloc[0]["t"] - attack_start))

    detection_rate = (
        detected_attack_runs / total_attack_runs
        if total_attack_runs
        else float("nan")
    )
    median_delay = float(pd.Series(delays).median()) if delays else None
    target_fpr = float(summary["target_fpr"])

    return {
        "detector": detector_name,
        "attack_samples": int(attack.sum()),
        "attack_alerts": attack_alerts,
        "benign_samples": int(benign.sum()),
        "benign_alerts": benign_alerts,
        "recall": recall,
        "fpr": fpr,
        "threshold": float(summary["threshold"]),
        "max_risk": float(summary["max_risk"]),
        "meets_external_target": bool(recall == 1.0 and fpr <= target_fpr),
        "detected_attack_runs": detected_attack_runs,
        "total_attack_runs": total_attack_runs,
        "attack_run_detection_rate": detection_rate,
        "median_detection_delay": median_delay,
        "meets_run_detection_target": bool(
            total_attack_runs > 0
            and detected_attack_runs == total_attack_runs
            and fpr <= target_fpr
        ),
    }


def score_benign_control(
    control_features: pd.DataFrame,
    out_dir: Path,
    target_fpr: float = 0.001,
    random_state: int = 42,
    training_seeds: int = 60,
    steps: int = 90,
    detector_name: str = "patef",
) -> dict[str, object]:
    """Calibrate one detector on synthetic runs and score an external trace.

    Detector-specific files are always written. PA-TEF additionally keeps the
    legacy unsuffixed files for compatibility with previously published
    laboratory artifacts.
    """
    if detector_name not in CONTROL_DETECTORS:
        raise ValueError(
            f"external control detector must be one of {CONTROL_DETECTORS}; "
            f"got {detector_name!r}"
        )

    synthetic = simulate_dataset(
        DEFAULT_SCENARIOS, seeds=range(training_seeds), steps=steps
    )
    training_features = build_features(synthetic)
    train, cal, _ = split_by_run(training_features, random_state=random_state)

    detector = build_detector(detector_name, random_state=random_state)
    detector.fit(train, train["attack_active"])
    if hasattr(detector, "calibrate"):
        detector.calibrate(cal, cal["attack_active"])

    cal_scores = detector.score_samples(cal)
    threshold = _threshold_at_fpr(
        cal_scores, cal["attack_active"].to_numpy(), target_fpr=target_fpr
    )

    report = _external_report(detector, control_features)
    for column in ("run_id", "scenario", "t", "phase"):
        if column in control_features.columns:
            report.insert(0, column, control_features[column].to_numpy())
    report["alert"] = report["risk_score"] >= threshold

    out_dir.mkdir(parents=True, exist_ok=True)
    scores_path = out_dir / f"control-scores-{detector_name}.csv"
    summary_path = out_dir / f"control-summary-{detector_name}.json"
    report.to_csv(scores_path, index=False)

    summary = {
        "detector": detector_name,
        "rows": int(len(report)),
        "target_fpr": target_fpr,
        "threshold": float(threshold),
        "alerts": int(report["alert"].sum()),
        "max_risk": float(report["risk_score"].max()),
        "median_risk": float(report["risk_score"].median()),
        "max_confidence": float(report["confidence"].max()),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if detector_name == "patef":
        report.to_csv(out_dir / "control-scores.csv", index=False)
        (out_dir / "control-summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )

    return summary
