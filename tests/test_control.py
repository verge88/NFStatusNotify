import json

import pytest

from nfnotify_lab.control import score_benign_control
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
