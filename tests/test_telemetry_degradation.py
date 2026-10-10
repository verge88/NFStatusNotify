import numpy as np
import pandas as pd

from nfnotify_lab.telemetry_degradation import (
    DEGRADATION_VARIANTS,
    apply_degradation,
)


def _real_like_trace() -> pd.DataFrame:
    phases = ["baseline"] * 2 + ["failover"] * 5 + ["recovery"] * 3
    nrf = ["a", "a"] + ["b"] * 5 + ["a"] * 3
    ausf = list(nrf)
    route = list(nrf)
    notify_seen = [0, 0, 1, 0, 0, 0, 0, 1, 0, 0]
    return pd.DataFrame(
        {
            "run_id": ["real-0"] * 10,
            "scenario": ["real_legitimate_udm_failover"] * 10,
            "seed": [0] * 10,
            "t": list(range(10)),
            "phase": phases,
            "label": [0] * 10,
            "attack_active": [0] * 10,
            "attack_start": [-1] * 10,
            "nrf_endpoint": nrf,
            "ausf_endpoint": ausf,
            "route_endpoint": route,
            "nrf_update_seen": [0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
            "notify_seen": notify_seen,
            "notify_subscription_valid": [1] * 10,
            "notify_sender_trusted": [1] * 10,
            "recovery_active": [0] * 10,
            "m_nrf": [1] * 10,
            "m_ausf": [1] * 10,
            "m_route": [1] * 10,
            "m_notify": [1] * 10,
        }
    )


def test_all_degradation_views_remain_benign():
    raw = _real_like_trace()
    for variant in DEGRADATION_VARIANTS:
        degraded = apply_degradation(raw, variant)
        assert not degraded["attack_active"].astype(bool).any()
        assert (degraded["attack_start"] == -1).all()
        assert degraded["scenario"].str.endswith(f"__{variant}").all()


def test_source_loss_masks_values_and_provenance():
    raw = _real_like_trace()
    degraded = apply_degradation(raw, "no_route")
    assert degraded["route_endpoint"].isna().all()
    assert (degraded["m_route"] == 0).all()

    burst = apply_degradation(raw, "nrf_burst_3")
    assert int((burst["m_nrf"] == 0).sum()) == 6
    assert burst.loc[burst["m_nrf"] == 0, "nrf_endpoint"].isna().all()


def test_observer_lag_creates_only_transient_single_source_skew():
    raw = _real_like_trace()
    lagged = apply_degradation(raw, "ausf_lag_2")

    failover = lagged.loc[lagged["phase"] == "failover"]
    assert list(failover["ausf_endpoint"].iloc[:2]) == ["a", "a"]
    assert failover["ausf_endpoint"].iloc[2] == "b"

    recovery = lagged.loc[lagged["phase"] == "recovery"]
    assert list(recovery["ausf_endpoint"].iloc[:2]) == ["b", "b"]
    assert recovery["ausf_endpoint"].iloc[2] == "a"


def test_notify_delay_keeps_channel_trusted_and_available():
    raw = _real_like_trace()
    delayed = apply_degradation(raw, "notify_delay_2")
    assert (delayed["m_notify"] == 1).all()
    assert set(delayed["notify_sender_trusted"].astype(int)) == {1}
    assert set(delayed["notify_subscription_valid"].astype(int)) == {1}
    assert np.isfinite(delayed["notify_seen"]).all()
