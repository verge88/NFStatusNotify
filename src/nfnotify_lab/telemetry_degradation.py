from __future__ import annotations

import numpy as np
import pandas as pd


DEGRADATION_VARIANTS = (
    "full",
    "no_nrf",
    "no_ausf",
    "no_route",
    "no_notify",
    "nrf_burst_3",
    "ausf_burst_3",
    "route_burst_3",
    "notify_burst_3",
    "nrf_notify_burst_3",
    "ausf_lag_2",
    "ausf_lag_4",
    "route_lag_2",
    "route_lag_4",
    "notify_delay_2",
)


def _transition_heads(df: pd.DataFrame, width: int) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    for _, run in df.groupby("run_id", sort=False):
        ordered = run.sort_values("t")
        previous_phase: object | None = None
        for phase, phase_rows in ordered.groupby("phase", sort=False):
            if previous_phase is not None:
                idx = phase_rows.index[:width]
                mask.loc[idx] = True
            previous_phase = phase
    return mask


def _hide_source(df: pd.DataFrame, source: str, mask: pd.Series | None = None) -> None:
    if mask is None:
        mask = pd.Series(True, index=df.index)
    if source == "nrf":
        df.loc[mask, "nrf_endpoint"] = np.nan
        df.loc[mask, "nrf_update_seen"] = np.nan
        df.loc[mask, "m_nrf"] = 0
    elif source == "ausf":
        df.loc[mask, "ausf_endpoint"] = np.nan
        df.loc[mask, "m_ausf"] = 0
    elif source == "route":
        df.loc[mask, "route_endpoint"] = np.nan
        df.loc[mask, "m_route"] = 0
    elif source == "notify":
        df.loc[mask, "notify_seen"] = np.nan
        df.loc[mask, "notify_subscription_valid"] = np.nan
        df.loc[mask, "notify_sender_trusted"] = np.nan
        df.loc[mask, "m_notify"] = 0
    else:
        raise ValueError(f"unknown telemetry source: {source}")


def _lag_endpoint(df: pd.DataFrame, column: str, width: int) -> None:
    for _, run in df.groupby("run_id", sort=False):
        ordered = run.sort_values("t")
        phases = list(ordered["phase"].drop_duplicates())
        for phase_index in range(1, len(phases)):
            phase = phases[phase_index]
            phase_rows = ordered.loc[ordered["phase"] == phase]
            prior = ordered.loc[ordered["t"] < phase_rows["t"].min(), column].dropna()
            if prior.empty:
                continue
            stale_value = prior.iloc[-1]
            df.loc[phase_rows.index[:width], column] = stale_value


def _delay_notify(df: pd.DataFrame, steps: int) -> None:
    columns = (
        "notify_seen",
        "notify_subscription_valid",
        "notify_sender_trusted",
    )
    for _, run in df.groupby("run_id", sort=False):
        ordered = run.sort_values("t")
        for column in columns:
            shifted = ordered[column].shift(steps)
            # A delayed but available benign channel emits "no notification"
            # until the original trusted event becomes visible.
            if column == "notify_seen":
                shifted = shifted.fillna(0.0)
            else:
                shifted = shifted.fillna(1.0)
            df.loc[ordered.index, column] = shifted.to_numpy()
        df.loc[ordered.index, "m_notify"] = 1


def apply_degradation(observations: pd.DataFrame, variant: str) -> pd.DataFrame:
    """Create a benign observer-degradation view of a real trace.

    The underlying NRF/AUSF/UDM execution is unchanged. Only the telemetry view
    supplied to the detector is masked or delayed.
    """
    if variant not in DEGRADATION_VARIANTS:
        raise ValueError(f"unknown degradation variant: {variant}")

    out = observations.copy().sort_values(["run_id", "t"]).reset_index(drop=True)
    out["scenario"] = f"{out['scenario'].astype(str)}__{variant}"
    out["attack_active"] = 0
    out["attack_start"] = -1
    if "label" in out.columns:
        out["label"] = 0

    if variant == "full":
        return out

    if variant.startswith("no_"):
        _hide_source(out, variant.removeprefix("no_"))
        return out

    transition_mask = _transition_heads(out, width=3)
    if variant == "nrf_burst_3":
        _hide_source(out, "nrf", transition_mask)
    elif variant == "ausf_burst_3":
        _hide_source(out, "ausf", transition_mask)
    elif variant == "route_burst_3":
        _hide_source(out, "route", transition_mask)
    elif variant == "notify_burst_3":
        _hide_source(out, "notify", transition_mask)
    elif variant == "nrf_notify_burst_3":
        _hide_source(out, "nrf", transition_mask)
        _hide_source(out, "notify", transition_mask)
    elif variant == "ausf_lag_2":
        _lag_endpoint(out, "ausf_endpoint", 2)
    elif variant == "ausf_lag_4":
        _lag_endpoint(out, "ausf_endpoint", 4)
    elif variant == "route_lag_2":
        _lag_endpoint(out, "route_endpoint", 2)
    elif variant == "route_lag_4":
        _lag_endpoint(out, "route_endpoint", 4)
    elif variant == "notify_delay_2":
        _delay_notify(out, 2)
    else:
        raise AssertionError(variant)

    return out
