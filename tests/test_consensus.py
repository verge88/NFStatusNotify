from nfnotify_lab.consensus import consensus_attack_support
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_run


def _scenario(name: str):
    return next(s for s in DEFAULT_SCENARIOS if s.name == name)


def _first_positive_delay(name: str) -> int:
    scenario = _scenario(name)
    raw = simulate_run(scenario, seed=0, steps=60)
    features = build_features(raw)
    scores = consensus_attack_support(features)
    active = features["attack_active"].astype(bool)
    positive = features.loc[active & scores.gt(0), "t"]
    assert len(positive)
    return int(positive.iloc[0] - int(features["attack_start"].iloc[0]))


def test_consensus_guard_suppresses_short_single_source_observer_skew():
    for name in ("cache_observer_skew", "route_observer_skew"):
        raw = simulate_run(_scenario(name), seed=0, steps=60)
        features = build_features(raw)
        scores = consensus_attack_support(features)
        assert float(scores.max()) == 0.0


def test_consensus_guard_uses_longer_grace_for_single_source_divergence():
    assert _first_positive_delay("persistent_cache_divergence") == 11
    assert _first_positive_delay("persistent_route_divergence") == 11


def test_consensus_guard_escalates_dual_source_divergence_quickly():
    assert _first_positive_delay("silent_dual_divergence") == 1
    assert _first_positive_delay("forged_notify") == 0
