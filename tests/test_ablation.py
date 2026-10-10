import numpy as np

from nfnotify_lab.ablation import apply_ablation
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


def test_no_nrf_ablation_recomputes_temporal_features_without_endpoint_leak():
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(2), steps=60)
    features = build_features(raw)

    ablated = apply_ablation(features, "no_nrf")

    assert (ablated["m_nrf"] == 0).all()
    assert ablated["nrf_endpoint"].isna().all()
    assert ablated["nrf_update_seen"].isna().all()
    assert ablated["delta_nrf_ausf"].isna().all()
    assert ablated["delta_route"].isna().all()
    assert ablated["nrf_endpoint_changed"].isna().all()
    assert (ablated["recent_nrf_endpoint_changed_12"] == 0).all()
    assert (ablated["recent_nrf_update_seen_12"] == 0).all()


def test_no_notify_ablation_keeps_missing_notify_as_unknown_not_consistent():
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(2), steps=60)
    features = build_features(raw)

    ablated = apply_ablation(features, "no_notify")

    assert (ablated["m_notify"] == 0).all()
    assert ablated["notify_seen"].isna().all()
    assert ablated["notify_subscription_valid"].isna().all()
    assert ablated["notify_sender_trusted"].isna().all()
    assert ablated["delta_notify"].isna().all()
    assert (ablated["recent_bad_notify_seen_6"] == 0).all()
    assert np.isfinite(ablated["obs_fraction"]).all()
