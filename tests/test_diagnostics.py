import pandas as pd

from nfnotify_lab.diagnostics import (
    calibration_diagnostics,
    generalization_risk_register,
)
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


def test_calibration_diagnostics_account_for_max_score_ties():
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(6), steps=50)
    features = build_features(raw)

    summary, ties = calibration_diagnostics(
        features,
        target_fpr=0.01,
        random_state=5,
    )

    assert set(summary["detector"]) == {
        "rules",
        "semantic_guard",
        "consensus_guard",
        "isolation_forest",
        "provenance_aware",
        "patef",
    }
    assert (summary["benign_samples"] > 0).all()
    assert (summary["max_score_tie_count"] > 0).all()
    assert (summary["max_score_tie_count"] <= summary["benign_samples"]).all()

    for detector, row in summary.set_index("detector").iterrows():
        detector_ties = ties.loc[ties["detector"] == detector]
        assert int(detector_ties["max_score_ties"].sum()) == int(
            row["max_score_tie_count"]
        )


def test_generalization_risk_register_flags_fpr_excess():
    holdout = pd.DataFrame(
        [
            {
                "detector": "patef",
                "heldout_scenario": "observer_skew",
                "threshold": 0.6,
                "benign_samples": 1000,
                "attack_samples": 0,
                "false_positives": 25,
                "true_positives": 0,
                "fpr": 0.025,
                "recall": float("nan"),
            },
            {
                "detector": "semantic_guard",
                "heldout_scenario": "stable",
                "threshold": 1.0,
                "benign_samples": 1000,
                "attack_samples": 0,
                "false_positives": 0,
                "true_positives": 0,
                "fpr": 0.0,
                "recall": float("nan"),
            },
        ]
    )

    register = generalization_risk_register(holdout, target_fpr=0.001)

    assert list(register["detector"]) == ["patef", "semantic_guard"]
    assert bool(register.iloc[0]["exceeds_target_fpr"])
    assert register.iloc[0]["fpr_ratio_to_target"] == 25.0
    assert not bool(register.iloc[1]["exceeds_target_fpr"])
