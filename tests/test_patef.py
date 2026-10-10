import numpy as np
import pandas as pd

from nfnotify_lab.detectors import build_detector
from nfnotify_lab.evaluate import evaluate_all
from nfnotify_lab.patef import provenance_normalized_attack_gate
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import (
    DEFAULT_SCENARIOS,
    Scenario,
    simulate_dataset,
    simulate_run,
)


def test_patef_detects_forged_notify_at_low_fpr():
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(12), steps=65)
    features = build_features(raw)
    metrics = evaluate_all(features, target_fpr=0.02, random_state=11)
    patef = metrics.loc[metrics["detector"] == "patef"].iloc[0]

    assert patef["fpr"] <= 0.03
    assert patef["recall_at_target_fpr"] >= 0.90
    assert patef["pr_auc"] >= 0.95


def test_temporal_features_do_not_cross_runs():
    raw = simulate_dataset(DEFAULT_SCENARIOS[:2], seeds=range(2), steps=10)
    features = build_features(raw)

    first_rows = features.groupby("run_id", sort=False).head(1)
    assert (first_rows["state_conflict_persist"] == 0).all()
    assert (first_rows["since_notify"] >= 0).all()
    assert isinstance(features, pd.DataFrame)


def test_endpoint_change_recovers_a_missed_update_event():
    scenario = Scenario("missed_update_probe", legit_update_at=5, notify_delay=3)
    raw = simulate_run(scenario, seed=0, steps=12)
    missed = raw["t"] == 5
    raw.loc[missed, "nrf_endpoint"] = None
    raw.loc[missed, "nrf_update_seen"] = np.nan

    features = build_features(raw)
    first_visible_new_endpoint = features.loc[features["t"] == 6].iloc[0]

    assert first_visible_new_endpoint["nrf_endpoint_changed"] == 1.0
    assert first_visible_new_endpoint["recent_nrf_endpoint_changed_12"] == 1.0
    assert first_visible_new_endpoint["trusted_transition"] == 1.0



def test_patef_v2_gate_suppresses_short_single_observer_skew():
    skew = next(s for s in DEFAULT_SCENARIOS if s.name == "cache_observer_skew")
    features = build_features(simulate_run(skew, seed=0, steps=50))
    gate = provenance_normalized_attack_gate(features)

    skew_window = features["t"].between(30, 35)
    assert gate.loc[skew_window].eq(0.0).all()


def test_patef_v2_gate_accepts_dual_conflict_immediately():
    attack = next(s for s in DEFAULT_SCENARIOS if s.name == "silent_dual_divergence")
    features = build_features(simulate_run(attack, seed=0, steps=50))
    gate = provenance_normalized_attack_gate(features)

    first = features.loc[features["t"] == 35].index[0]
    assert gate.loc[first] == 1.0


def test_patef_v2_partial_state_waits_for_persistence():
    attack = next(
        s for s in DEFAULT_SCENARIOS if s.name == "persistent_cache_divergence"
    )
    raw = simulate_run(attack, seed=0, steps=50)
    raw.loc[raw["t"] >= 35, "route_endpoint"] = None
    raw.loc[raw["t"] >= 35, "m_route"] = 0
    features = build_features(raw)
    gate = provenance_normalized_attack_gate(features)

    assert gate.loc[features["t"].between(35, 40)].eq(0.0).all()
    first_ready = features.loc[features["t"] == 41].index[0]
    assert gate.loc[first_ready] == 1.0


def test_patef_v2_gate_is_source_symmetric():
    cache_skew = next(
        s for s in DEFAULT_SCENARIOS if s.name == "cache_observer_skew"
    )
    route_skew = next(
        s for s in DEFAULT_SCENARIOS if s.name == "route_observer_skew"
    )
    cache_gate = provenance_normalized_attack_gate(
        build_features(simulate_run(cache_skew, seed=0, steps=50))
    )
    route_gate = provenance_normalized_attack_gate(
        build_features(simulate_run(route_skew, seed=0, steps=50))
    )

    assert cache_gate.tolist() == route_gate.tolist()


def test_patef_gate_only_exactly_matches_decision_gate():
    scenario = next(
        s for s in DEFAULT_SCENARIOS if s.name == "silent_dual_divergence"
    )
    features = build_features(simulate_run(scenario, seed=2, steps=50))
    detector = build_detector("patef_gate_only", random_state=3)
    detector.fit(features, features["attack_active"])

    expected = provenance_normalized_attack_gate(features).to_numpy()
    actual = detector.score_samples(features)
    assert np.array_equal(actual, expected)


def test_patef_learned_only_has_no_decision_gate_or_consensus_meta():
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(8), steps=50)
    features = build_features(raw)
    detector = build_detector("patef_learned_only", random_state=5)

    assert detector.use_decision_gate is False
    assert detector.include_consensus_meta is False
    assert "consensus_support" not in detector.meta_features

    detector.fit(features, features["attack_active"])
    scores = detector.score_samples(features)
    assert np.isfinite(scores).all()
    assert ((scores >= 0.0) & (scores <= 1.0)).all()
