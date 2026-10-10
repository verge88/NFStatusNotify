from pathlib import Path

import pandas as pd
import yaml

from nfnotify_lab.consensus import consensus_attack_support


def _base_features(rows: int = 12) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "recent_bad_notify_seen_6": [0.0] * rows,
            "recovery_active": [0.0] * rows,
            "recent_nrf_update_seen_12": [0.0] * rows,
            "recent_nrf_endpoint_changed_12": [0.0] * rows,
            "evidence_coverage": [1.0] * rows,
            "dual_source_conflict_persist": list(range(1, rows + 1)),
            "single_source_conflict_persist": [0.0] * rows,
            "delta_time": [0.0] * rows,
        }
    )


def test_frozen_candidate_is_locked_and_development_selected():
    config = yaml.safe_load(Path("configs/consensus-candidate.yaml").read_text())
    assert config["selection"]["locked"] is True
    assert config["selection"]["development_run_id"] == 38058210231
    assert config["selection"]["real_attack_like_validation_used_for_selection"] is False
    assert config["reference"]["single_source_steps"] == 12
    assert config["reference"]["dual_source_steps"] == 2
    assert config["candidate"]["single_source_steps"] == 8
    assert config["candidate"]["dual_source_steps"] == 1


def test_candidate_detects_dual_conflict_one_sample_before_reference():
    features = _base_features(rows=4)

    reference = consensus_attack_support(
        features,
        single_source_steps=12,
        dual_source_steps=2,
    )
    candidate = consensus_attack_support(
        features,
        single_source_steps=8,
        dual_source_steps=1,
    )

    assert reference.iloc[0] == 0.0
    assert reference.iloc[1] == 1.0
    assert candidate.iloc[0] == 1.0


def test_candidate_single_source_gate_opens_at_eight_not_twelve():
    features = _base_features(rows=12)
    features["dual_source_conflict_persist"] = 0.0
    features["single_source_conflict_persist"] = list(range(1, 13))

    reference = consensus_attack_support(
        features,
        single_source_steps=12,
        dual_source_steps=2,
    )
    candidate = consensus_attack_support(
        features,
        single_source_steps=8,
        dual_source_steps=1,
    )

    assert candidate.iloc[6] == 0.0
    assert candidate.iloc[7] == 1.0
    assert reference.iloc[10] == 0.0
    assert reference.iloc[11] == 1.0
