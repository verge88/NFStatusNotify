import numpy as np

from nfnotify_lab.features import build_features
from nfnotify_lab.patef import provenance_normalized_attack_gate
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_run


def test_patef_gate_parameterization_is_monotone_for_single_conflict():
    scenario = next(
        s for s in DEFAULT_SCENARIOS if s.name == "persistent_cache_divergence"
    )
    features = build_features(simulate_run(scenario, seed=0, steps=50))

    permissive = provenance_normalized_attack_gate(
        features, single_source_steps=3, dual_source_steps=1
    )
    conservative = provenance_normalized_attack_gate(
        features, single_source_steps=7, dual_source_steps=1
    )

    assert (permissive >= conservative).all()
    assert permissive.sum() >= conservative.sum()


def test_patef_gate_rejects_nonpositive_persistence():
    scenario = next(s for s in DEFAULT_SCENARIOS if s.name == "stable")
    features = build_features(simulate_run(scenario, seed=0, steps=10))

    try:
        provenance_normalized_attack_gate(
            features, single_source_steps=0, dual_source_steps=1
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for zero persistence")


def test_default_gate_matches_explicit_7_1():
    scenario = next(
        s for s in DEFAULT_SCENARIOS if s.name == "silent_dual_divergence"
    )
    features = build_features(simulate_run(scenario, seed=1, steps=50))

    default = provenance_normalized_attack_gate(features).to_numpy()
    explicit = provenance_normalized_attack_gate(
        features, single_source_steps=7, dual_source_steps=1
    ).to_numpy()
    assert np.array_equal(default, explicit)
