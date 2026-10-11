"""No label leakage, no lookahead, no consensus suppression in Stage 6."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nfnotify_lab.consensus import consensus_attack_support
from nfnotify_lab.patef_residual import (
    ABSTAIN_THRESHOLD,
    PatefResidualGuard,
    rolling_residual_scores,
    threshold_for_allowed_fps,
)
from nfnotify_lab.residual_freshness import (
    availability_mask,
    make_view,
    with_causal_source_ages,
)
from nfnotify_lab.simulator import Scenario, simulate_dataset


class FakeFusion:
    def calibrate(self, frame, labels):
        return self

    def learned_scores(self, frame):
        return np.asarray(frame["t"], dtype=float) / 100.0


def _sample():
    scenarios = (
        Scenario("stable"),
        Scenario(
            "attack", attack=True, silent_divergence_at=5,
            silent_divergence_sources=("ausf", "route"),
        ),
    )
    return simulate_dataset(scenarios, seeds=range(3), steps=20)


def test_guard_invariant_on_all_views_even_abstaining():
    raw = _sample()
    model = PatefResidualGuard()
    model.fusion = FakeFusion()
    model.thresholds = {"1111": ABSTAIN_THRESHOLD}
    for view in ("original", "route_lag4", "both_lag2", "no_ausf",
                 "no_route", "no_nrf"):
        frame = make_view(raw, view)
        scores = model.decide(frame)
        reference = consensus_attack_support(frame).to_numpy(float) > 0
        assert np.array_equal(scores["guard_alert"].to_numpy(bool), reference)
        assert not ((~scores["hybrid_alert"]) & reference).any()


def test_calibration_uses_only_benign_guard_silent_points():
    raw = simulate_dataset((Scenario("benign"),), seeds=range(2), steps=25)
    features = make_view(raw, "original")
    model = PatefResidualGuard(target_fpr=0.001)
    model.fusion = FakeFusion()
    model.calibrate(features, {"original": features})
    report = model.mask_reports[0]
    assert report["baseline_calibration_fp"] == 0
    assert report["residual_calibration_fp"] == 0
    assert model.thresholds["1111"] > 0.24
    assert not model.decide(features)["hybrid_alert"].any()


def test_group_mask_without_calibration_abstains():
    frame = make_view(_sample(), "no_ausf")
    model = PatefResidualGuard()
    model.fusion = FakeFusion()
    model.thresholds = {"1111": 0.25}
    decision = model.decide(frame)
    assert decision.loc[
        decision["mask"].ne("1111"), "residual_alert"
    ].eq(False).all()


def test_threshold_ties_are_never_partially_counted():
    scores = np.array([0.8, 0.8, 0.7, 0.5])
    threshold = threshold_for_allowed_fps(scores, 1)
    assert (scores >= threshold).sum() <= 1
    assert threshold > 0.8
    next_threshold = threshold_for_allowed_fps(scores, 2)
    assert (scores >= next_threshold).sum() <= 2
    assert threshold_for_allowed_fps(np.array([]), 3) == ABSTAIN_THRESHOLD
    with pytest.raises(ValueError, match="non-finite"):
        threshold_for_allowed_fps(np.array([np.nan]), 0)


def test_causal_age_missing_and_future_are_not_zero():
    observed = make_view(_sample(), "route_lag4")
    early = observed["t"] < 4
    assert observed.loc[early, "age_route"].isna().all()
    assert observed.loc[early, "age_route_missing"].eq(1).all()
    later = observed["t"] >= 4
    assert observed.loc[later, "age_route"].eq(4).all()
    assert observed.loc[later, "age_route_missing"].eq(0).all()

    future = observed.copy()
    future["ausf_origin_t"] = future["t"] + 5
    future = with_causal_source_ages(future)
    assert future["age_ausf"].isna().all()
    assert future["age_ausf_missing"].eq(1).all()


def test_source_mask_removes_clock_and_endpoint_but_not_labels():
    raw = _sample()
    frame = make_view(raw, "no_route")
    assert frame["m_route"].eq(0).all()
    assert frame["route_endpoint"].isna().all()
    assert frame["route_origin_t"].isna().all()
    assert frame["age_route"].isna().all()
    assert frame["attack_active"].to_numpy().tolist() == (
        raw.sort_values(["run_id", "t"])["attack_active"].to_numpy().tolist()
    )
    assert set(availability_mask(frame)) == {"1101"}


def test_sequential_scores_do_not_look_ahead_or_cross_runs():
    df = pd.DataFrame({
        "run_id": ["a", "a", "a", "b", "b"],
        "t": [0, 1, 2, 0, 1],
    })
    scores = np.array([0.1, 0.9, 0.2, 0.05, 0.01])
    out = rolling_residual_scores(df, scores)
    assert np.allclose(out, [0.1, 0.9, 0.9, 0.05, 0.05])
    changed_future = scores.copy()
    changed_future[2] = 0.99
    alt = rolling_residual_scores(df, changed_future)
    assert np.allclose(out[:2], alt[:2])


def test_model_separates_masks_and_reports_abstention():
    raw = _sample()
    pristine = make_view(raw, "original")
    masked = make_view(raw, "no_nrf")
    model = PatefResidualGuard(target_fpr=0.001)
    model.fusion = FakeFusion()
    model.calibrate(
        pristine, {"original": pristine, "no_nrf": masked}
    )
    report = {p["mask"]: p for p in model.mask_reports}
    assert set(report) == {"1111", "0111"}
    assert all(p["calibration_fpr"] <= 0.001 for p in report.values())


def test_calibration_rejects_mismatching_parent_runs():
    raw = _sample()
    pristine = make_view(raw, "original")
    mismatched = pristine.loc[pristine["run_id"] != raw["run_id"].iloc[0]]
    model = PatefResidualGuard()
    model.fusion = FakeFusion()
    with pytest.raises(ValueError, match="nonmatching"):
        model.calibrate(pristine, {"broken": mismatched})
