"""Exploratory availability-aware deterministic *comparator* to Stage 6.

Added AFTER viewing the locked Stage-6 evaluation. Do not treat this
diagnostic as a preregistered baseline or use it to rejudge H1/H2/H3.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .consensus import (
    SINGLE_SOURCE_PERSISTENCE_STEPS,
    consensus_attack_support,
)


def available_source_consensus_support(x: pd.DataFrame) -> pd.Series:
    """NRF+one available observer can support a persistent discrepancy.

    Retains exact validated original guard on fully observed rows. When only
    AUSF or route can be compared against NRF, wait the same validated
    eight-observation persistence, and apply the existing recovery/transition
    block. When NRF itself is missing, do not infer a benign state or
    manufacture a source comparison; still preserve bad-notify support.
    """
    original = consensus_attack_support(x)
    nrf = x["m_nrf"].fillna(0).gt(0)
    cache = x["prov_nrf_ausf"].fillna(0).gt(0)
    route = x["prov_route"].fillna(0).gt(0)
    only_cache = nrf & cache & ~route
    only_route = nrf & route & ~cache

    cache_ready = (
        only_cache
        & x["delta_nrf_ausf"].fillna(0).gt(0)
        & x["cache_conflict_persist"].fillna(0).ge(
            SINGLE_SOURCE_PERSISTENCE_STEPS
        )
    )
    route_ready = (
        only_route
        & x["delta_route"].fillna(0).gt(0)
        & x["route_conflict_persist"].fillna(0).ge(
            SINGLE_SOURCE_PERSISTENCE_STEPS
        )
    )
    transition = pd.concat([
        x["recovery_active"].fillna(0),
        x["recent_nrf_update_seen_12"].fillna(0),
        x["recent_nrf_endpoint_changed_12"].fillna(0),
    ], axis=1).max(axis=1).gt(0)
    eligible = (cache_ready | route_ready) & ~transition
    partial = eligible.astype(float) * x[
        "evidence_coverage"
    ].fillna(0).clip(0, 1)
    return pd.Series(
        np.maximum(original.to_numpy(float), partial.to_numpy(float)),
        index=x.index,
    )


@dataclass
class AvailableSourceConsensusDetector:
    """Research-only rule baseline; never added to default published runs."""

    def fit(self, x: pd.DataFrame, y: pd.Series | None = None):
        return self

    def score_samples(self, x: pd.DataFrame) -> np.ndarray:
        return available_source_consensus_support(x).to_numpy(float)
