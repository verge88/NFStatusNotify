#!/usr/bin/env python3
"""Locked Stage 6 scenario-disjoint PA-TEF OR-consensus benchmark.

Synthetic source origin ticks are oracle metadata, NOT real source timestamps.
No forged network notification traffic is generated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nfnotify_lab.evaluate import _run_delay, _threshold_at_fpr
from nfnotify_lab.features import build_features
from nfnotify_lab.freshness import attach_acquisition_times
from nfnotify_lab.patef_residual import (
    PatefResidualGuard, TARGET_FPR, ABSTAIN_THRESHOLD,
)
from nfnotify_lab.residual_freshness import (
    SOURCE_COLUMNS, availability_mask, make_view, with_causal_source_ages,
)
from nfnotify_lab.simulator import (
    DEFAULT_SCENARIOS, Scenario, simulate_dataset,
)


VIEWS = (
    "original", "route_lag4", "both_lag2", "route_lag8",
    "no_ausf", "no_route", "no_nrf",
)
CAL_VIEWS = (
    "original", "route_lag4", "both_lag2", "ausf_lag4",
    "route_lag8", "no_ausf", "no_route", "no_nrf",
)
TRAIN_VIEWS = ("original", "route_lag4", "both_lag2", "ausf_lag4")
CHALLENGE_SCENARIOS = (
    Scenario(
        "skew_route_duration4_24", observer_skew_at=24,
        observer_skew_duration=4, observer_skew_sources=("route",),
    ),
    Scenario(
        "skew_ausf_duration10_28", observer_skew_at=28,
        observer_skew_duration=10, observer_skew_sources=("ausf",),
    ),
    Scenario("recovery_28_48_new", recovery_start=28, recovery_end=48),
    Scenario(
        "route_divergence_at27_new", attack=True,
        silent_divergence_at=27, silent_divergence_sources=("route",),
    ),
    Scenario(
        "cache_divergence_at38_new", attack=True,
        silent_divergence_at=38, silent_divergence_sources=("ausf",),
    ),
    Scenario(
        "dual_divergence_at31_new", attack=True,
        silent_divergence_at=31,
        silent_divergence_sources=("ausf", "route"),
    ),
)
ARMS = (
    "consensus_guard", "patef_learned_only",
    "residual_no_age_no_dropout",
    "residual_age_dropout", "residual_sequential",
)
SEEDS_TRAIN = range(0, 30)
SEEDS_CAL = range(30, 40)
SEEDS_TEST = range(300, 324)
STEPS = 90


def augmented_train(raw: pd.DataFrame) -> pd.DataFrame:
    parts = [make_view(raw, name) for name in TRAIN_VIEWS]
    # One reproducible dropout copy for each parent run. Up to two sources
    # vanish, with the capture clocks removed just like their state values.
    rng = np.random.default_rng(42)
    dropout = attach_acquisition_times(raw)
    for _, indices in dropout.groupby("run_id", sort=False).groups.items():
        count = int(rng.integers(1, 3))
        sources = rng.choice(tuple(SOURCE_COLUMNS), size=count, replace=False)
        for source in sources:
            cols = SOURCE_COLUMNS[source]
            for col in cols[:-1]:
                dropout.loc[indices, col] = np.nan
            dropout.loc[indices, cols[-1]] = 0
            dropout.loc[indices, f"{source}_origin_t"] = np.nan
    parts.append(build_features(with_causal_source_ages(dropout)))
    return pd.concat(parts, ignore_index=True)


def score_arms(
    frame: pd.DataFrame,
    base: PatefResidualGuard,
    hybrid: PatefResidualGuard,
    seq: PatefResidualGuard,
    learned_threshold: float,
) -> dict[str, pd.DataFrame]:
    guard = base.guard_alerts(frame)
    masks = availability_mask(frame)
    scores = base.fusion.learned_scores(frame)
    result = {
        "consensus_guard": pd.DataFrame({
            "pred": guard, "mask": masks,
            "incremental": np.zeros(len(frame), dtype=bool),
            "threshold": float(np.nextafter(0.0, np.inf)),
        }),
        "patef_learned_only": pd.DataFrame({
            "pred": scores >= learned_threshold, "mask": masks,
            "incremental": np.zeros(len(frame), dtype=bool),
            "threshold": learned_threshold,
        }),
    }
    for name, model in (
        ("residual_no_age_no_dropout", base),
        ("residual_age_dropout", hybrid),
        ("residual_sequential", seq),
    ):
        decision = model.decide(frame)
        result[name] = pd.DataFrame({
            "pred": decision["hybrid_alert"].to_numpy(bool),
            "mask": decision["mask"].to_numpy(),
            "incremental": decision["residual_alert"].to_numpy(bool),
            "threshold": decision["threshold"].to_numpy(float),
        })
        if np.any(guard & ~result[name]["pred"].to_numpy(bool)):
            raise AssertionError(f"guard was suppressed: {name}")
    return result


def scenario_rows(
    view: str, arm: str, frame: pd.DataFrame, scored: pd.DataFrame,
) -> list[dict]:
    data = frame[[
        "run_id", "scenario", "t", "attack_start", "attack_active",
    ]].reset_index(drop=True).copy()
    for column in scored:
        data[column] = scored[column].to_numpy()
    out = []
    # Partition by availability mask as well as scenario; runs can change
    # masks during lag warmup. Do not count zero-attack mask groups as attacks.
    for (scenario, mask), g in data.groupby(["scenario", "mask"], sort=True):
        attacked = g["attack_active"].to_numpy(bool)
        pred = g["pred"].to_numpy(bool)
        benign = ~attacked
        if attacked.any():
            delay, detected, total = _run_delay(
                g, pred.astype(float), 0.5
            )
        else:
            delay, detected, total = (float("inf"), 0, 0)
        out.append({
            "view": view,
            "arm": arm,
            "scenario": scenario,
            "mask": mask,
            "benign_samples": int(benign.sum()),
            "attack_samples": int(attacked.sum()),
            "false_positives": int(pred[benign].sum()),
            "true_positives": int(pred[attacked].sum()),
            "incremental_alerts": int(g["incremental"].sum()),
            "fpr": float(pred[benign].mean()) if benign.any() else None,
            "recall": float(pred[attacked].mean()) if attacked.any() else None,
            "median_detection_delay": delay if np.isfinite(delay) else None,
            "detected_attack_runs": int(detected),
            "total_attack_runs": int(total),
            "calibration_cutoff_min": float(g["threshold"].min()),
            "calibration_cutoff_max": float(g["threshold"].max()),
        })
    return out


def summarize(data: pd.DataFrame, original: pd.DataFrame) -> pd.DataFrame:
    summary = []
    for (view, arm), g in data.groupby(["view", "arm"], sort=True):
        benign = int(g["benign_samples"].sum())
        attack = int(g["attack_samples"].sum())
        fp = int(g["false_positives"].sum())
        tp = int(g["true_positives"].sum())
        delays = []
        for scenario in CHALLENGE_SCENARIOS:
            if not scenario.attack:
                continue
            subset = original.loc[original["scenario"] == scenario.name]
            scored = subset.loc[
                (subset["view"] == view) & (subset["arm"] == arm)
            ]
            if not scored.empty:
                delays.extend(scored["delay"].dropna().tolist())
        summary.append({
            "view": view,
            "arm": arm,
            "benign_samples": benign,
            "attack_samples": attack,
            "false_positives": fp,
            "true_positives": tp,
            "fpr": fp / benign if benign else None,
            "recall": tp / attack if attack else None,
            "incremental_alerts": int(g["incremental_alerts"].sum()),
            "worst_mask_fpr": float(g.loc[g["benign_samples"] > 0, "fpr"].max()),
            "median_run_delay": float(np.median(delays)) if delays else None,
        })
    return pd.DataFrame(summary)


def run_bootstrap(
    observations: pd.DataFrame,
    results: dict[str, dict[str, pd.DataFrame]],
    reps: int = 300,
) -> pd.DataFrame:
    """Paired parent-run bootstrap stratified by *new* scenario, not samples."""
    rng = np.random.default_rng(42)
    data = []
    for view in VIEWS:
        frame = observations.loc[observations["view"] == view]
        # stored predictions must follow original row order for this view
        for arm in ("residual_no_age_no_dropout", "residual_age_dropout",
                    "residual_sequential"):
            guard = results[view]["consensus_guard"]["pred"].to_numpy(bool)
            hybrid = results[view][arm]["pred"].to_numpy(bool)
            y = frame["attack_active"].to_numpy(bool)
            parts = []
            for _, g in frame.reset_index(drop=True).groupby(
                ["scenario", "run_id"], sort=False
            ):
                indices = g.index.to_numpy()
                active = int(y[indices].sum())
                benign = int((~y[indices]).sum())
                parts.append({
                    "scenario": g["scenario"].iloc[0],
                    "active": active, "benign": benign,
                    "baseline_tp": int((guard[indices] & y[indices]).sum()),
                    "hybrid_tp": int((hybrid[indices] & y[indices]).sum()),
                    "hybrid_fp": int((hybrid[indices] & ~y[indices]).sum()),
                })
            grouped: dict[str, list[dict]] = {}
            for p in parts:
                grouped.setdefault(p["scenario"], []).append(p)
            deltas, fprs = [], []
            for _ in range(reps):
                sampled = [
                    group[int(rng.integers(len(group)))]
                    for group in grouped.values()
                    for _ in group
                ]
                attacks = sum(p["active"] for p in sampled)
                benign = sum(p["benign"] for p in sampled)
                deltas.append(
                    sum(p["hybrid_tp"] - p["baseline_tp"] for p in sampled)
                    / attacks if attacks else 0.0
                )
                fprs.append(
                    sum(p["hybrid_fp"] for p in sampled) / benign
                    if benign else 0.0
                )
            data.append({
                "view": view,
                "arm": arm,
                "bootstrap_replicates": reps,
                "unit": "parent_run_stratified_by_scenario",
                "recall_delta_lower_95": float(np.quantile(deltas, 0.025)),
                "recall_delta_upper_95": float(np.quantile(deltas, 0.975)),
                "fpr_lower_95": float(np.quantile(fprs, 0.025)),
                "fpr_upper_95": float(np.quantile(fprs, 0.975)),
            })
    return pd.DataFrame(data)


def verdict(
    details: pd.DataFrame, summary: pd.DataFrame,
    boot: pd.DataFrame, models: list[PatefResidualGuard],
) -> dict:
    named = summary.set_index(["view", "arm"])
    checks = []
    all_h1 = True
    h2_recall = False
    h2_new_scenarios = False
    h3 = []
    for view in VIEWS:
        baseline = named.loc[(view, "consensus_guard")]
        candidate = named.loc[(view, "residual_age_dropout")]
        masks = details.loc[
            (details["view"] == view)
            & (details["arm"] == "residual_age_dropout")
            & (details["benign_samples"] > 0)
        ]
        mask_pass = bool((masks["fpr"] <= TARGET_FPR).all())
        recall_pass = bool(candidate["recall"] + 1e-12 >= baseline["recall"])
        delay_pass = bool(
            candidate["median_run_delay"] <= baseline["median_run_delay"]
            if pd.notna(baseline["median_run_delay"]) else True
        )
        baseline_infeasible = bool(
            named.loc[(view, "consensus_guard"), "fpr"] > TARGET_FPR
        )
        case = {
            "view": view,
            "baseline_fpr": float(baseline["fpr"]),
            "hybrid_fpr": float(candidate["fpr"]),
            "baseline_recall": float(baseline["recall"]),
            "hybrid_recall": float(candidate["recall"]),
            "mask_fpr_budget_pass": mask_pass,
            "recall_nonregression": recall_pass,
            "delay_nonregression": delay_pass,
            "baseline_budget_infeasible": baseline_infeasible,
            "incremental_alerts": int(candidate["incremental_alerts"]),
        }
        all_h1 &= mask_pass and recall_pass and delay_pass
        checks.append(case)
        if view != "original":
            gain = float(candidate["recall"] - baseline["recall"])
            interval = boot.loc[
                (boot["view"] == view)
                & (boot["arm"] == "residual_age_dropout")
            ].iloc[0]
            h2_recall |= (gain >= 0.01
                          and interval["recall_delta_lower_95"] > 0.0)
        for view_name in ("no_ausf", "no_route"):
            if view == view_name:
                h3.append({
                    "view": view,
                    "recall_gt_0_62": bool(candidate["recall"] > 0.62),
                    "mask_budget_pass": mask_pass,
                })

    for view in VIEWS:
        tested = details.loc[(details["view"] == view)
                             & (details["arm"].isin(
                                 ("consensus_guard", "residual_age_dropout")
                             ))]
        per_scenario = tested.groupby(["arm", "scenario"])[
            ["true_positives", "attack_samples"]
        ].sum()
        winners = 0
        for scenario in CHALLENGE_SCENARIOS:
            if not scenario.attack:
                continue
            a = per_scenario.loc[
                ("consensus_guard", scenario.name), "true_positives"
            ]
            b = per_scenario.loc[
                ("residual_age_dropout", scenario.name), "true_positives"
            ]
            winners += int(b > a)
        h2_new_scenarios |= winners >= 2
    h1 = bool(all_h1)
    return {
        "protocol": "docs/stage6-residual-protocol.md",
        "target_fpr": TARGET_FPR,
        "source_age_provenance": "synthetic_oracle_no_real_authentication",
        "truth_free_guard_union_guarantee": True,
        "calibration_lag_and_mask_views_correlated": True,
        "test_scenarios": [s.name for s in CHALLENGE_SCENARIOS],
        "test_seeds": [300, 323],
        "h1_view_checks": checks,
        "h1_success": h1,
        "h2_two_attack_scenarios_strictly_improved": h2_new_scenarios,
        "h2_run_bootstrap_stressed_gain_at_least_1pp": h2_recall,
        "h2_success": bool(h1 and h2_new_scenarios and h2_recall),
        "h3_masks": h3,
        "h3_success": bool(all(
            c["recall_gt_0_62"] and c["mask_budget_pass"] for c in h3
        ) and len(h3) == 2),
        "calibration_has_residual_abstentions": {
            name: sum(int(p["residual_abstains"]) for p in model.mask_reports)
            for name, model in zip(
                ["no_age_no_dropout", "age_dropout", "sequential"],
                models, strict=True,
            )
        },
        "real_provenance_fusion_validated": False,
        "population_fpr_guarantee_established": False,
        "production_promotion_allowed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)

    train_raw = simulate_dataset(DEFAULT_SCENARIOS, SEEDS_TRAIN, STEPS)
    cal_raw = simulate_dataset(DEFAULT_SCENARIOS, SEEDS_CAL, STEPS)
    heldout_raw = simulate_dataset(CHALLENGE_SCENARIOS, SEEDS_TEST, STEPS)
    ids = (
        set(train_raw["run_id"]), set(cal_raw["run_id"]),
        set(heldout_raw["run_id"]),
    )
    assert not ids[0].intersection(ids[1])
    assert not ids[0].intersection(ids[2])
    assert not ids[1].intersection(ids[2])
    assert not set(heldout_raw["scenario"]).intersection(
        set(train_raw["scenario"])
    )
    train_base = make_view(train_raw, "original")
    train_aug = augmented_train(train_raw)
    cal_frames = {v: make_view(cal_raw, v) for v in CAL_VIEWS}
    test_frames = {v: make_view(heldout_raw, v) for v in VIEWS}
    print(
        f"locked parents train={len(ids[0])},cal={len(ids[1])},test={len(ids[2])}; "
        f"train augmented rows={len(train_aug)}",
        flush=True,
    )

    base = PatefResidualGuard(random_state=42, use_ages=False)
    base.fit(train_base).calibrate(cal_frames["original"], cal_frames)
    print("fitted and mask-calibrated unaugmented PA-TEF", flush=True)
    hybrid = PatefResidualGuard(random_state=42, use_ages=True)
    hybrid.fit(train_aug).calibrate(cal_frames["original"], cal_frames)
    print("fitted and mask-calibrated augmented freshness PA-TEF", flush=True)
    sequential = PatefResidualGuard(
        random_state=42, use_ages=True, sequential=True
    )
    sequential.fusion = hybrid.fusion
    sequential.calibrate(cal_frames["original"], cal_frames)
    print("calibrated fixed causal sequential max-3 residual", flush=True)

    pristine_cal = cal_frames["original"]
    learned_threshold = _threshold_at_fpr(
        base.fusion.learned_scores(pristine_cal),
        pristine_cal["attack_active"].to_numpy(),
        TARGET_FPR,
    )
    details = []
    run_summaries = []
    stored_predictions: dict[str, dict[str, pd.DataFrame]] = {}
    bootstrap_inputs = []
    for view, frame in test_frames.items():
        scored = score_arms(frame, base, hybrid, sequential, learned_threshold)
        stored_predictions[view] = scored
        for name, predictions in scored.items():
            details.extend(scenario_rows(view, name, frame, predictions))
            truth = frame[[
                "run_id", "scenario", "t", "attack_start", "attack_active"
            ]].copy()
            truth["view"], truth["arm"] = view, name
            truth["pred"] = predictions["pred"].to_numpy(bool)
            for scenario, subset in truth.groupby("scenario", sort=False):
                if not subset["attack_active"].astype(bool).any():
                    continue
                delay, detected, total = _run_delay(
                    subset, subset["pred"].to_numpy(float), 0.5
                )
                run_summaries.append({
                    "view": view, "arm": name, "scenario": scenario,
                    "delay": float(delay) if np.isfinite(delay) else None,
                    "detected_attack_runs": detected,
                    "total_attack_runs": total,
                })
        info = frame[["run_id", "scenario", "t", "attack_active"]].copy()
        info["view"] = view
        bootstrap_inputs.append(info)
        print(f"completed heldout observer view {view}", flush=True)
    details_df = pd.DataFrame(details)
    runs_df = pd.DataFrame(run_summaries)
    summary = summarize(details_df, runs_df)
    boot = run_bootstrap(
        pd.concat(bootstrap_inputs, ignore_index=True), stored_predictions
    )
    decision = verdict(details_df, summary, boot, [base, hybrid, sequential])

    cal_reports = []
    for name, detector in (
        ("no_age_no_dropout", base),
        ("age_dropout", hybrid),
        ("sequential", sequential),
    ):
        cal_reports.extend({"arm": name, **row} for row in detector.mask_reports)
    pd.DataFrame(cal_reports).to_csv(
        output / "stage6-mask-thresholds.csv", index=False
    )
    details_df.to_csv(output / "stage6-scenarios.csv", index=False)
    summary.to_csv(output / "stage6-summary.csv", index=False)
    boot.to_csv(output / "stage6-bootstrap.csv", index=False)
    runs_df.to_csv(output / "stage6-episode-delay.csv", index=False)
    (output / "stage6-decision.json").write_text(
        json.dumps(decision, indent=2), encoding="utf-8"
    )
    (output / "stage6-config.json").write_text(
        json.dumps({
            "training_seeds": [0, 29],
            "calibration_seeds": [30, 39],
            "test_seeds": [300, 323],
            "steps": STEPS,
            "training_views": list(TRAIN_VIEWS),
            "calibration_views": list(CAL_VIEWS),
            "test_views": list(VIEWS),
            "target_fpr": TARGET_FPR,
            "bootstrap_replicates": 300,
            "calibration_minimum_benign_per_mask_scenario": 20,
            "source_age": "simulator_oracle_only",
            "new_attack_traffic": False,
        }, indent=2), encoding="utf-8"
    )
    print(summary.to_csv(index=False), flush=True)
    print(json.dumps(decision, indent=2), flush=True)


if __name__ == "__main__":
    main()
