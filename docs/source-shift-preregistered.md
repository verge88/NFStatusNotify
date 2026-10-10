# Locked source-shift experiment: PA-TEF v2 versus causal gate

**Protocol locked before the stress workflow is executed.**
Parent: `research/patef-v3-soft-gate` (PR #21). This is an exploratory branch, not a replacement for `main` or the publication freeze. No real attack messages are sent.

## Primary question and estimand

Does **learned fusion add classification value beyond its exact provenance-normalized gate** under previously unseen scenario type and observation-time skew, when both use the **same unmodified training/calibration sets and a common FPR budget**?

Detectors: `consensus_guard`, `patef_gate_only`, `patef_learned_only` (no consensus meta-feature), and complete `patef`. The gate-only / full contrast is primary; other baselines are diagnostic.

## Data partition and provenance

- Original simulator `DEFAULT_SCENARIOS`: 12 scenarios × 60 fixed seeds (0..59) × 90 steps.
- Leave-one-scenario-out evaluation with `_split_scenario_holdout`: all runs of that scenario are test only. No run_id is shared with training or calibration.
- Fixed `random_state=42`, calibration fraction 0.25, target FPR 0.001.
- Fit each detector **once per scenario fold** on the pristine training set; model calibration and alert threshold come only from the pristine held-in-scenario calibration set. Then reuse that same fitted model and threshold on every stress view of the held-out scenario. NO re-training or re-calibration on stressed/held-out test data.
- The test labels, run IDs, attack onset, scenario names and `recovery_active` stay unchanged. Observation transformations act only on the test observer streams; recompute all semantic and temporal features after transformation with `build_features` to avoid temporal/feature leakage.
- Per source, delayed readings use **past** values (`shift(+lag)`) within run_id. Leading missing samples have mask 0/NaN, not a duplicated future value. Do not use `bfill`.

## Fixed stress views (no tuning)

1. `original`: original heldout sample streams.
2. `ausf_lag4`: delay AUSF endpoint and its availability mask by 4 samples.
3. `route_lag4`: delay route endpoint and mask by 4 samples.
4. `both_lag2`: delay AUSF and route endpoints/masks by 2 samples.
5. `notify_lag2`: delay notification presence, subscription-valid and sender-trust with mask by 2 samples.
6. `nrf_burst3`: mask NRF endpoint and update signal for t in [34,36], reflecting a three-sample point failure near change onset.

The masks and timestamps must remain causal. The fixed attack onset at t=35 is from the simulator; it is not an input to either detector.

## Reporting and decision rule

For each (view, scenario, detector): benign samples, attack samples, FP, TP, FPR, recall, episode coverage, median delay, and thresholds. Aggregate *counts* across scenarios separately from worst-scenario FPR. Include full-vs-gate deltas. Treat views of one run as correlated: they are not independent replicates.

**Success only if all hold:**
1. For **every view**, full PA-TEF has pooled test FPR <=0.001 **and** worst individual benign-scenario FPR <=0.001.
2. For **every view**, full PA-TEF has attack recall no lower than gate-only and no greater median detection delay.
3. In at least one of the five stressed views, full PA-TEF gains >=0.01 absolute attack recall over gate-only, without reducing attack-run detection rate.
4. A new independent real Open5GS benign A→B→A failover run reports **zero** alerts for full PA-TEF (and report every baseline including cases that failed).

Otherwise the outcome is **negative/inconclusive**: do not claim ML classification superiority or promote to main. Pointwise zero FPR on finite correlated test data is not a population upper bound.

## External laboratory boundary

Real Open5GS v2.7.7 runs are **benign** failover/recovery controls. An attack-like check may freeze the reference NRF view on a recorded trace to construct an offline counterfactual *post-effect*. The study does **not** transmit forged `NFStatusNotify` exploit payload. Results must distinguish synthetic attack, real benign and real-derived counterfactual. Never select hyperparameters on the external real traces.

## Reproducibility

Commit this protocol before adding implementation/workflow, retain tool versions, exact head SHA, model thresholds, per-fold CSVs, aggregate JSON and GitHub Actions run/artifact identifiers. Failed tests and negative results are valid research outcomes; no automatic merge.
