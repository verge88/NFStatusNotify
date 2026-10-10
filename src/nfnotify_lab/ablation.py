from __future__ import annotations

import numpy as np
import pandas as pd

from .evaluate import evaluate_all
from .features import build_features


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
    """Hide one telemetry source and recompute every derived feature.

    The input may already contain derived features. Ablation is applied to the
    raw observation columns first, then build_features() overwrites semantic,
    temporal and provenance features. This prevents pre-ablation state from
    leaking through endpoint-change or rolling-window features.
    """
    if name not in ABLATIONS:
        raise ValueError(f"unknown ablation: {name}")

    out = df.copy()
    hidden = set(ABLATIONS[name])

    if "m_nrf" in hidden:
        out["m_nrf"] = 0
        out["nrf_endpoint"] = None
        out["nrf_update_seen"] = np.nan
    if "m_ausf" in hidden:
        out["m_ausf"] = 0
        out["ausf_endpoint"] = None
    if "m_route" in hidden:
        out["m_route"] = 0
        out["route_endpoint"] = None
    if "m_notify" in hidden:
        out["m_notify"] = 0
        out["notify_seen"] = np.nan
        out["notify_subscription_valid"] = np.nan
        out["notify_sender_trusted"] = np.nan

    return build_features(out)


def evaluate_ablations(
    feature_df: pd.DataFrame,
    target_fpr: float = 0.001,
    random_state: int = 0,
) -> pd.DataFrame:
    frames = []
    for name in ABLATIONS:
        result = evaluate_all(
            apply_ablation(feature_df, name),
            target_fpr=target_fpr,
            random_state=random_state,
        )
        result.insert(0, "ablation", name)
        frames.append(result)
    return pd.concat(frames, ignore_index=True)
