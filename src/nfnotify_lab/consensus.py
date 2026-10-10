from __future__ import annotations

import numpy as np
import pandas as pd


# Historical conservative reference used before the preregistered candidate
# validation. Kept explicitly for reproducibility of published comparisons.
REFERENCE_SINGLE_SOURCE_PERSISTENCE_STEPS = 12
REFERENCE_DUAL_SOURCE_PERSISTENCE_STEPS = 2

# Current validated operating point. Selected on development-only sensitivity
# run 38058210231, then independently validated on eight fresh Open5GS runs in
# 38060262689 before promotion.
SINGLE_SOURCE_PERSISTENCE_STEPS = 8
DUAL_SOURCE_PERSISTENCE_STEPS = 1


def consensus_attack_support(
    x: pd.DataFrame,
    *,
    single_source_steps: int = SINGLE_SOURCE_PERSISTENCE_STEPS,
    dual_source_steps: int = DUAL_SOURCE_PERSISTENCE_STEPS,
) -> pd.Series:
    """Deterministic provenance-consensus evidence.

    A bad/untrusted notification is strong evidence immediately. State
    divergence is treated differently by source multiplicity:

    - disagreement confirmed by both AUSF-cache and actual route needs a short
      persistence window;
    - disagreement seen in only one independent observer needs a longer
      persistence window before it is considered suspicious.

    The validated default is dual=1 / single=8. The historical conservative
    reference dual=2 / single=12 remains available through explicit parameters
    and named constants for reproducibility.
    """
    if single_source_steps < 1 or dual_source_steps < 1:
        raise ValueError("persistence steps must be >= 1")

    bad_notify = x["recent_bad_notify_seen_6"].fillna(0.0).clip(0.0, 1.0)
    recovery = x["recovery_active"].fillna(0.0).clip(0.0, 1.0)
    observed_transition = pd.concat(
        [
            x["recent_nrf_update_seen_12"].fillna(0.0),
            x["recent_nrf_endpoint_changed_12"].fillna(0.0),
        ],
        axis=1,
    ).max(axis=1)
    transition_block = np.maximum(recovery, observed_transition)
    coverage = x["evidence_coverage"].fillna(0.0).clip(0.0, 1.0)

    dual_ready = (
        x["dual_source_conflict_persist"].fillna(0.0) >= dual_source_steps
    ).astype(float)
    single_ready = (
        x["single_source_conflict_persist"].fillna(0.0) >= single_source_steps
    ).astype(float)
    conflict_ready = np.maximum(dual_ready, single_ready)

    state_support = conflict_ready * (1.0 - transition_block) * coverage
    temporal_support = (
        x["delta_time"].fillna(0.0)
        * (1.0 - transition_block)
        * coverage
        * conflict_ready
    )

    return pd.concat(
        [bad_notify, state_support, temporal_support],
        axis=1,
    ).max(axis=1).clip(0.0, 1.0)
