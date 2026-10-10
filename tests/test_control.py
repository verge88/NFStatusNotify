import json

from nfnotify_lab.control import score_benign_control
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_run


def test_semantic_guard_external_control_writes_detector_specific_artifacts(tmp_path):
    raw = simulate_run(DEFAULT_SCENARIOS[0], seed=0, steps=20)
    features = build_features(raw)

    summary = score_benign_control(
        features,
        out_dir=tmp_path,
        target_fpr=0.01,
        random_state=3,
        training_seeds=6,
        steps=30,
        detector_name="semantic_guard",
    )

    assert summary["detector"] == "semantic_guard"
    assert summary["alerts"] == 0
    assert (tmp_path / "control-scores-semantic_guard.csv").exists()
    summary_path = tmp_path / "control-summary-semantic_guard.json"
    assert summary_path.exists()
    written = json.loads(summary_path.read_text())
    assert written["detector"] == "semantic_guard"
    assert not (tmp_path / "control-summary.json").exists()
