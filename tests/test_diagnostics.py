from nfnotify_lab.diagnostics import (
    calibration_diagnostics,
    generalization_risk_register,
)
from nfnotify_lab.evaluate import evaluate_scenario_holdout
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


def test_calibration_diagnostics_account_for_max_score_ties():
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(8), steps=60)
    features = build_features(raw)

    summary, ties = calibration_diagnostics(
        features,
        target_fpr=0.01,
        random_state=5,
    )

    assert set(summary["detector"]) == {
        "rules",
        "semantic_guard",
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
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(6), steps=60)
    features = build_features(raw)
    holdout = evaluate_scenario_holdout(
        features,
        target_fpr=0.02,
        random_state=9,
        calibration_fraction=0.25,
    )

    register = generalization_risk_register(holdout, target_fpr=0.02)

    assert len(register) > 0
    assert {
        "detector",
        "heldout_scenario",
        "fpr",
        "fpr_excess",
        "fpr_ratio_to_target",
        "exceeds_target_fpr",
    }.issubset(register.columns)
    assert (
        register["exceeds_target_fpr"]
        == (register["fpr"] > register["target_fpr"])
    ).all()
