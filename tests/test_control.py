import json

import pandas as pd
import pytest

from nfnotify_lab.control import score_benign_control, summarize_external_replay
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_run


@pytest.mark.parametrize("detector_name", ["semantic_guard", "consensus_guard"])
def test_deterministic_external_control_writes_detector_specific_artifacts(
    tmp_path, detector_name
):
    raw = simulate_run(DEFAULT_SCENARIOS[0], seed=0, steps=20)
    features = build_features(raw)

    summary = score_benign_control(
        features,
        out_dir=tmp_path,
        target_fpr=0.01,
        random_state=3,
        training_seeds=6,
        steps=30,
        detector_name=detector_name,
    )

    assert summary["detector"] == detector_name
    assert summary["alerts"] == 0
    assert (tmp_path / f"control-scores-{detector_name}.csv").exists()
    summary_path = tmp_path / f"control-summary-{detector_name}.json"
    assert summary_path.exists()
    written = json.loads(summary_path.read_text())
    assert written["detector"] == detector_name
    assert not (tmp_path / "control-summary.json").exists()


def test_external_replay_separates_sample_recall_from_run_detection():
    observations = pd.DataFrame(
        {
            "run_id": ["r1"] * 7,
            "t": list(range(7)),
            "attack_start": [2] * 7,
            "attack_active": [0, 0, 1, 1, 1, 1, 1],
        }
    )
    scores = pd.DataFrame(
        {"alert": [False, False, False, True, True, True, True]}
    )
    summary = {
        "target_fpr": 0.001,
        "threshold": 0.1,
        "max_risk": 0.75,
    }

    result = summarize_external_replay(
        "consensus_guard", observations, scores, summary
    )

    assert result["recall"] == 0.8
    assert result["fpr"] == 0.0
    assert result["detected_attack_runs"] == 1
    assert result["total_attack_runs"] == 1
    assert result["attack_run_detection_rate"] == 1.0
    assert result["median_detection_delay"] == 1.0
    assert not result["meets_external_target"]
    assert result["meets_run_detection_target"]
