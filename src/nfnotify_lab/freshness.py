"""Experimental oracle event-time provenance, NOT production Open5GS telemetry.

Each synthetic observation carries a trusted source-acquisition *logical tick*.
Only a snapshot observed at that exact tick may be used as an NRF comparator.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features import build_features
from .temporal import add_temporal_features


EVENTTIME_VIEWS = (
    "original",
    "ausf_lag4",
    "route_lag4",
    "both_lag2",
    "notify_lag2",
    "nrf_burst3",
    "route_lag8",
    "route_jitter2_6",
)
SOURCE_COLUMNS = {
    "nrf": ("nrf_endpoint", "nrf_update_seen", "m_nrf"),
    "ausf": ("ausf_endpoint", "m_ausf"),
    "route": ("route_endpoint", "m_route"),
    "notify": (
        "notify_seen",
        "notify_subscription_valid",
        "notify_sender_trusted",
        "m_notify",
    ),
}


def attach_acquisition_times(observations: pd.DataFrame) -> pd.DataFrame:
    """Attach per-source acquisition ticks to an independently observed stream.

    In a real deployment these must come from authenticated source metadata.
    Deriving source timestamps from this simulator is a *known synthetic oracle*.
    """
    out = observations.sort_values(["run_id", "t"]).reset_index(drop=True).copy()
    for source, columns in SOURCE_COLUMNS.items():
        mask = out[columns[-1]].fillna(0.0).eq(1.0)
        out[f"{source}_origin_t"] = out["t"].where(mask, np.nan).astype(float)
    return out


def _delay(out: pd.DataFrame, source: str, lag: int | None = None) -> None:
    columns = (*SOURCE_COLUMNS[source], f"{source}_origin_t")
    if lag is not None:
        for column in columns:
            out[column] = out.groupby("run_id", sort=False)[column].shift(lag)
    else:
        # Variable lag is decided solely by observation tick, not labels.
        result = pd.DataFrame(index=out.index, columns=columns)
        for _, indices in out.groupby("run_id", sort=False).groups.items():
            group = out.loc[indices].sort_values("t")
            lookup = group.set_index("t")
            for idx, row in group.iterrows():
                lag_at_t = 2 if int(row["t"]) % 2 == 0 else 6
                observed_tick = row["t"] - lag_at_t
                if observed_tick in lookup.index:
                    earlier = lookup.loc[observed_tick, list(columns)]
                    result.loc[idx, list(columns)] = earlier.to_numpy()
        for column in columns:
            out[column] = result[column]
    mask = SOURCE_COLUMNS[source][-1]
    out[mask] = pd.to_numeric(out[mask], errors="coerce").fillna(0).astype(int)
    out.loc[out[mask].eq(0), f"{source}_origin_t"] = np.nan
    for column in SOURCE_COLUMNS[source][:-1]:
        out.loc[out[mask].eq(0), column] = np.nan


def observed_view(source_timed: pd.DataFrame, view: str) -> pd.DataFrame:
    """Return a frozen, source-clocked view without touching attack labels."""
    if view not in EVENTTIME_VIEWS:
        raise ValueError(f"unknown source-clock view: {view}")
    out = source_timed.sort_values(["run_id", "t"]).reset_index(drop=True).copy()
    if view == "ausf_lag4":
        _delay(out, "ausf", 4)
    elif view == "route_lag4":
        _delay(out, "route", 4)
    elif view == "both_lag2":
        _delay(out, "ausf", 2)
        _delay(out, "route", 2)
    elif view == "notify_lag2":
        _delay(out, "notify", 2)
    elif view == "route_lag8":
        _delay(out, "route", 8)
    elif view == "route_jitter2_6":
        _delay(out, "route", None)
    elif view == "nrf_burst3":
        missing = out["t"].between(34, 36)
        for column in SOURCE_COLUMNS["nrf"][:-1]:
            out.loc[missing, column] = np.nan
        out.loc[missing, "m_nrf"] = 0
        out.loc[missing, "nrf_origin_t"] = np.nan
    return out


def _different(a: object, b: object) -> float:
    if pd.isna(a) or pd.isna(b):
        return float("nan")
    return float(a != b)


def aligned_features(source_timed_view: pd.DataFrame) -> pd.DataFrame:
    """Compare each AUSF/route snapshot to NRF at its *same observed tick*.

    NRF history is constructed causally, run by run. No extrapolation over a
    missing NRF sample, no future read, and no cross-run carryover are allowed.
    Only the two comparison deltas and their provenance masks are replaced.
    """
    original = source_timed_view.sort_values(["run_id", "t"]).reset_index(drop=True)
    features = build_features(original)
    for column in ("nrf_origin_t", "ausf_origin_t", "route_origin_t"):
        if column not in original:
            raise ValueError(f"absent trusted acquisition metadata: {column}")

    cache_delta = np.full(len(original), np.nan, dtype=float)
    route_delta = np.full(len(original), np.nan, dtype=float)
    cache_provenance = np.zeros(len(original), dtype=float)
    route_provenance = np.zeros(len(original), dtype=float)

    for _, indices in original.groupby("run_id", sort=False).groups.items():
        history: dict[int, object] = {}
        for idx in indices:
            row = original.loc[idx]
            now = int(row["t"])
            nrf_tick = row["nrf_origin_t"]
            if (
                row["m_nrf"] == 1
                and pd.notna(nrf_tick)
                and int(nrf_tick) <= now
                and pd.notna(row["nrf_endpoint"])
            ):
                history[int(nrf_tick)] = row["nrf_endpoint"]

            for source, endpoint, mask, dst, prov in (
                ("ausf", "ausf_endpoint", "m_ausf", cache_delta, cache_provenance),
                ("route", "route_endpoint", "m_route", route_delta, route_provenance),
            ):
                tick = row[f"{source}_origin_t"]
                if (
                    row[mask] != 1
                    or pd.isna(tick)
                    or int(tick) > now
                    or int(tick) not in history
                ):
                    continue
                comparison = _different(history[int(tick)], row[endpoint])
                if np.isfinite(comparison):
                    dst[idx] = comparison
                    prov[idx] = 1.0

    features["delta_nrf_ausf"] = cache_delta
    features["delta_route"] = route_delta
    features["prov_nrf_ausf"] = cache_provenance
    features["prov_route"] = route_provenance
    return add_temporal_features(features)
