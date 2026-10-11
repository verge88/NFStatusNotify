"""Experimental causal source ages for simulator-origin metadata only.

Real Stage-5 Open5GS poll completion/log/pcap times are NOT valid substitutes
for the simulator's same-unit source capture ticks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import build_features
from .freshness import attach_acquisition_times, observed_view

SOURCE_MASK_COLUMNS = ("m_nrf", "m_ausf", "m_route", "m_notify")
SOURCE_COLUMNS = {
    "nrf": ("nrf_endpoint", "nrf_update_seen", "m_nrf"),
    "ausf": ("ausf_endpoint", "m_ausf"),
    "route": ("route_endpoint", "m_route"),
    "notify": (
        "notify_seen", "notify_subscription_valid", "notify_sender_trusted",
        "m_notify",
    ),
}
FRESHNESS_FEATURES = tuple(
    f"age_{name}" for name in SOURCE_COLUMNS
) + tuple(f"age_{name}_missing" for name in SOURCE_COLUMNS)


def with_causal_source_ages(frame: pd.DataFrame) -> pd.DataFrame:
    """Age is unknown, *not* zero, if a capture tick is missing or in future."""
    out = frame.copy()
    for source, columns in SOURCE_COLUMNS.items():
        origin = pd.to_numeric(
            out.get(f"{source}_origin_t", pd.Series(np.nan, index=out.index)),
            errors="coerce",
        )
        mask = out[columns[-1]].fillna(0).eq(1)
        valid = mask & origin.notna() & origin.le(out["t"]) & origin.ge(0)
        age = (out["t"] - origin).clip(0, 25).where(valid, np.nan)
        out[f"age_{source}"] = age.astype(float)
        out[f"age_{source}_missing"] = (~valid).astype(float)
    return out


def hide_source(frame: pd.DataFrame, source: str) -> None:
    """Hide endpoint/event/capture timestamp consistently, never labels."""
    columns = SOURCE_COLUMNS[source]
    for name in columns[:-1]:
        frame[name] = np.nan
    frame[columns[-1]] = 0
    frame[f"{source}_origin_t"] = np.nan


def make_view(
    observations: pd.DataFrame,
    view: str,
    *,
    dropout_sources: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Fresh simulation observer view, no alteration to ground-truth labels."""
    clocked = attach_acquisition_times(observations)
    if view in ("original", "route_lag4", "both_lag2", "route_lag8", "ausf_lag4"):
        changed = observed_view(clocked, view)
    elif view.startswith("no_"):
        changed = observed_view(clocked, "original")
        hide_source(changed, view.removeprefix("no_"))
    else:
        raise ValueError(f"unknown source view: {view}")
    for source in dropout_sources:
        hide_source(changed, source)
    enriched = with_causal_source_ages(changed)
    return build_features(enriched)


def availability_mask(x: pd.DataFrame) -> np.ndarray:
    """4-bit observed mask, not scenario label or attack ground truth."""
    return (
        x[list(SOURCE_MASK_COLUMNS)]
        .fillna(0.0).gt(0.0).astype(int).astype(str)
        .agg("".join, axis=1).to_numpy(dtype=str)
    )


def age_stats(frame: pd.DataFrame) -> dict[str, int]:
    return {
        source: int(frame[f"age_{source}_missing"].sum())
        for source in SOURCE_COLUMNS
    }
