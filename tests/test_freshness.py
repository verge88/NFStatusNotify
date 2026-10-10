from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nfnotify_lab.features import build_features
from nfnotify_lab.freshness import (
    aligned_features,
    attach_acquisition_times,
    observed_view,
)
from nfnotify_lab.simulator import Scenario, simulate_dataset


def _sample():
    return simulate_dataset(
        [Scenario("healthy", legit_update_at=35, notify_delay=1)],
        seeds=range(2),
        steps=55,
    )


def test_original_alignment_is_pointwise_equivalent():
    clock = attach_acquisition_times(_sample())
    original = build_features(clock)
    aligned = aligned_features(clock)
    for column in ("delta_nrf_ausf", "delta_route", "prov_nrf_ausf", "prov_route"):
        np.testing.assert_allclose(
            original[column].to_numpy(float),
            aligned[column].to_numpy(float),
            equal_nan=True,
        )


def test_route_lag_compares_only_recorded_contemporaneous_nrf():
    clock = attach_acquisition_times(_sample())
    lagged = observed_view(clock, "route_lag4")
    original = build_features(lagged)
    aligned = aligned_features(lagged)
    for run_id in lagged["run_id"].unique():
        observation = lagged.loc[
            (lagged["run_id"] == run_id) & (lagged["t"] == 38)
        ].index[0]
        assert lagged.loc[observation, "route_origin_t"] == 34
        assert original.loc[observation, "delta_route"] == 1.0
        assert aligned.loc[observation, "delta_route"] == 0.0


def test_missing_past_nrf_never_imputed_as_consistent():
    clock = attach_acquisition_times(_sample())
    lagged = observed_view(clock, "route_lag4")
    lagged.loc[lagged["t"].eq(34), [
        "nrf_endpoint", "nrf_update_seen", "nrf_origin_t"
    ]] = np.nan
    lagged.loc[lagged["t"].eq(34), "m_nrf"] = 0
    corrected = aligned_features(lagged)
    # At t=38, the route snapshot is from t=34; that NRF tick is missing.
    missing = corrected["t"].eq(38)
    assert corrected.loc[missing, "delta_route"].isna().all()
    assert corrected.loc[missing, "prov_route"].eq(0).all()


def test_jitter_uses_only_past_observation_and_no_cross_run():
    clock = attach_acquisition_times(_sample())
    lagged = observed_view(clock, "route_jitter2_6")
    for _, group in lagged.groupby("run_id"):
        assert group.loc[group["t"].eq(10), "route_origin_t"].iloc[0] == 8
        assert group.loc[group["t"].eq(11), "route_origin_t"].iloc[0] == 5
        valid = group["route_origin_t"].notna()
        assert (
            group.loc[valid, "route_origin_t"] <= group.loc[valid, "t"]
        ).all()
        assert group["attack_active"].eq(0).all()


def test_future_provenance_is_rejected_and_missing_clock_is_an_error():
    source = attach_acquisition_times(_sample())
    source.loc[source["t"].eq(20), "route_origin_t"] = 45
    aligned = aligned_features(source)
    assert aligned.loc[aligned["t"].eq(20), "prov_route"].eq(0).all()
    assert aligned.loc[aligned["t"].eq(20), "delta_route"].isna().all()
    with pytest.raises(ValueError, match="acquisition metadata"):
        aligned_features(source.drop(columns="route_origin_t"))


def test_metadata_fields_are_separate_from_attack_labels():
    source = attach_acquisition_times(_sample())
    for view in ("original", "ausf_lag4", "route_lag4", "both_lag2",
                 "notify_lag2", "nrf_burst3", "route_lag8", "route_jitter2_6"):
        observed = observed_view(source, view)
        assert observed["run_id"].equals(source["run_id"])
        assert observed["attack_active"].equals(source["attack_active"])
        assert observed["attack_start"].equals(source["attack_start"])
        assert pd.notna(observed["t"]).all()
