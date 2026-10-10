import numpy as np

from nfnotify_lab.evaluate import (
    evaluate_scenario_holdout,
    summarize_scenario_holdout,
)
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


def test_scenario_holdout_never_trains_on_heldout_scenario():
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(8), steps=60)
    features = build_features(raw)
    holdout = evaluate_scenario_holdout(
        features,
        target_fpr=0.02,
        random_state=17,
        calibration_fraction=0.25,
    )

    assert set(holdout["detector"]) == {
        "rules",
        "isolation_forest",
        "provenance_aware",
        "patef",
    }
    assert set(holdout["heldout_scenario"]) == {
        scenario.name for scenario in DEFAULT_SCENARIOS
    }

    for row in holdout.itertuples(index=False):
        assert row.heldout_scenario not in row.train_scenarios.split(",")

    summary = summarize_scenario_holdout(holdout)
    patef = summary.loc[summary["detector"] == "patef"].iloc[0]
    assert patef["heldout_scenarios"] == len(DEFAULT_SCENARIOS)
    assert np.isfinite(patef["unseen_scenario_fpr"])
    assert np.isfinite(patef["unseen_attack_recall"])
    assert patef["attack_samples"] > 0
    assert patef["benign_samples"] > 0
