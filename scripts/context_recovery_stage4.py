#!/usr/bin/env python3
"""Stage 4 locked causal recovery/transition provenance challenge (synthetic only)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nfnotify_lab.detectors import build_detector
from nfnotify_lab.evaluate import _run_delay, _threshold_at_fpr, split_by_run
from nfnotify_lab.features import build_features
from nfnotify_lab.freshness import (
    attach_acquisition_times,
    aligned_features,
    context_aligned_features,
    observed_view,
)
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, ROGUE_UDM, Scenario, simulate_dataset


TRAIN_SEEDS = range(60)
TEST_SEEDS = range(200, 224)
STEPS = 90
TARGET_FPR = 0.001
VIEWS = (
    "original",
    "route_lag4",
    "both_lag2",
    "route_lag8",
    "route_jitter2_6",
    "nrf_burst3",
)
METHODS = ("raw", "state_only", "state_and_context")
DETECTORS = ("consensus_guard", "patef_gate_only", "patef_learned_only", "patef")
MID_RECOVERY_ATTACKS = ("during_recovery_route_42", "during_recovery_dual_42")
SCENARIOS = (
    Scenario("recovery_end38", recovery_start=30, recovery_end=38),
    Scenario("recovery_end55", recovery_start=30, recovery_end=55),
    Scenario(
        "recovery_update_35", legit_update_at=35, notify_delay=4,
        recovery_start=30, recovery_end=45,
    ),
    Scenario("delayed_notify_14", legit_update_at=35, notify_delay=14),
    Scenario(
        "update_then_recovery_40", legit_update_at=30, notify_delay=8,
        recovery_start=40, recovery_end=55,
    ),
    Scenario(
        "post_recovery_route_47", attack=True,
        recovery_start=30, recovery_end=45, silent_divergence_at=47,
        silent_divergence_sources=("route",),
    ),
    Scenario(
        "post_recovery_cache_47", attack=True,
        recovery_start=30, recovery_end=45, silent_divergence_at=47,
        silent_divergence_sources=("ausf",),
    ),
    Scenario(
        "post_recovery_dual_47", attack=True,
        recovery_start=30, recovery_end=45, silent_divergence_at=47,
        silent_divergence_sources=("ausf", "route"),
    ),
    Scenario(
        "during_recovery_route_42", attack=True,
        recovery_start=30, recovery_end=45, silent_divergence_at=42,
        silent_divergence_sources=("route",),
    ),
    Scenario(
        "during_recovery_dual_42", attack=True,
        recovery_start=30, recovery_end=45, silent_divergence_at=42,
        silent_divergence_sources=("ausf", "route"),
    ),
)


def challenge_observations() -> pd.DataFrame:
    """Only the two canary effects persist beyond recovery; labels are honest."""
    out = simulate_dataset(SCENARIOS, seeds=TEST_SEEDS, steps=STEPS)
    for scenario, sources in (
        ("during_recovery_route_42", ("route",)),
        ("during_recovery_dual_42", ("ausf", "route")),
    ):
        active = out["scenario"].eq(scenario) & out["t"].ge(42)
        for src in sources:
            mask = out[f"m_{src}"].eq(1)
            out.loc[active & mask, f"{src}_endpoint"] = ROGUE_UDM
    return out


def reduce_metrics(rows: pd.DataFrame) -> pd.DataFrame:
    data = []
    for (method, view, detector), frame in rows.groupby(
        ["method", "view", "detector"], sort=False
    ):
        benign = int(frame["benign_samples"].sum())
        attack = int(frame["attack_samples"].sum())
        fp = int(frame["false_positives"].sum())
        tp = int(frame["true_positives"].sum())
        benign_cases = frame.loc[frame["benign_samples"] > 0]
        attack_cases = frame.loc[frame["attack_samples"] > 0]
        delays = attack_cases["median_detection_delay"].to_numpy(float)
        delays = delays[np.isfinite(delays)]
        data.append({
            "method": method,
            "view": view,
            "detector": detector,
            "benign_samples": benign,
            "attack_samples": attack,
            "false_positives": fp,
            "true_positives": tp,
            "pooled_fpr": fp / benign if benign else float("nan"),
            "pooled_recall": tp / attack if attack else float("nan"),
            "worst_benign_scenario_fpr": float(benign_cases["fpr"].max()),
            "minimum_attack_scenario_recall": float(attack_cases["recall"].min()),
            "detected_attack_runs": int(frame["detected_attack_runs"].sum()),
            "total_attack_runs": int(frame["total_attack_runs"].sum()),
            "median_scenario_delay": float(np.median(delays)) if len(delays) else None,
            "route_explanations": int(frame["route_explanations"].sum()),
            "ausf_explanations": int(frame["ausf_explanations"].sum()),
            "missing_route_provenance": int(frame["missing_route_provenance"].sum()),
            "missing_ausf_provenance": int(frame["missing_ausf_provenance"].sum()),
        })
    return pd.DataFrame(data)


def decision(summary: pd.DataFrame, per_scenario: pd.DataFrame) -> dict:
    lookup = summary.set_index(["method", "view", "detector"])
    folds = per_scenario.set_index(["method", "view", "detector", "scenario"])
    h1 = []
    h2 = []
    h1_budget = h1_recall = h1_scenario = h1_coverage = True
    h1_fp = h1_canary = True
    h2_budget = h2_recall = h2_delay = True
    h2_gain = False
    for view in VIEWS:
        state = lookup.loc[("state_only", view, "patef_gate_only")]
        ctx = lookup.loc[("state_and_context", view, "patef_gate_only")]
        full = lookup.loc[("state_and_context", view, "patef")]
        fpr_ok = bool(
            ctx["pooled_fpr"] <= TARGET_FPR
            and ctx["worst_benign_scenario_fpr"] <= TARGET_FPR
        )
        sample_ok = bool(ctx["pooled_recall"] >= state["pooled_recall"] - 0.03)
        scenario_ok = True
        for scenario in SCENARIOS:
            if not scenario.attack:
                continue
            raw = folds.loc[("state_only", view, "patef_gate_only", scenario.name)]
            candidate = folds.loc[
                ("state_and_context", view, "patef_gate_only", scenario.name)
            ]
            if raw["recall"] > 0 and candidate["recall"] < 0.8 * raw["recall"]:
                scenario_ok = False

        coverage_ok = bool(
            ctx["detected_attack_runs"] >= 114
            and ctx["total_attack_runs"] == 120
        )
        canary_ok = True
        for name in MID_RECOVERY_ATTACKS:
            fold = folds.loc[("state_and_context", view, "patef_gate_only", name)]
            if fold["total_attack_runs"] != 24 or fold["detected_attack_runs"] < 22:
                canary_ok = False

        fp_strict = bool(
            view not in ("route_lag4", "both_lag2")
            or ctx["false_positives"] < state["false_positives"]
        )
        fp_nonincrease = bool(
            ctx["false_positives"] <= state["false_positives"]
        )
        h1_budget &= fpr_ok
        h1_recall &= sample_ok
        h1_scenario &= scenario_ok
        h1_coverage &= coverage_ok
        h1_canary &= canary_ok
        h1_fp &= fp_strict and fp_nonincrease
        h1.append({
            "view": view,
            "fpr_budget": fpr_ok,
            "state_only_fpr": float(state["pooled_fpr"]),
            "context_fpr": float(ctx["pooled_fpr"]),
            "worst_context_fpr": float(ctx["worst_benign_scenario_fpr"]),
            "false_positive_delta": int(
                ctx["false_positives"] - state["false_positives"]
            ),
            "state_only_recall": float(state["pooled_recall"]),
            "context_recall": float(ctx["pooled_recall"]),
            "recall_loss_at_most_3pp": sample_ok,
            "per_attack_scenario_recall_ratio_at_least_0_8": scenario_ok,
            "detected_at_least_114_of_120": coverage_ok,
            "mid_recovery_canary_detection_22_of_24_each": canary_ok,
            "prespecified_fp_strict_and_nonincrease": fp_strict and fp_nonincrease,
        })

        ml_fpr_ok = bool(
            full["pooled_fpr"] <= TARGET_FPR
            and full["worst_benign_scenario_fpr"] <= TARGET_FPR
        )
        recall_delta = float(full["pooled_recall"] - ctx["pooled_recall"])
        learned_no_loss = bool(recall_delta >= -1e-12)
        x = full["median_scenario_delay"]
        y = ctx["median_scenario_delay"]
        learned_no_delay = bool(
            (pd.isna(x) and pd.isna(y))
            or (pd.notna(x) and pd.notna(y) and x <= y)
            or (pd.notna(x) and pd.isna(y))
        )
        h2_gain |= bool(view != "original" and recall_delta >= 0.01)
        h2_budget &= ml_fpr_ok
        h2_recall &= learned_no_loss
        h2_delay &= learned_no_delay
        h2.append({
            "view": view,
            "fpr_budget": ml_fpr_ok,
            "full_minus_context_gate_recall": recall_delta,
            "no_recall_loss": learned_no_loss,
            "no_delay_loss": learned_no_delay,
        })
    return {
        "protocol": "docs/context-recovery-stage4-protocol.md",
        "synthetic_oracle_source_timestamps_and_recovery_context": True,
        "challenge_new_scenario_names": [s.name for s in SCENARIOS],
        "train_seeds": [0, 59],
        "test_seeds": [200, 223],
        "target_fpr": TARGET_FPR,
        "views": list(VIEWS),
        "h1_context_checks": h1,
        "h1_all_fpr_budgets_met": h1_budget,
        "h1_all_sample_recall_noninferiority": h1_recall,
        "h1_all_attack_scenario_ratio": h1_scenario,
        "h1_all_episode_coverage": h1_coverage,
        "h1_all_recovery_canaries": h1_canary,
        "h1_prespecified_fp_reduction": h1_fp,
        "h1_success": bool(
            h1_budget and h1_recall and h1_scenario and
            h1_coverage and h1_canary and h1_fp
        ),
        "h2_learned_checks": h2,
        "h2_all_fpr_budgets_met": h2_budget,
        "h2_all_no_recall_loss": h2_recall,
        "h2_all_no_delay_loss": h2_delay,
        "h2_recall_gain_at_least_1pp": h2_gain,
        "h2_success": bool(h2_budget and h2_recall and h2_delay and h2_gain),
        "real_context_alignment_validated": False,
        "production_provenance_available": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    pool = build_features(simulate_dataset(DEFAULT_SCENARIOS, TRAIN_SEEDS, STEPS))
    train, cal, _ = split_by_run(pool, random_state=42)
    challenge = challenge_observations()
    train_ids, cal_ids, challenge_ids = (
        set(train["run_id"]), set(cal["run_id"]), set(challenge["run_id"])
    )
    assert not train_ids.intersection(cal_ids)
    assert not train_ids.intersection(challenge_ids)
    assert not cal_ids.intersection(challenge_ids)
    assert set(challenge["scenario"]).isdisjoint(set(pool["scenario"]))
    assert len(challenge_ids) == 240
    assert challenge["attack_active"].sum() == sum(
        (STEPS - (42 if s.name in MID_RECOVERY_ATTACKS else 47))
        * len(TEST_SEEDS) for s in SCENARIOS if s.attack
    )

    features = {}
    for view in VIEWS:
        clocked = attach_acquisition_times(challenge)
        observed = observed_view(clocked, view)
        features[(view, "raw")] = build_features(observed)
        features[(view, "state_only")] = aligned_features(observed)
        features[(view, "state_and_context")] = context_aligned_features(observed)
        truth = features[(view, "raw")][["run_id", "t", "attack_active"]]
        for method in METHODS:
            f = features[(view, method)]
            assert f[["run_id", "t", "attack_active"]].equals(truth)
        print(f"constructed fixed observer view: {view}", flush=True)

    rows = []
    for name in DETECTORS:
        detector = build_detector(name, random_state=42)
        detector.fit(train, train["attack_active"])
        if hasattr(detector, "calibrate"):
            detector.calibrate(cal, cal["attack_active"])
        threshold = _threshold_at_fpr(
            detector.score_samples(cal), cal["attack_active"].to_numpy(),
            TARGET_FPR,
        )
        print(f"calibrated pristine held-in detector: {name}", flush=True)
        for (view, method), frame in features.items():
            scores = np.asarray(detector.score_samples(frame), dtype=float)
            if not np.isfinite(scores).all():
                raise ValueError(f"non-finite output: {name}/{view}/{method}")
            scored = frame[[
                "run_id", "t", "scenario", "attack_start", "attack_active"
            ]].copy()
            scored["score"] = scores
            scored["pred"] = scores >= threshold
            for scenario, group in scored.groupby("scenario", sort=True):
                y = group["attack_active"].to_numpy(bool)
                pred = group["pred"].to_numpy(bool)
                benign = ~y
                delay, detected, total = _run_delay(
                    group, group["score"].to_numpy(float), threshold
                )
                selected = frame.loc[group.index]
                rows.append({
                    "detector": name,
                    "method": method,
                    "view": view,
                    "scenario": scenario,
                    "threshold": float(threshold),
                    "benign_samples": int(benign.sum()),
                    "attack_samples": int(y.sum()),
                    "false_positives": int(pred[benign].sum()),
                    "true_positives": int(pred[y].sum()),
                    "fpr": float(pred[benign].mean()) if benign.any() else np.nan,
                    "recall": float(pred[y].mean()) if y.any() else np.nan,
                    "median_detection_delay": float(delay),
                    "detected_attack_runs": detected,
                    "total_attack_runs": total,
                    "route_explanations": int(
                        selected.get(
                            "eventtime_route_explained",
                            pd.Series(0, index=group.index),
                        ).sum()
                    ),
                    "ausf_explanations": int(
                        selected.get(
                            "eventtime_ausf_explained",
                            pd.Series(0, index=group.index),
                        ).sum()
                    ),
                    "missing_route_provenance": int(
                        selected["prov_route"].fillna(0).eq(0).sum()
                    ),
                    "missing_ausf_provenance": int(
                        selected["prov_nrf_ausf"].fillna(0).eq(0).sum()
                    ),
                })
        print(f"completed detector: {name}", flush=True)

    detail = pd.DataFrame(rows)
    summary = reduce_metrics(detail)
    verdict = decision(summary, detail)
    detail.to_csv(out_dir / "stage4-scenario.csv", index=False)
    summary.to_csv(out_dir / "stage4-summary.csv", index=False)
    (out_dir / "stage4-decision.json").write_text(
        json.dumps(verdict, indent=2), encoding="utf-8"
    )
    (out_dir / "stage4-manifest.json").write_text(
        json.dumps({
            "protocol": verdict["protocol"],
            "scenario_names": verdict["challenge_new_scenario_names"],
            "training_seeds": [0, 59],
            "test_seeds": [200, 223],
            "views": list(VIEWS),
            "methods": list(METHODS),
            "detectors": list(DETECTORS),
            "source_provenance": "unverified simulator oracle",
        }, indent=2), encoding="utf-8"
    )
    print(summary.to_string(index=False), flush=True)
    print(json.dumps(verdict, indent=2), flush=True)


if __name__ == "__main__":
    main()
