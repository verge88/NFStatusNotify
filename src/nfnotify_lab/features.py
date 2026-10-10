from __future__ import annotations

import numpy as np
import pandas as pd

from .temporal import add_temporal_features


MODEL_FEATURES = [
    "delta_nrf_ausf",
    "delta_route",
    "delta_notify",
    "delta_time",
    "recovery_active",
    "m_nrf",
    "m_ausf",
    "m_route",
    "m_notify",
    "obs_fraction",
    "prov_nrf_ausf",
    "prov_route",
    "prov_notify",
]


def _neq(a: object, b: object) -> float:
    if pd.isna(a) or pd.isna(b):
        return np.nan
    return float(a != b)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build semantic, temporal and provenance features per run."""
    out = df.copy().sort_values(["run_id", "t"]).reset_index(drop=True)

    out["delta_nrf_ausf"] = [
        _neq(a, b) for a, b in zip(out["nrf_endpoint"], out["ausf_endpoint"], strict=False)
    ]
    out["delta_route"] = [
        _neq(a, b) for a, b in zip(out["nrf_endpoint"], out["route_endpoint"], strict=False)
    ]

    notify_seen = out["notify_seen"].fillna(0.0)
    invalid_subscription = 1.0 - out["notify_subscription_valid"].fillna(1.0)
    untrusted_sender = 1.0 - out["notify_sender_trusted"].fillna(1.0)
    notify_conflict = notify_seen * np.maximum(invalid_subscription, untrusted_sender)
    out["delta_notify"] = notify_conflict.where(out["m_notify"].fillna(0) > 0, np.nan)

    prev_cache = out.groupby("run_id")["ausf_endpoint"].shift()
    has_pair = out["ausf_endpoint"].notna() & prev_cache.notna()
    cache_changed = np.where(
        has_pair,
        out["ausf_endpoint"].ne(prev_cache).astype(float),
        np.nan,
    )
    first_in_run = out.groupby("run_id").cumcount().eq(0)
    out["cache_changed"] = cache_changed
    out.loc[first_in_run, "cache_changed"] = 0.0

    recent_update = (
        out.groupby("run_id")["nrf_update_seen"]
        .transform(lambda s: s.fillna(0).rolling(6, min_periods=1).max())
        .astype(float)
    )
    out["delta_time"] = out["cache_changed"] * (1.0 - recent_update)

    out["obs_fraction"] = out[["m_nrf", "m_ausf", "m_route", "m_notify"]].mean(axis=1)
    out["prov_nrf_ausf"] = out["m_nrf"] * out["m_ausf"]
    out["prov_route"] = out["m_nrf"] * out["m_route"]
    out["prov_notify"] = out["m_notify"]

    return add_temporal_features(out)


def model_matrix(feature_df: pd.DataFrame) -> pd.DataFrame:
    return feature_df[MODEL_FEATURES].astype(float)
