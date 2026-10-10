from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .detectors import build_detector
from .evaluate import _threshold_at_fpr, split_by_run
from .features import build_features
from .simulator import DEFAULT_SCENARIOS, simulate_dataset


def score_benign_control(
    control_features: pd.DataFrame,
    out_dir: Path,
    target_fpr: float = 0.001,
    random_state: int = 42,
    training_seeds: int = 60,
    steps: int = 90,
) -> dict[str, object]:
    """Train PA-TEF on synthetic runs and score an external benign control trace."""
    synthetic = simulate_dataset(
        DEFAULT_SCENARIOS, seeds=range(training_seeds), steps=steps
    )
    training_features = build_features(synthetic)
    train, cal, _ = split_by_run(training_features, random_state=random_state)

    detector = build_detector("patef", random_state=random_state)
    detector.fit(train, train["attack_active"])
    detector.calibrate(cal, cal["attack_active"])
    cal_scores = detector.score_samples(cal)
    threshold = _threshold_at_fpr(
        cal_scores, cal["attack_active"].to_numpy(), target_fpr=target_fpr
    )

    report = detector.risk_report(control_features)
    for column in ("run_id", "scenario", "t", "phase"):
        if column in control_features.columns:
            report.insert(0, column, control_features[column].to_numpy())
    report["alert"] = report["risk_score"] >= threshold

    out_dir.mkdir(parents=True, exist_ok=True)
    report.to_csv(out_dir / "control-scores.csv", index=False)

    summary = {
        "detector": "patef",
        "rows": int(len(report)),
        "target_fpr": target_fpr,
        "threshold": float(threshold),
        "alerts": int(report["alert"].sum()),
        "max_risk": float(report["risk_score"].max()),
        "median_risk": float(report["risk_score"].median()),
        "max_confidence": float(report["confidence"].max()),
    }
    (out_dir / "control-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary
