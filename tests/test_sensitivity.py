import numpy as np

from nfnotify_lab.features import build_features
from nfnotify_lab.sensitivity import ConsensusGrid, evaluate_consensus_grid, pareto_frontier
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


def test_consensus_sensitivity_reports_reference_without_real_data():
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(4), steps=55)
    features = build_features(raw)
    run_split, holdout = evaluate_consensus_grid(
        features,
        target_fpr=0.02,
        random_state=7,
        grid=ConsensusGrid(
            single_source_steps=(6, 12),
            dual_source_steps=(1, 2),
        ),
    )

    assert len(run_split) == 4
    assert len(holdout) == 4
    reference = holdout.loc[holdout["is_reference_2_12"]]
    assert len(reference) == 1
    assert int(reference.iloc[0]["single_source_steps"]) == 12
    assert int(reference.iloc[0]["dual_source_steps"]) == 2
    assert np.isfinite(reference.iloc[0]["unseen_scenario_fpr"])
    assert np.isfinite(reference.iloc[0]["unseen_attack_recall"])

    frontier = pareto_frontier(holdout)
    assert len(frontier) >= 1
    assert set(frontier.columns) == set(holdout.columns)
