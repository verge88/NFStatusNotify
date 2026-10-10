#!/usr/bin/env python3
"""Preregistered, causal out-of-domain source-lag experiment (NO exploit traffic)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nfnotify_lab.detectors import build_detector
from nfnotify_lab.evaluate import (
    _run_delay,
    _split_scenario_holdout,
    _threshold_at_fpr,
)
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


DETECTORS = ("consensus_guard", "patef_gate_only", "patef_learned_only", "patef")
VIEWS = ("original", "ausf_lag4", "route_lag4", "both_lag2", "notify_lag2", "nrf_burst3")
STREAMS = {
    "ausf": ("ausf_endpoint", "m_ausf"),
    "route": ("route_endpoint", "m_route"),
    "notify": (
        "notify_seen", "notify_subscription_valid", "notify_sender_trusted", "m_notify"
    ),
}


def stress_observations(raw: pd.DataFrame, view: str) -> pd.DataFrame:
    """Delayed observer streams are strictly causal and isolated by run_id."""
    if view not in VIEWS:
        raise ValueError(f"unknown preregistered view: {view}")
    out = raw.sort_values(["run_id", "t"]).reset_index(drop=True).copy()
    if view == "original":
        return out
    if view == "nrf_burst3":
        affected = out["t"].between(34, 36)
        for column in ("nrf_endpoint", "nrf_update_seen"):
            out.loc[affected, column] = np.nan
        out.loc[affected, "m_nrf"] = 0
        return out

    delay_by_stream = {
        "ausf_lag4": {"ausf": 4},
        "route_lag4": {"route": 4},
        "both_lag2": {"ausf": 2, "route": 2},
        "notify_lag2": {"notify": 2},
    }[view]
    for stream, lag in delay_by_stream.items():
        columns = STREAMS[stream]
        # Each observation comes from an earlier time step, never the future.
        for column in columns:
            out[column] = out.groupby("run_id", sort=False)[column].shift(lag)
        mask = columns[-1]
        out[mask] = out[mask].fillna(0).astype(int)
        for column in columns[:-1]:
            out.loc[out[mask] == 0, column] = np.nan
    return out


def _finite_mean(numbers: list[float]) -> float | None:
    arr = np.asarray(numbers, dtype=float)
    arr = arr[np.isfinite(arr)]
    return float(np.median(arr)) if len(arr) else None


def summarize(details: pd.DataFrame) -> pd.DataFrame:
    summary = []
    for (view, detector), group in details.groupby(["view", "detector"], sort=False):
        benign = int(group["benign_samples"].sum())
        attack = int(group["attack_samples"].sum())
        fp = int(group["false_positives"].sum())
        tp = int(group["true_positives"].sum())
        benign_cases = group.loc[group["benign_samples"] > 0]
        attack_cases = group.loc[group["attack_samples"] > 0]
        summary.append({
            "view": view,
            "detector": detector,
            "false_positives": fp,
            "benign_samples": benign,
            "true_positives": tp,
            "attack_samples": attack,
            "pooled_fpr": fp / benign if benign else float("nan"),
            "pooled_recall": tp / attack if attack else float("nan"),
            "worst_benign_scenario_fpr": float(benign_cases["fpr"].max())
            if len(benign_cases) else float("nan"),
            "min_attack_scenario_recall": float(attack_cases["recall"].min())
            if len(attack_cases) else float("nan"),
            "detected_attack_runs": int(group["detected_attack_runs"].sum()),
            "total_attack_runs": int(group["total_attack_runs"].sum()),
            "median_scenario_detection_delay": _finite_mean(
                attack_cases["median_detection_delay"].tolist()
            ),
        })
    return pd.DataFrame(summary)


def decide(summary: pd.DataFrame, target_fpr: float) -> dict:
    s = summary.set_index(["view", "detector"])
    rows = []
    fp_all_ok = True
    no_recall_loss = True
    no_delay_loss = True
    gain_seen = False
    no_episode_loss = True
    for view in VIEWS:
        gate = s.loc[(view, "patef_gate_only")]
        full = s.loc[(view, "patef")]
        gain = float(full["pooled_recall"] - gate["pooled_recall"])
        fp_ok = bool(
            full["pooled_fpr"] <= target_fpr
            and full["worst_benign_scenario_fpr"] <= target_fpr
        )
        recall_ok = bool(gain >= -1e-12)
        gate_delay, full_delay = gate["median_scenario_detection_delay"], full["median_scenario_detection_delay"]
        delay_ok = bool(
            (gate_delay is None and full_delay is None)
            or (gate_delay is not None and full_delay is not None and full_delay <= gate_delay)
            or (gate_delay is None and full_delay is not None)
        )
        episode_ok = bool(full["detected_attack_runs"] >= gate["detected_attack_runs"])
        if view != "original" and gain >= 0.01 and episode_ok:
            gain_seen = True
        fp_all_ok &= fp_ok
        no_recall_loss &= recall_ok
        no_delay_loss &= delay_ok
        no_episode_loss &= episode_ok
        rows.append({
            "view": view,
            "recall_gain_full_minus_gate": gain,
            "fp_budget_pass": fp_ok,
            "no_recall_loss": recall_ok,
            "no_delay_loss": delay_ok,
            "no_episode_loss": episode_ok,
        })
    synthetic_pass = bool(
        fp_all_ok and no_recall_loss and no_delay_loss
        and no_episode_loss and gain_seen
    )
    return {
        "protocol": "docs/source-shift-preregistered.md",
        "target_fpr": target_fpr,
        "views": list(VIEWS),
        "detectors": list(DETECTORS),
        "view_checks": rows,
        "synthetic_all_views_fpr_pass": fp_all_ok,
        "synthetic_all_views_no_recall_loss": no_recall_loss,
        "synthetic_all_views_no_delay_loss": no_delay_loss,
        "synthetic_all_views_no_episode_loss": no_episode_loss,
        "stressed_view_recall_gain_at_least_1pp": gain_seen,
        "synthetic_success": synthetic_pass,
        "independent_real_control_required": True,
        "external_benign_control_checked_here": False,
        "full_success_not_established": True,
        "interpretation": (
            "Synthetic conditions met, external real benign evidence still required"
            if synthetic_pass else "NEGATIVE: no preregistered incremental ML value"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--seeds", type=int, default=60)
    parser.add_argument("--steps", type=int, default=90)
    parser.add_argument("--target-fpr", type=float, default=0.001)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()
    if args.seeds < 2 or args.steps < 40:
        raise ValueError("need at least two runs/scenario and 40 temporal steps")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    observations = simulate_dataset(
        DEFAULT_SCENARIOS, seeds=range(args.seeds), steps=args.steps
    )
    pristine = build_features(observations)
    scenarios = sorted(pristine["scenario"].unique())
    rows = []

    for scenario_index, heldout in enumerate(scenarios):
        train, cal, test = _split_scenario_holdout(
            pristine, heldout_scenario=heldout,
            random_state=args.random_state + 100 * scenario_index,
            calibration_fraction=0.25,
        )
        train_ids = set(train["run_id"])
        cal_ids = set(cal["run_id"])
        test_ids = set(test["run_id"])
        assert not (train_ids & cal_ids or train_ids & test_ids or cal_ids & test_ids)
        assert heldout not in set(train["scenario"]) | set(cal["scenario"])

        raw_test = observations.loc[observations["scenario"] == heldout]
        stressed = {
            view: build_features(stress_observations(raw_test, view))
            for view in VIEWS
        }
        for view, frame in stressed.items():
            assert frame[["run_id", "t"]].equals(
                test[["run_id", "t"]].reset_index(drop=True)
            ), (view, heldout)
            assert frame["attack_active"].equals(
                test["attack_active"].reset_index(drop=True)
            )

        for detector_name in DETECTORS:
            detector = build_detector(
                detector_name, random_state=args.random_state + 1000 * scenario_index
            )
            detector.fit(train, train["attack_active"])
            if hasattr(detector, "calibrate"):
                detector.calibrate(cal, cal["attack_active"])
            threshold = _threshold_at_fpr(
                detector.score_samples(cal),
                cal["attack_active"].to_numpy(),
                args.target_fpr,
            )

            for view, frame in stressed.items():
                scores = np.asarray(detector.score_samples(frame), dtype=float)
                if not np.isfinite(scores).all():
                    raise ValueError(f"nonfinite risk {detector_name}/{heldout}/{view}")
                actual = frame["attack_active"].to_numpy(dtype=bool)
                pred = scores >= threshold
                benign = ~actual
                tp = int(pred[actual].sum())
                fp = int(pred[benign].sum())
                delay, detected, total = _run_delay(frame, scores, threshold)
                rows.append({
                    "view": view,
                    "heldout_scenario": heldout,
                    "detector": detector_name,
                    "train_runs": len(train_ids),
                    "calibration_runs": len(cal_ids),
                    "test_runs": len(test_ids),
                    "threshold": float(threshold),
                    "false_positives": fp,
                    "benign_samples": int(benign.sum()),
                    "true_positives": tp,
                    "attack_samples": int(actual.sum()),
                    "fpr": fp / int(benign.sum()) if benign.any() else float("nan"),
                    "recall": tp / int(actual.sum()) if actual.any() else float("nan"),
                    "median_detection_delay": float(delay),
                    "detected_attack_runs": detected,
                    "total_attack_runs": total,
                })
        print(f"holdout completed: {heldout}", flush=True)

    details = pd.DataFrame(rows)
    summary = summarize(details)
    decision = decide(summary, args.target_fpr)
    details.to_csv(out_dir / "source-shift-folds.csv", index=False)
    summary.to_csv(out_dir / "source-shift-summary.csv", index=False)
    (out_dir / "source-shift-decision.json").write_text(
        json.dumps(decision, indent=2), encoding="utf-8"
    )
    print(summary.to_string(index=False), flush=True)
    print(json.dumps(decision, indent=2), flush=True)


if __name__ == "__main__":
    main()
