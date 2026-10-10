from __future__ import annotations

import numpy as np
import pandas as pd


SINGLE_SOURCE_PERSISTENCE_STEPS = 12
DUAL_SOURCE_PERSISTENCE_STEPS = 2


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

    The default operating point remains dual=2 / single=12. Parameters are
    exposed so publication-time sensitivity analysis can evaluate the trade-off
    without modifying detector code or using real-test labels for tuning.
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
