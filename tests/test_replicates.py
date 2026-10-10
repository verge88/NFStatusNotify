import json

import pandas as pd

from nfnotify_lab.replicates import (
    bootstrap_interval,
    collect_replicates,
    numeric_summary,
    proportion_summary,
    study_summary,
    wilson_interval,
)


def _write_replicate(root, replicate_id, consensus_recall, delay):
    run = root / f"open5gs-replicate-{replicate_id}"
    (run / "real").mkdir(parents=True)
    (run / "counterfactual").mkdir(parents=True)

    result = {
        "replicate_id": replicate_id,
        "target_fpr": 0.001,
        "semantic_guard": {
            "detector": "semantic_guard",
            "attack_samples": 5,
            "attack_alerts": 0,
            "benign_samples": 6,
            "benign_alerts": 0,
            "recall": 0.0,
            "fpr": 0.0,
            "threshold": 1.0,
            "max_risk": 0.75,
            "meets_external_target": False,
            "detected_attack_runs": 0,
            "total_attack_runs": 1,
            "attack_run_detection_rate": 0.0,
            "median_detection_delay": None,
            "meets_run_detection_target": False,
        },
        "consensus_guard": {
            "detector": "consensus_guard",
            "attack_samples": 5,
            "attack_alerts": int(round(5 * consensus_recall)),
            "benign_samples": 6,
            "benign_alerts": 0,
            "recall": consensus_recall,
            "fpr": 0.0,
            "threshold": 0.01,
            "max_risk": 0.75,
            "meets_external_target": consensus_recall == 1.0,
            "detected_attack_runs": 1,
            "total_attack_runs": 1,
            "attack_run_detection_rate": 1.0,
            "median_detection_delay": delay,
            "meets_run_detection_target": True,
        },
        "patef": {
            "detector": "patef",
            "attack_samples": 5,
            "attack_alerts": 0,
            "benign_samples": 6,
            "benign_alerts": 0,
            "recall": 0.0,
            "fpr": 0.0,
            "threshold": 0.75,
            "max_risk": 0.74,
            "meets_external_target": False,
            "detected_attack_runs": 0,
            "total_attack_runs": 1,
            "attack_run_detection_rate": 0.0,
            "median_detection_delay": None,
            "meets_run_detection_target": False,
        },
    }
    (run / "counterfactual-result.json").write_text(json.dumps(result))
    (run / "failover-meta.json").write_text(
        json.dumps(
            {
                "replicate_id": replicate_id,
                "udm_a_instance_id": f"a-{replicate_id}",
                "udm_b_instance_id": f"b-{replicate_id}",
                "phase_epochs": {
                    "baseline_start": 0.0,
                    "failover_start": 10.0,
                    "recovery_start": 20.0 + replicate_id,
                    "experiment_end": 30.0 + replicate_id,
                },
            }
        )
    )
    (run / "evidence-summary.json").write_text(
        json.dumps({"cache_events": [{}, {}, {}]})
    )
    (run / "notifications.tsv").write_text("header\nrow\nrow\n")
    (run / "routes.tsv").write_text("header\nrow\nrow\nrow\n")

    for detector in ("semantic_guard", "consensus_guard", "patef"):
        (run / "real" / f"control-summary-{detector}.json").write_text(
            json.dumps({"alerts": 0, "max_risk": 0.0})
        )


def test_replicate_statistics_and_intervals(tmp_path):
    for replicate_id, recall, delay in (
        (0, 0.8, 1.0),
        (1, 1.0, 0.0),
        (2, 0.8, 1.0),
    ):
        _write_replicate(tmp_path, replicate_id, recall, delay)

    detector_df, infra_df = collect_replicates(tmp_path)
    assert detector_df["replicate_id"].nunique() == 3
    assert infra_df["replicate_id"].nunique() == 3

    consensus = detector_df.loc[detector_df["detector"] == "consensus_guard"]
    assert consensus["real_benign_alerts"].eq(0).all()
    assert consensus["attack_run_detection_rate"].eq(1.0).all()

    stats = numeric_summary(detector_df)
    recall_stats = stats.loc[
        (stats["detector"] == "consensus_guard") & (stats["metric"] == "recall")
    ].iloc[0]
    assert recall_stats["n"] == 3
    assert 0.8 <= recall_stats["mean"] <= 1.0
    assert recall_stats["bootstrap_mean_ci_low"] <= recall_stats["mean"]
    assert recall_stats["bootstrap_mean_ci_high"] >= recall_stats["mean"]

    proportions = proportion_summary(detector_df)
    run_detection = proportions.loc[
        (proportions["detector"] == "consensus_guard")
        & (proportions["metric"] == "attack_run_detected")
    ].iloc[0]
    assert run_detection["successes"] == 3
    assert run_detection["proportion"] == 1.0
    assert 0.0 < run_detection["wilson_95_ci_low"] < 1.0

    summary = study_summary(detector_df, infra_df, requested_replicates=8)
    assert summary["valid_replicates"] == 3
    assert summary["detectors"]["consensus_guard"]["run_detection_target_runs"] == 3


def test_interval_helpers_are_deterministic():
    values = pd.Series([0.8, 0.8, 1.0, 0.8]).to_numpy()
    first = bootstrap_interval(values, random_state=7)
    second = bootstrap_interval(values, random_state=7)
    assert first == second
    assert first[0] <= values.mean() <= first[1]

    low, high = wilson_interval(8, 8)
    assert 0.0 < low < 1.0
    assert high == 1.0
