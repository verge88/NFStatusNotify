from nfnotify_lab.features import build_features
from nfnotify_lab.patef import semantic_attack_support
from nfnotify_lab.simulator import (
    ALT_UDM,
    LEGIT_UDM,
    ROGUE_UDM,
    Scenario,
    simulate_run,
)


def test_observer_skew_changes_only_reported_cache_view():
    scenario = Scenario(
        "cache_observer_skew_test",
        observer_skew_at=4,
        observer_skew_duration=3,
        observer_skew_sources=("ausf",),
    )
    rows = simulate_run(scenario, seed=0, steps=10)

    during = rows[(rows["t"] >= 4) & (rows["t"] < 7)]
    after = rows[rows["t"] >= 7]

    assert (during["nrf_endpoint"] == LEGIT_UDM).all()
    assert (during["route_endpoint"] == LEGIT_UDM).all()
    assert (during["ausf_endpoint"] == ALT_UDM).all()
    assert (after["ausf_endpoint"] == LEGIT_UDM).all()
    assert (rows["attack_active"] == 0).all()


def test_silent_divergence_has_no_bad_notification_evidence():
    scenario = Scenario(
        "silent_dual_test",
        attack=True,
        silent_divergence_at=4,
        silent_divergence_sources=("ausf", "route"),
    )
    rows = simulate_run(scenario, seed=0, steps=10)

    after = rows[rows["t"] >= 4]
    assert (after["nrf_endpoint"] == LEGIT_UDM).all()
    assert (after["ausf_endpoint"] == ROGUE_UDM).all()
    assert (after["route_endpoint"] == ROGUE_UDM).all()
    assert (after["notify_seen"] == 0).all()
    assert (after["attack_active"] == 1).all()


def test_benign_skew_and_persistent_divergence_overlap_semantic_support():
    benign = Scenario(
        "cache_observer_skew_test",
        observer_skew_at=10,
        observer_skew_duration=6,
        observer_skew_sources=("ausf",),
    )
    attack = Scenario(
        "persistent_cache_test",
        attack=True,
        silent_divergence_at=10,
        silent_divergence_sources=("ausf",),
    )

    benign_features = build_features(simulate_run(benign, seed=0, steps=30))
    attack_features = build_features(simulate_run(attack, seed=0, steps=30))

    benign_support = semantic_attack_support(benign_features)
    attack_support = semantic_attack_support(attack_features)

    assert benign_support.max() == 1.0
    assert attack_support.max() == 1.0
    assert (attack_support.iloc[-5:] == 1.0).all()
