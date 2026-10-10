from __future__ import annotations

import numpy as np
import pandas as pd


TEMPORAL_WINDOWS = (3, 6, 12)
TRANSITION_GRACE_STEPS = 12


def _persistence(series: pd.Series) -> pd.Series:
    values = series.fillna(0.0).to_numpy()
    out = np.zeros(len(values), dtype=float)
    count = 0
    for i, value in enumerate(values):
        count = count + 1 if value > 0 else 0
        out[i] = count
    return pd.Series(out, index=series.index)


def _since_event(series: pd.Series, cap: int = 25) -> pd.Series:
    values = series.fillna(0.0).to_numpy()
    out: list[float] = []
    elapsed = cap
    for value in values:
        elapsed = 0 if value > 0 else min(elapsed + 1, cap)
        out.append(float(elapsed))
    return pd.Series(out, index=series.index)


def _observed_change(series: pd.Series) -> pd.Series:
    """Detect a value change across the last two *observed* samples.

    Missing telemetry does not reset the remembered value. If an NRF update
    event is lost while the endpoint observation is missing, the first later
    observation of the new endpoint still records a transition.
    """
    out: list[float] = []
    previous: object | None = None
    seen = False
    for value in series:
        if pd.isna(value):
            out.append(float("nan"))
            continue
        changed = float(seen and value != previous)
        out.append(changed)
        previous = value
        seen = True
    return pd.Series(out, index=series.index)


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add temporal/provenance features without crossing run boundaries."""
    out = df.copy().sort_values(["run_id", "t"]).reset_index(drop=True)

    out["trusted_notify_seen"] = (
        out["notify_seen"].fillna(0.0)
        * out["notify_sender_trusted"].fillna(0.0)
        * out["notify_subscription_valid"].fillna(0.0)
    )
    out["bad_notify_seen"] = out["delta_notify"].fillna(0.0)
    out["nrf_endpoint_changed"] = out.groupby("run_id", sort=False)[
        "nrf_endpoint"
    ].transform(_observed_change)

    state_pair = out[["delta_nrf_ausf", "delta_route"]]
    out["state_conflict"] = state_pair.max(axis=1, skipna=True)
    out.loc[state_pair.isna().all(axis=1), "state_conflict"] = np.nan

    cache_pair_available = out["prov_nrf_ausf"].fillna(0.0) > 0
    route_pair_available = out["prov_route"].fillna(0.0) > 0
    out["state_pair_available_count"] = (
        cache_pair_available.astype(float) + route_pair_available.astype(float)
    )
    cache_conflict = (
        out["delta_nrf_ausf"].fillna(0.0) * cache_pair_available.astype(float)
    )
    route_conflict = (
        out["delta_route"].fillna(0.0) * route_pair_available.astype(float)
    )
    out["conflict_source_count"] = cache_conflict + route_conflict
    complete_state_view = out["state_pair_available_count"] == 2.0
    out["single_source_conflict"] = (
        complete_state_view & out["conflict_source_count"].eq(1.0)
    ).astype(float)
    out["dual_source_conflict"] = (
        complete_state_view & out["conflict_source_count"].eq(2.0)
    ).astype(float)

    age_available = {
        source: out[f"{source}_age_steps"].notna()
        & out[f"m_{source}"].fillna(0.0).astype(float).gt(0.0)
        for source in ("nrf", "ausf", "route")
    }
    available_state_sources = (
        out["m_nrf"].fillna(0.0).astype(float)
        + out["m_ausf"].fillna(0.0).astype(float)
        + out["m_route"].fillna(0.0).astype(float)
    )
    known_age_sources = sum(mask.astype(float) for mask in age_available.values())
    out["freshness_coverage"] = (
        known_age_sources / available_state_sources.replace(0.0, np.nan)
    ).fillna(0.0)

    cache_age_known = age_available["nrf"] & age_available["ausf"]
    route_age_known = age_available["nrf"] & age_available["route"]
    cache_pair_age = pd.concat(
        [out["nrf_age_steps"], out["ausf_age_steps"]], axis=1
    ).max(axis=1, skipna=False)
    route_pair_age = pd.concat(
        [out["nrf_age_steps"], out["route_age_steps"]], axis=1
    ).max(axis=1, skipna=False)

    cache_conflict = out["delta_nrf_ausf"].fillna(0.0).gt(0.0)
    route_conflict = out["delta_route"].fillna(0.0).gt(0.0)
    out["fresh_conflict_source_count"] = (
        (cache_conflict & cache_age_known & cache_pair_age.eq(0.0)).astype(float)
        + (route_conflict & route_age_known & route_pair_age.eq(0.0)).astype(float)
    )
    out["stale_conflict_source_count"] = (
        (cache_conflict & cache_age_known & cache_pair_age.gt(0.0)).astype(float)
        + (route_conflict & route_age_known & route_pair_age.gt(0.0)).astype(float)
    )
    known_conflict_age_count = (
        (cache_conflict & cache_age_known).astype(float)
        + (route_conflict & route_age_known).astype(float)
    )
    out["unknown_freshness_conflict_source_count"] = (
        out["conflict_source_count"] - known_conflict_age_count
    ).clip(lower=0.0)
    conflict_denominator = out["conflict_source_count"].replace(0.0, np.nan)
    out["fresh_conflict_fraction"] = (
        out["fresh_conflict_source_count"] / conflict_denominator
    ).fillna(0.0)
    out["stale_conflict_fraction"] = (
        out["stale_conflict_source_count"] / conflict_denominator
    ).fillna(0.0)
    out["unknown_freshness_conflict_fraction"] = (
        out["unknown_freshness_conflict_source_count"] / conflict_denominator
    ).fillna(0.0)
    out["max_state_age_steps"] = pd.concat(
        [out["nrf_age_steps"], out["ausf_age_steps"], out["route_age_steps"]],
        axis=1,
    ).max(axis=1, skipna=True)
    out.loc[
        ~pd.concat(
            [age_available["nrf"], age_available["ausf"], age_available["route"]],
            axis=1,
        ).any(axis=1),
        "max_state_age_steps",
    ] = np.nan

    rolling_columns = (
        "delta_nrf_ausf",
        "delta_route",
        "delta_notify",
        "delta_time",
        "state_conflict",
        "conflict_source_count",
        "single_source_conflict",
        "dual_source_conflict",
        "fresh_conflict_source_count",
        "stale_conflict_source_count",
        "unknown_freshness_conflict_source_count",
        "fresh_conflict_fraction",
        "stale_conflict_fraction",
        "freshness_coverage",
        "recovery_active",
        "obs_fraction",
    )
    for column in rolling_columns:
        grouped = out.groupby("run_id", sort=False)[column]
        for window in TEMPORAL_WINDOWS:
            out[f"{column}_mean_{window}"] = grouped.transform(
                lambda s, w=window: s.rolling(w, min_periods=1).mean()
            )
            out[f"{column}_max_{window}"] = grouped.transform(
                lambda s, w=window: s.rolling(w, min_periods=1).max()
            )

    for column in (
        "nrf_update_seen",
        "notify_seen",
        "trusted_notify_seen",
        "bad_notify_seen",
    ):
        out[f"recent_{column}_6"] = out.groupby("run_id", sort=False)[column].transform(
            lambda s: s.fillna(0.0).rolling(6, min_periods=1).max()
        )

    out["recent_nrf_update_seen_12"] = out.groupby("run_id", sort=False)[
        "nrf_update_seen"
    ].transform(
        lambda s: s.fillna(0.0).rolling(TRANSITION_GRACE_STEPS, min_periods=1).max()
    )
    out["recent_nrf_endpoint_changed_12"] = out.groupby("run_id", sort=False)[
        "nrf_endpoint_changed"
    ].transform(
        lambda s: s.fillna(0.0).rolling(TRANSITION_GRACE_STEPS, min_periods=1).max()
    )

    out["state_conflict_persist"] = out.groupby("run_id", sort=False)[
        "state_conflict"
    ].transform(_persistence)
    out["route_conflict_persist"] = out.groupby("run_id", sort=False)[
        "delta_route"
    ].transform(_persistence)
    out["cache_conflict_persist"] = out.groupby("run_id", sort=False)[
        "delta_nrf_ausf"
    ].transform(_persistence)
    out["single_source_conflict_persist"] = out.groupby("run_id", sort=False)[
        "single_source_conflict"
    ].transform(_persistence)
    out["dual_source_conflict_persist"] = out.groupby("run_id", sort=False)[
        "dual_source_conflict"
    ].transform(_persistence)
    out["fresh_conflict_persist"] = out.groupby("run_id", sort=False)[
        "fresh_conflict_source_count"
    ].transform(_persistence)
    out["stale_conflict_persist"] = out.groupby("run_id", sort=False)[
        "stale_conflict_source_count"
    ].transform(_persistence)

    out["since_nrf_update"] = out.groupby("run_id", sort=False)[
        "nrf_update_seen"
    ].transform(_since_event)
    out["since_nrf_endpoint_change"] = out.groupby("run_id", sort=False)[
        "nrf_endpoint_changed"
    ].transform(_since_event)
    out["since_notify"] = out.groupby("run_id", sort=False)["notify_seen"].transform(
        _since_event
    )

    observed_transition = np.maximum(
        out["recent_nrf_update_seen_12"].fillna(0.0),
        out["recent_nrf_endpoint_changed_12"].fillna(0.0),
    )
    out["unexplained_conflict"] = (
        out["state_conflict"].fillna(0.0) * (1.0 - observed_transition)
    )
    out["trusted_transition"] = np.maximum(
        observed_transition,
        out["recent_trusted_notify_seen_6"].fillna(0.0),
    ) * (1.0 - out["bad_notify_seen"].fillna(0.0))

    out["evidence_coverage"] = (
        0.35 * out["prov_nrf_ausf"].fillna(0.0)
        + 0.25 * out["prov_route"].fillna(0.0)
        + 0.20 * out["prov_notify"].fillna(0.0)
        + 0.20 * out["obs_fraction"].fillna(0.0)
    )
    return out
