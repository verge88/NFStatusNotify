# Scenario-disjoint evaluation

The default run-level split prevents individual simulated runs from leaking across
train, calibration, and test partitions, but it still allows the same scenario
template to appear in every partition. That is useful for measuring repeatability,
but it can overstate generalization when a detector learns scenario-specific
signatures.

The scenario-disjoint protocol therefore holds out one complete scenario at a
time. The held-out scenario contributes no rows to either training or threshold
calibration. Every remaining scenario is split by `run_id` into training and
calibration subsets, so calibration still operates on independent runs.

For each detector and held-out scenario the harness reports:

- empirical FPR on benign windows;
- recall on attack-active windows when the held-out scenario contains an attack;
- ROC-AUC and PR-AUC when both classes exist in the held-out scenario;
- per-run detection delay and detected-run counts;
- the number of training, calibration, and held-out runs.

The summary pools false positives and true positives across the mutually
exclusive held-out folds and also reports the worst scenario FPR and the minimum
recall across held-out attack scenarios.

Run the protocol with:

```bash
nfnotify-lab all --config configs/patef-benchmark.yaml --out artifacts/patef-benchmark
```

The resulting files are `scenario-holdout.csv` and
`scenario-holdout-summary.csv`.

This protocol is deliberately separate from the real Open5GS benign controls.
Real controls establish that legitimate NRF/AUSF/route transitions do not
produce alerts; scenario-disjoint simulation tests whether the detector
generalizes beyond a scenario template it saw during training. Neither result by
itself is sufficient evidence of production robustness.
