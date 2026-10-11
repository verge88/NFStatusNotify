from __future__ import annotations

import numpy as np

from nfnotify_lab.available_consensus import available_source_consensus_support
from nfnotify_lab.consensus import consensus_attack_support
from nfnotify_lab.residual_freshness import make_view
from nfnotify_lab.simulator import Scenario, simulate_run


def test_full_observation_identical_to_validated_consensus():
    raw = simulate_run(
        Scenario(
            "dual", attack=True, silent_divergence_at=15,
            silent_divergence_sources=("ausf", "route"),
        ),
        seed=10, steps=45,
    )
    frame = make_view(raw, "original")
    assert np.array_equal(
        available_source_consensus_support(frame),
        consensus_attack_support(frame),
    )


def test_no_nrf_abstains_from_state_decision():
    raw = simulate_run(
        Scenario(
            "route", attack=True, silent_divergence_at=12,
            silent_divergence_sources=("route",),
        ),
        seed=1, steps=30,
    )
    frame = make_view(raw, "no_nrf")
    assert available_source_consensus_support(frame).eq(0).all()


def test_eight_persistent_single_observer_conflicts_after_mask():
    raw = simulate_run(
        Scenario(
            "route", attack=True, silent_divergence_at=12,
            silent_divergence_sources=("route",),
        ),
        seed=1, steps=31,
    )
    frame = make_view(raw, "no_ausf")
    scores = available_source_consensus_support(frame)
    assert scores.loc[frame["t"].eq(18)].eq(0).all()
    assert scores.loc[frame["t"].eq(19)].gt(0).all()
    assert consensus_attack_support(frame).eq(0).all()


def test_short_benign_skew_abstains():
    raw = simulate_run(
        Scenario(
            "benign_short_skew", observer_skew_at=12,
            observer_skew_duration=4, observer_skew_sources=("route",),
        ),
        seed=1, steps=30,
    )
    frame = make_view(raw, "no_ausf")
    assert available_source_consensus_support(frame).eq(0).all()


def test_partial_detector_never_removes_original_alerts():
    raw = simulate_run(
        Scenario(
            "forged", attack=True, forged_notify_at=15,
        ),
        seed=1, steps=30,
    )
    frame = make_view(raw, "no_ausf")
    old = consensus_attack_support(frame).gt(0)
    new = available_source_consensus_support(frame).gt(0)
    assert not (old & ~new).any()
