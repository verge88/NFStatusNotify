from __future__ import annotations

import pandas as pd

from nfnotify_lab.simulator import Scenario, simulate_dataset
from scripts.source_shift_preregistered import VIEWS, decide, stress_observations


def _raw():
    return simulate_dataset(
        [Scenario("probe", legit_update_at=8, notify_delay=1)],
        seeds=[0, 1],
        steps=45,
    )


def test_lag_is_causal_run_bounded_and_preserves_labels():
    raw = _raw()
    lagged = stress_observations(raw, "ausf_lag4")
    for run_id, group in lagged.groupby("run_id"):
        baseline = raw.loc[raw["run_id"] == run_id].sort_values("t")
        group = group.sort_values("t")
        assert group.iloc[:4]["m_ausf"].eq(0).all()
        assert group.iloc[:4]["ausf_endpoint"].isna().all()
        assert group.loc[group["t"] == 12, "ausf_endpoint"].iloc[0] == "udm-a"
        assert group.loc[group["t"] == 13, "ausf_endpoint"].iloc[0] == "udm-b"
        assert group["attack_active"].tolist() == baseline["attack_active"].tolist()
        assert group["attack_start"].tolist() == baseline["attack_start"].tolist()


def test_burst_masks_only_nrf_observations():
    raw = _raw()
    masked = stress_observations(raw, "nrf_burst3")
    assert masked.loc[masked["t"].between(34, 36), "m_nrf"].eq(0).all()
    assert masked.loc[masked["t"].between(34, 36), "nrf_endpoint"].isna().all()
    assert masked.loc[masked["t"] == 37, "m_nrf"].eq(1).all()
    assert masked["attack_active"].tolist() == raw["attack_active"].tolist()


def test_decision_does_not_credit_gate_only_performance_to_ml():
    rows = []
    for view in VIEWS:
        for name in ("consensus_guard", "patef_gate_only", "patef_learned_only", "patef"):
            rows.append({
                "view": view, "detector": name,
                "pooled_fpr": 0.0, "worst_benign_scenario_fpr": 0.0,
                "pooled_recall": 0.85,
                "detected_attack_runs": 5,
                "median_scenario_detection_delay": 1.0,
            })
    s = pd.DataFrame(rows)
    result = decide(s, 0.001)
    assert result["synthetic_success"] is False
    assert result["stressed_view_recall_gain_at_least_1pp"] is False

    s.loc[(s["view"] == "ausf_lag4") & (s["detector"] == "patef"),
          "pooled_recall"] = 0.87
    assert decide(s, 0.001)["synthetic_success"] is True
    s.loc[(s["view"] == "route_lag4") & (s["detector"] == "patef"),
          "worst_benign_scenario_fpr"] = 0.01
    assert decide(s, 0.001)["synthetic_success"] is False
