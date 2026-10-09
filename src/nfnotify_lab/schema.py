from __future__ import annotations

import pandas as pd


REQUIRED_OBSERVATION_COLUMNS = {
    "run_id",
    "scenario",
    "seed",
    "t",
    "attack_active",
    "attack_start",
    "nrf_endpoint",
    "ausf_endpoint",
    "route_endpoint",
    "nrf_update_seen",
    "notify_seen",
    "notify_subscription_valid",
    "notify_sender_trusted",
    "recovery_active",
    "m_nrf",
    "m_ausf",
    "m_route",
    "m_notify",
}


def validate_observations(df: pd.DataFrame) -> pd.DataFrame:
    """Validate the semantic observation contract used by the feature pipeline."""
    missing = sorted(REQUIRED_OBSERVATION_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"missing required observation columns: {', '.join(missing)}")

    if df.duplicated(["run_id", "t"]).any():
        raise ValueError("duplicate (run_id, t) observations are not allowed")

    for column in ("m_nrf", "m_ausf", "m_route", "m_notify", "recovery_active", "attack_active"):
        values = set(df[column].dropna().astype(int).unique())
        if not values.issubset({0, 1}):
            raise ValueError(f"{column} must contain only 0/1 values")

    if (df["t"] < 0).any():
        raise ValueError("t must be non-negative")

    return df.sort_values(["run_id", "t"]).reset_index(drop=True)
