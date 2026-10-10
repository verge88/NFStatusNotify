from nfnotify_lab.consensus import (
    DUAL_SOURCE_PERSISTENCE_STEPS,
    REFERENCE_DUAL_SOURCE_PERSISTENCE_STEPS,
    REFERENCE_SINGLE_SOURCE_PERSISTENCE_STEPS,
    SINGLE_SOURCE_PERSISTENCE_STEPS,
    consensus_attack_support,
)
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_run


def _scenario(name: str):
    return next(s for s in DEFAULT_SCENARIOS if s.name == name)


def _first_positive_delay(
    name: str,
    *,
    single_source_steps: int = SINGLE_SOURCE_PERSISTENCE_STEPS,
    dual_source_steps: int = DUAL_SOURCE_PERSISTENCE_STEPS,
) -> int:
    scenario = _scenario(name)
    raw = simulate_run(scenario, seed=0, steps=60)
    features = build_features(raw)
    scores = consensus_attack_support(
        features,
        single_source_steps=single_source_steps,
        dual_source_steps=dual_source_steps,
    )
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


def test_validated_default_uses_eight_sample_single_source_gate():
    assert SINGLE_SOURCE_PERSISTENCE_STEPS == 8
    assert _first_positive_delay("persistent_cache_divergence") == 7
    assert _first_positive_delay("persistent_route_divergence") == 7


def test_validated_default_escalates_dual_source_divergence_immediately():
    assert DUAL_SOURCE_PERSISTENCE_STEPS == 1
    assert _first_positive_delay("silent_dual_divergence") == 0
    assert _first_positive_delay("forged_notify") == 0


def test_historical_reference_remains_reproducible():
    assert REFERENCE_SINGLE_SOURCE_PERSISTENCE_STEPS == 12
    assert REFERENCE_DUAL_SOURCE_PERSISTENCE_STEPS == 2
    assert (
        _first_positive_delay(
            "persistent_cache_divergence",
            single_source_steps=REFERENCE_SINGLE_SOURCE_PERSISTENCE_STEPS,
            dual_source_steps=REFERENCE_DUAL_SOURCE_PERSISTENCE_STEPS,
        )
        == 11
    )
    assert (
        _first_positive_delay(
            "silent_dual_divergence",
            single_source_steps=REFERENCE_SINGLE_SOURCE_PERSISTENCE_STEPS,
            dual_source_steps=REFERENCE_DUAL_SOURCE_PERSISTENCE_STEPS,
        )
        == 1
    )
