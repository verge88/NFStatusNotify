from nfnotify_lab.evaluate import evaluate_all
from nfnotify_lab.features import build_features
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


def test_end_to_end_smoke():
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=range(10), steps=60)
    features = build_features(raw)
    result = evaluate_all(features, target_fpr=0.01, random_state=7)
    assert set(result["detector"]) == {
        "rules",
        "isolation_forest",
        "provenance_aware",
        "patef",
    }
    assert result["fpr"].notna().all()
    assert result["recall_at_target_fpr"].notna().all()
    assert result["roc_auc"].notna().all()
    assert result["pr_auc"].notna().all()
