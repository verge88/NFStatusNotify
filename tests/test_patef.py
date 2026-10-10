import pandas as pd

from nfnotify_lab.evaluate import evaluate_all
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


def test_patef_detects_forged_notify_at_low_fpr():
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(12), steps=65)
    features = build_features(raw)
    metrics = evaluate_all(features, target_fpr=0.02, random_state=11)
    patef = metrics.loc[metrics["detector"] == "patef"].iloc[0]

    assert patef["fpr"] <= 0.03
    assert patef["recall_at_target_fpr"] >= 0.90
    assert patef["pr_auc"] >= 0.95


def test_temporal_features_do_not_cross_runs():
    raw = simulate_dataset(DEFAULT_SCENARIOS[:2], seeds=range(2), steps=10)
    features = build_features(raw)

    first_rows = features.groupby("run_id", sort=False).head(1)
    assert (first_rows["state_conflict_persist"] == 0).all()
    assert (first_rows["since_notify"] >= 0).all()
    assert isinstance(features, pd.DataFrame)
