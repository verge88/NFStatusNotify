#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from nfnotify_lab.consensus import consensus_attack_support
from nfnotify_lab.control import summarize_external_replay
from nfnotify_lab.evaluate import _threshold_at_fpr, split_by_run
from nfnotify_lab.features import build_features
from nfnotify_lab.schema import validate_observations
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


def _load_config(path: Path) -> dict:
    raw = path.read_bytes()
    config = yaml.safe_load(raw)
    config["_sha256"] = hashlib.sha256(raw).hexdigest()
    return config


def _calibration_features(config: dict) -> pd.DataFrame:
    cal_cfg = config["calibration"]
    synthetic = simulate_dataset(
        DEFAULT_SCENARIOS,
        seeds=range(int(cal_cfg["training_seeds"])),
        steps=int(cal_cfg["steps"]),
    )
    features = build_features(synthetic)
    _, cal, _ = split_by_run(
        features,
        random_state=int(cal_cfg["random_state"]),
    )
    return cal


def _score_setting(
    *,
    setting_name: str,
    setting: dict,
    cal: pd.DataFrame,
    real_features: pd.DataFrame,
    counter_features: pd.DataFrame,
    counter_observations: pd.DataFrame,
    target_fpr: float,
    out_dir: Path,
) -> dict[str, object]:
    single_steps = int(setting["single_source_steps"])
    dual_steps = int(setting["dual_source_steps"])

    cal_scores = consensus_attack_support(
        cal,
        single_source_steps=single_steps,
        dual_source_steps=dual_steps,
    ).to_numpy(dtype=float)
    threshold = _threshold_at_fpr(
        cal_scores,
        cal["attack_active"].to_numpy(),
        target_fpr=target_fpr,
    )

    real_scores = consensus_attack_support(
        real_features,
        single_source_steps=single_steps,
        dual_source_steps=dual_steps,
    ).to_numpy(dtype=float)
    real_alerts = real_scores >= threshold

    counter_scores = consensus_attack_support(
        counter_features,
        single_source_steps=single_steps,
        dual_source_steps=dual_steps,
    ).to_numpy(dtype=float)
    counter_alerts = counter_scores >= threshold

    real_report = pd.DataFrame(
        {
            "run_id": real_features["run_id"].astype(str).to_numpy(),
            "scenario": real_features["scenario"].astype(str).to_numpy(),
            "t": real_features["t"].to_numpy(),
            "risk_score": real_scores,
            "alert": real_alerts,
        }
    )
    if "phase" in real_features:
        real_report.insert(3, "phase", real_features["phase"].astype(str).to_numpy())

    counter_report = pd.DataFrame(
        {
            "run_id": counter_features["run_id"].astype(str).to_numpy(),
            "scenario": counter_features["scenario"].astype(str).to_numpy(),
            "t": counter_features["t"].to_numpy(),
            "risk_score": counter_scores,
            "alert": counter_alerts,
        }
    )
    if "phase" in counter_features:
        counter_report.insert(
            3,
            "phase",
            counter_features["phase"].astype(str).to_numpy(),
        )

    real_report.to_csv(out_dir / f"{setting_name}-real-scores.csv", index=False)
    counter_report.to_csv(
        out_dir / f"{setting_name}-counterfactual-scores.csv",
        index=False,
    )

    counter_summary_seed = {
        "target_fpr": target_fpr,
        "threshold": float(threshold),
        "max_risk": float(counter_scores.max()) if len(counter_scores) else 0.0,
    }
    counter_summary = summarize_external_replay(
        setting_name,
        counter_observations,
        counter_report[["alert"]].copy(),
        counter_summary_seed,
    )

    return {
        "name": setting_name,
        "single_source_steps": single_steps,
        "dual_source_steps": dual_steps,
        "target_fpr": target_fpr,
        "threshold": float(threshold),
        "calibration_benign_alert_rate": float(
            (cal_scores[cal["attack_active"].to_numpy() == 0] >= threshold).mean()
        ),
        "real_benign_rows": int(len(real_report)),
        "real_benign_alerts": int(real_alerts.sum()),
        "real_benign_alert_rate": float(real_alerts.mean()),
        "real_benign_alert_free": bool(not real_alerts.any()),
        "real_max_risk": float(real_scores.max()) if len(real_scores) else 0.0,
        "counterfactual": counter_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--real-observations", required=True)
    parser.add_argument("--counterfactual-observations", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--replicate-id", type=int, required=True)
    args = parser.parse_args()

    config_path = Path(args.config)
    config = _load_config(config_path)
    if not bool(config["selection"]["locked"]):
        raise SystemExit("candidate config must be locked before validation")
    if bool(config["selection"]["real_attack_like_validation_used_for_selection"]):
        raise SystemExit("candidate selection must not use real attack-like validation")

    real_raw = validate_observations(pd.read_csv(args.real_observations))
    counter_raw = validate_observations(pd.read_csv(args.counterfactual_observations))
    if real_raw["attack_active"].astype(bool).any():
        raise SystemExit("real control trace must remain benign")
    if not counter_raw["attack_active"].astype(bool).any():
        raise SystemExit("counterfactual trace must contain attack-active rows")

    real_features = build_features(real_raw)
    counter_features = build_features(counter_raw)
    cal = _calibration_features(config)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    target_fpr = float(config["calibration"]["target_fpr"])
    reference = _score_setting(
        setting_name=str(config["reference"]["name"]),
        setting=config["reference"],
        cal=cal,
        real_features=real_features,
        counter_features=counter_features,
        counter_observations=counter_raw,
        target_fpr=target_fpr,
        out_dir=out_dir,
    )
    candidate = _score_setting(
        setting_name=str(config["candidate"]["name"]),
        setting=config["candidate"],
        cal=cal,
        real_features=real_features,
        counter_features=counter_features,
        counter_observations=counter_raw,
        target_fpr=target_fpr,
        out_dir=out_dir,
    )

    ref_counter = reference["counterfactual"]
    cand_counter = candidate["counterfactual"]
    result = {
        "replicate_id": args.replicate_id,
        "candidate_config_sha256": config["_sha256"],
        "selection": config["selection"],
        "reference": reference,
        "candidate": candidate,
        "paired_delta": {
            "sample_recall": float(cand_counter["recall"] - ref_counter["recall"]),
            "fpr": float(cand_counter["fpr"] - ref_counter["fpr"]),
            "median_detection_delay": (
                float(
                    cand_counter["median_detection_delay"]
                    - ref_counter["median_detection_delay"]
                )
                if (
                    cand_counter["median_detection_delay"] is not None
                    and ref_counter["median_detection_delay"] is not None
                )
                else None
            ),
            "real_benign_alerts": int(
                candidate["real_benign_alerts"] - reference["real_benign_alerts"]
            ),
        },
    }
    (out_dir / "frozen-candidate-validation.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
