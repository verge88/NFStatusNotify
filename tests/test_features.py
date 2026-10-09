import numpy as np

from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import Scenario, simulate_run


def test_forged_notify_creates_state_contradiction():
    df = simulate_run(Scenario("attack", attack=True, forged_notify_at=10), seed=1, steps=20)
    feat = build_features(df)
    row = feat.loc[feat["t"] == 10].iloc[0]
    assert row["delta_nrf_ausf"] == 1.0
    assert row["delta_route"] == 1.0
    assert row["delta_notify"] == 1.0


def test_missing_nrf_produces_unknown_not_false_consistency():
    scenario = Scenario(
        "missing",
        attack=True,
        forged_notify_at=5,
        missing_sources=("nrf",),
        missing_probability=1.0,
    )
    feat = build_features(simulate_run(scenario, seed=2, steps=12))
    assert feat["m_nrf"].eq(0).all()
    assert np.isnan(feat["delta_nrf_ausf"]).all()
    assert np.isnan(feat["delta_route"]).all()
