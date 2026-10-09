from __future__ import annotations

import pandas as pd

from .evaluate import evaluate_all


ABLATIONS = {
    "full": (),
    "no_nrf": ("m_nrf", "nrf_endpoint", "nrf_update_seen"),
    "no_ausf": ("m_ausf", "ausf_endpoint"),
    "no_route": ("m_route", "route_endpoint"),
    "no_notify": (
        "m_notify",
        "notify_seen",
        "notify_subscription_valid",
        "notify_sender_trusted",
    ),
}


def apply_ablation(df: pd.DataFrame, name: str) -> pd.DataFrame:
    if name not in ABLATIONS:
        raise ValueError(f"unknown ablation: {name}")
    out = df.copy()
    hidden = set(ABLATIONS[name])

    if "m_nrf" in hidden:
        out["m_nrf"] = 0
        out["delta_nrf_ausf"] = float("nan")
        out["delta_route"] = float("nan")
        out["prov_nrf_ausf"] = 0
        out["prov_route"] = 0
    if "m_ausf" in hidden:
        out["m_ausf"] = 0
        out["delta_nrf_ausf"] = float("nan")
        out["prov_nrf_ausf"] = 0
    if "m_route" in hidden:
        out["m_route"] = 0
        out["delta_route"] = float("nan")
        out["prov_route"] = 0
    if "m_notify" in hidden:
        out["m_notify"] = 0
        out["delta_notify"] = float("nan")
        out["prov_notify"] = 0

    out["obs_fraction"] = out[["m_nrf", "m_ausf", "m_route", "m_notify"]].mean(axis=1)
    return out


def evaluate_ablations(feature_df: pd.DataFrame, target_fpr: float = 0.001) -> pd.DataFrame:
    frames = []
    for name in ABLATIONS:
        result = evaluate_all(apply_ablation(feature_df, name), target_fpr=target_fpr)
        result.insert(0, "ablation", name)
        frames.append(result)
    return pd.concat(frames, ignore_index=True)
