from __future__ import annotations

import numpy as np

from nfnotify_lab.freshness import (
    aligned_features,
    attach_acquisition_times,
    context_aligned_features,
    observed_view,
)
from nfnotify_lab.simulator import ROGUE_UDM, Scenario, simulate_dataset


def _scenario(scenario: Scenario):
    return attach_acquisition_times(simulate_dataset((scenario,), range(2), steps=90))


def test_recovery_context_follows_route_origin_not_arrival():
    obs = observed_view(
        _scenario(Scenario("recovery", recovery_start=30, recovery_end=45)),
        "route_lag4",
    )
    state = aligned_features(obs)
    context = context_aligned_features(obs)
    # t46 arrived after recovery, but route snapshot came from t42 during recovery.
    late = state["t"].eq(46)
    assert obs.loc[late, "route_origin_t"].eq(42).all()
    assert obs.loc[late, "recovery_active"].eq(0).all()
    assert state.loc[late, "delta_route"].eq(1).all()
    assert context.loc[late, "delta_route"].eq(0).all()
    assert context.loc[late, "eventtime_route_recovery_explained"].eq(1).all()
    assert context.loc[late, "delta_nrf_ausf"].eq(
        state.loc[late, "delta_nrf_ausf"]
    ).all()


def test_update_context_explains_historically_legit_delayed_route():
    obs = observed_view(
        _scenario(Scenario("laggy_notify", legit_update_at=35, notify_delay=14)),
        "route_lag8",
    )
    state = aligned_features(obs)
    context = context_aligned_features(obs)
    changed = context["eventtime_route_transition_explained"].eq(1)
    assert changed.any()
    assert state.loc[changed, "delta_route"].eq(1).all()
    assert context.loc[changed, "delta_route"].eq(0).all()


def test_absent_nrf_evidence_cannot_create_trusted_context():
    obs = observed_view(
        _scenario(Scenario("recovery", recovery_start=30, recovery_end=45)),
        "route_lag4",
    )
    obs.loc[obs["t"].eq(42), ["nrf_endpoint", "nrf_update_seen", "nrf_origin_t"]] = np.nan
    obs.loc[obs["t"].eq(42), "m_nrf"] = 0
    context = context_aligned_features(obs)
    assert context.loc[context["t"].eq(46), "delta_route"].isna().all()
    assert context.loc[context["t"].eq(46), "eventtime_route_explained"].eq(0).all()


def test_cache_attack_not_hidden_by_unrelated_route_recovery_context():
    scenario = Scenario(
        "cache_attack", attack=True, silent_divergence_at=42,
        silent_divergence_sources=("ausf",),
        recovery_start=30, recovery_end=45,
    )
    obs = _scenario(scenario)
    obs.loc[obs["t"].ge(42), "ausf_endpoint"] = ROGUE_UDM
    observed = observed_view(obs, "route_lag4")
    context = context_aligned_features(observed)
    recovery_late = context["t"].eq(46)
    assert context.loc[recovery_late, "eventtime_route_recovery_explained"].eq(1).all()
    assert context.loc[recovery_late, "delta_nrf_ausf"].eq(1).all()
    assert context.loc[recovery_late, "eventtime_ausf_explained"].eq(0).all()


def test_bad_notify_evidence_is_not_mutated():
    obs = _scenario(
        Scenario("bad_notify", attack=True, forged_notify_at=35)
    )
    raw = observed_view(obs, "route_lag4")
    state = aligned_features(raw)
    context = context_aligned_features(raw)
    assert context["delta_notify"].equals(state["delta_notify"])
    assert context["recent_bad_notify_seen_6"].equals(
        state["recent_bad_notify_seen_6"]
    )


def test_source_origin_is_causal_and_labels_are_invariant():
    obs = _scenario(
        Scenario("benign", recovery_start=30, recovery_end=45)
    )
    for view in (
        "original", "route_lag4", "both_lag2", "route_lag8",
        "route_jitter2_6", "nrf_burst3",
    ):
        raw = observed_view(obs, view)
        frame = context_aligned_features(raw)
        assert frame["attack_active"].equals(raw["attack_active"])
        assert frame["attack_start"].equals(raw["attack_start"])
        for source in ("nrf", "ausf", "route", "notify"):
            clock = raw[f"{source}_origin_t"].dropna()
            assert (clock <= raw.loc[clock.index, "t"]).all()
