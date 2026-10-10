from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .detectors import build_detector
from .evaluate import _threshold_at_fpr, split_by_run
from .features import build_features
from .simulator import DEFAULT_SCENARIOS, simulate_dataset


CONTROL_DETECTORS = ("semantic_guard", "patef")


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
