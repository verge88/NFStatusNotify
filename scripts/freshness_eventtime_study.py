#!/usr/bin/env python3
"""Locked event-time source provenance study; never transmits network traffic."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nfnotify_lab.detectors import build_detector
from nfnotify_lab.evaluate import _run_delay, _split_scenario_holdout, _threshold_at_fpr
from nfnotify_lab.features import build_features
from nfnotify_lab.freshness import (
    EVENTTIME_VIEWS,
    aligned_features,
    attach_acquisition_times,
    observed_view,
)
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


DETECTORS = ("consensus_guard", "patef_gate_only", "patef_learned_only", "patef")
ALIGNMENTS = ("unaligned", "aligned")
TARGET_FPR = 0.001


def report_rows(details: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (alignment, view, name), g in details.groupby(
        ["alignment", "view", "detector"], sort=False
    ):
        benign = int(g["benign_samples"].sum())
        attacks = int(g["attack_samples"].sum())
        fp = int(g["false_positives"].sum())
        tp = int(g["true_positives"].sum())
        benign_groups = g.loc[g["benign_samples"] > 0]
        attack_groups = g.loc[g["attack_samples"] > 0]
        finite_delays = attack_groups["median_detection_delay"].to_numpy(float)
        finite_delays = finite_delays[np.isfinite(finite_delays)]
        rows.append({
            "alignment": alignment, "view": view, "detector": name,
            "benign_samples": benign, "attack_samples": attacks,
            "false_positives": fp, "true_positives": tp,
            "pooled_fpr": fp / benign if benign else float("nan"),
            "pooled_recall": tp / attacks if attacks else float("nan"),
            "worst_benign_scenario_fpr": float(benign_groups["fpr"].max())
            if len(benign_groups) else float("nan"),
            "minimum_attack_scenario_recall": float(attack_groups["recall"].min())
            if len(attack_groups) else float("nan"),
            "detected_attack_runs": int(g["detected_attack_runs"].sum()),
            "total_attack_runs": int(g["total_attack_runs"].sum()),
            "median_scenario_delay": float(np.median(finite_delays))
            if len(finite_delays) else None,
        })
    return pd.DataFrame(rows)


def _no_delay_worse(a, b) -> bool:
    # a is candidate, b reference; missing/no detections can never be better
    if pd.isna(a):
        return pd.isna(b)
    if pd.isna(b):
        return True
    return bool(a <= b)


def interpret(summary: pd.DataFrame) -> dict:
    indexed = summary.set_index(["alignment", "view", "detector"])
    freshness_checks = []
    ml_checks = []
    freshness_budgets = True
    freshness_noninferiority = True
    freshness_fp_improved = True
    freshness_episode_coverage = True
    ml_budgets = True
    ml_no_recall_loss = True
    ml_no_delay_loss = True
    ml_gain = False

    for view in EVENTTIME_VIEWS:
        raw_gate = indexed.loc[("unaligned", view, "patef_gate_only")]
        aligned_gate = indexed.loc[("aligned", view, "patef_gate_only")]
        full = indexed.loc[("aligned", view, "patef")]
        fpr_ok = bool(
            aligned_gate["pooled_fpr"] <= TARGET_FPR
            and aligned_gate["worst_benign_scenario_fpr"] <= TARGET_FPR
        )
        recall_ok = bool(
            aligned_gate["pooled_recall"] >= raw_gate["pooled_recall"] - 0.03
        )
        episode_ok = bool(
            aligned_gate["detected_attack_runs"] >= raw_gate["detected_attack_runs"]
        )
        improvement_ok = bool(
            view not in ("route_lag4", "both_lag2")
            or aligned_gate["false_positives"] < raw_gate["false_positives"]
        )
        freshness_budgets &= fpr_ok
        freshness_noninferiority &= recall_ok
        freshness_episode_coverage &= episode_ok
        freshness_fp_improved &= improvement_ok
        freshness_checks.append({
            "view": view,
            "raw_gate_fpr": float(raw_gate["pooled_fpr"]),
            "aligned_gate_fpr": float(aligned_gate["pooled_fpr"]),
            "raw_gate_recall": float(raw_gate["pooled_recall"]),
            "aligned_gate_recall": float(aligned_gate["pooled_recall"]),
            "false_positive_delta": int(
                aligned_gate["false_positives"] - raw_gate["false_positives"]
            ),
            "fpr_budget_met": fpr_ok,
            "recall_degradation_at_most_3pp": recall_ok,
            "episode_coverage_not_reduced": episode_ok,
            "prespecified_false_positive_reduction": improvement_ok,
        })

        ml_fpr_ok = bool(
            full["pooled_fpr"] <= TARGET_FPR
            and full["worst_benign_scenario_fpr"] <= TARGET_FPR
        )
        recall_delta = float(full["pooled_recall"] - aligned_gate["pooled_recall"])
        ml_recall_ok = bool(recall_delta >= -1e-12)
        ml_delay_ok = _no_delay_worse(
            full["median_scenario_delay"], aligned_gate["median_scenario_delay"]
        )
        episodes_ok = bool(
            full["detected_attack_runs"] >= aligned_gate["detected_attack_runs"]
        )
        if view != "original" and recall_delta >= 0.01 and episodes_ok:
            ml_gain = True
        ml_budgets &= ml_fpr_ok
        ml_no_recall_loss &= ml_recall_ok
        ml_no_delay_loss &= ml_delay_ok
        ml_checks.append({
            "view": view,
            "full_minus_gate_recall": recall_delta,
            "fpr_budget_met": ml_fpr_ok,
            "no_recall_loss": ml_recall_ok,
            "no_delay_loss": ml_delay_ok,
            "no_episode_loss": episodes_ok,
        })

    freshness_success = bool(
        freshness_budgets and freshness_noninferiority
        and freshness_fp_improved and freshness_episode_coverage
    )
    learned_success = bool(
        ml_budgets and ml_no_recall_loss and ml_no_delay_loss and ml_gain
    )
    return {
        "protocol": "docs/freshness-eventtime-protocol.md",
        "target_fpr": TARGET_FPR,
        "synthetic_oracle_acquisition_timestamps": True,
        "real_trusted_source_timestamps_available": False,
        "views": list(EVENTTIME_VIEWS),
        "freshness_checks": freshness_checks,
        "freshness_all_fpr_budgets_pass": freshness_budgets,
        "freshness_all_recall_noninferiority": freshness_noninferiority,
        "freshness_prespecified_fp_improvement": freshness_fp_improved,
        "freshness_all_episode_coverage": freshness_episode_coverage,
        "freshness_success_on_synthetic_oracle": freshness_success,
        "learned_checks": ml_checks,
        "learned_all_fpr_budgets_pass": ml_budgets,
        "learned_all_no_recall_loss": ml_no_recall_loss,
        "learned_all_no_delay_loss": ml_no_delay_loss,
        "learned_gain_at_least_one_pp": ml_gain,
        "learned_incremental_success_on_synthetic": learned_success,
        "real_event_time_validation_performed": False,
        "production_claim_justified": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--train-seeds", type=int, default=60)
    p.add_argument("--test-first-seed", type=int, default=100)
    p.add_argument("--test-seeds", type=int, default=40)
    p.add_argument("--steps", type=int, default=90)
    p.add_argument("--random-state", type=int, default=42)
    args = p.parse_args()
    if args.train_seeds < 8 or args.test_seeds < 2 or args.steps < 45:
        raise ValueError("insufficient runs or time steps for locked evaluation")
    if args.test_first_seed < args.train_seeds:
        raise ValueError("test seeds must not overlap train/calibration seeds")

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    training_pool = build_features(
        simulate_dataset(
            DEFAULT_SCENARIOS, seeds=range(args.train_seeds), steps=args.steps
        )
    )
    heldout_raw = simulate_dataset(
        DEFAULT_SCENARIOS,
        seeds=range(args.test_first_seed, args.test_first_seed + args.test_seeds),
        steps=args.steps,
    )
    rows = []
    scenarios = sorted(training_pool["scenario"].astype(str).unique())
    for fold, heldout in enumerate(scenarios):
        train, cal, _ = _split_scenario_holdout(
            training_pool, heldout,
            args.random_state + 100 * fold, 0.25,
        )
        raw = heldout_raw.loc[heldout_raw["scenario"] == heldout].copy()
        assert set(raw["run_id"]).isdisjoint(set(train["run_id"]))
        assert set(raw["run_id"]).isdisjoint(set(cal["run_id"]))
        assert heldout not in set(train["scenario"]) | set(cal["scenario"])
        clocked = attach_acquisition_times(raw)
        views = {}
        for view in EVENTTIME_VIEWS:
            observed = observed_view(clocked, view)
            unaligned = build_features(observed)
            aligned = aligned_features(observed)
            assert unaligned[["run_id", "t", "attack_active"]].equals(
                aligned[["run_id", "t", "attack_active"]]
            ), (heldout, view)
            assert raw["attack_active"].sum() == aligned["attack_active"].sum()
            views[(view, "unaligned")] = unaligned
            views[(view, "aligned")] = aligned

        for name in DETECTORS:
            detector = build_detector(
                name, random_state=args.random_state + 1000 * fold
            )
            detector.fit(train, train["attack_active"])
            if hasattr(detector, "calibrate"):
                detector.calibrate(cal, cal["attack_active"])
            threshold = _threshold_at_fpr(
                detector.score_samples(cal),
                cal["attack_active"].to_numpy(),
                TARGET_FPR,
            )
            for (view, alignment), frame in views.items():
                scores = np.asarray(detector.score_samples(frame), dtype=float)
                if not np.isfinite(scores).all():
                    raise ValueError(f"nonfinite {name}/{heldout}/{view}/{alignment}")
                y = frame["attack_active"].to_numpy(dtype=bool)
                pred = scores >= threshold
                benign = ~y
                fp = int(pred[benign].sum())
                tp = int(pred[y].sum())
                delay, detected, total = _run_delay(frame, scores, threshold)
                rows.append({
                    "heldout_scenario": heldout,
                    "view": view,
                    "alignment": alignment,
                    "detector": name,
                    "threshold": float(threshold),
                    "train_runs": int(train["run_id"].nunique()),
                    "calibration_runs": int(cal["run_id"].nunique()),
                    "test_runs": int(frame["run_id"].nunique()),
                    "false_positives": fp,
                    "benign_samples": int(benign.sum()),
                    "true_positives": tp,
                    "attack_samples": int(y.sum()),
                    "fpr": fp / int(benign.sum()) if benign.any() else float("nan"),
                    "recall": tp / int(y.sum()) if y.any() else float("nan"),
                    "median_detection_delay": float(delay),
                    "detected_attack_runs": detected,
                    "total_attack_runs": total,
                })
        print(f"Completed locked event-time holdout: {heldout}", flush=True)

    detail = pd.DataFrame(rows)
    summary = report_rows(detail)
    verdict = interpret(summary)
    detail.to_csv(dest / "freshness-folds.csv", index=False)
    summary.to_csv(dest / "freshness-summary.csv", index=False)
    (dest / "freshness-decision.json").write_text(
        json.dumps(verdict, indent=2), encoding="utf-8"
    )
    (dest / "study-config.json").write_text(json.dumps({
        "train_seeds": [0, args.train_seeds - 1],
        "test_seeds": [args.test_first_seed,
                       args.test_first_seed + args.test_seeds - 1],
        "steps": args.steps,
        "random_state": args.random_state,
        "target_fpr": TARGET_FPR,
        "source_clock": "synthetic oracle logical ticks",
    }, indent=2), encoding="utf-8")
    print(summary.to_string(index=False), flush=True)
    print(json.dumps(verdict, indent=2), flush=True)


if __name__ == "__main__":
    main()
