# Locked source-shift experiment: observed results (negative ML increment)

Protocol committed **before** implementation: [source-shift-preregistered.md](source-shift-preregistered.md), commit `4e8565e85038fef68e6381ff65f97cd3ddc410d5`.

Synthetic GitHub Actions [run 38075859698](https://github.com/verge88/NFStatusNotify/actions/runs/38075859698), artifact ID `11678815494`, successful; no changes to evaluation criteria after observing the results. The experiment was run on the **synthetic** 12-scenario 60-seed 90-step benchmark, with held-out scenario classes and fixed pristine calibration.

## Per-view pooled metrics

| View | Gate-only recall | Full PA-TEF recall | Full FPR | Worst benign scenario FPR | Full-minus-gate recall | Median full delay |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| original | 0.956364 | 0.956364 | 0 | 0 | 0 | 0 |
| ausf_lag4 | 0.917818 | 0.917818 | 0 | 0 | 0 | 4 |
| route_lag4 | 0.917818 | 0.917818 | 0.004969 | 0.044444 | 0 | 4 |
| both_lag2 | 0.929818 | 0.920000 | 0.002484 | 0.022222 | -0.009818 | 2 |
| notify_lag2 | 0.956364 | 0.956364 | 0 | 0 | 0 | 0 |
| nrf_burst3 | 0.929818 | 0.920000 | 0 | 0 | -0.009818 | 2 |

For each view the sample counts were 48,300 benign and 16,500 attack-active; attack-run detection was 300/300 for the four compared detectors. **Attack-run coverage is not pointwise recall.** Counts rather than scenario-wise percentage averages determine pooled rates. The six views reuse the same underlying traces and are correlated.

The `consensus_guard` baseline had original FPR 0, recall 0.949091; under `route_lag4`, FPR 0.004969, recall 0.910545; under `both_lag2`, FPR 0.002484, recall 0.922545. Therefore the observer-lag failure is not isolated to one particular ML model.

The `patef_learned_only` model (no decision gate and no consensus-support meta-feature) exhibited FPR 0.026087 and worst FPR 0.10 in the pristine holdout (recall 0.956364), and FPR 0.012422 for `nrf_burst3`. It does not meet the 0.001 budget.

## Locked decision

From `source-shift-decision.json`:
- `synthetic_all_views_fpr_pass = false`;
- `synthetic_all_views_no_recall_loss = false`;
- `synthetic_all_views_no_delay_loss = true`;
- `synthetic_all_views_no_episode_loss = true`;
- `stressed_view_recall_gain_at_least_1pp = false`;
- `synthetic_success = false`.

**Negative outcome:** Full PA-TEF did not achieve prespecified incremental classification value beyond gate-only. In two views its Recall was lower; in two lagged views its FPR exceeded budget. No hyperparameter or threshold may be tuned to this held-out result and then reported as an independent test.

## Scientific interpretation

The external observations are time-indexed but were not equipped with explicit independently observed capture-time/snapshot freshness. A delayed route observer can create a sustained *apparent* disagreement with a more recent NRF state. A syntactically valid discrepancy cannot automatically distinguish a stale reader from an unexpected state change. This is a failure of provenance temporal semantics, not evidence that simply widening the gate helps; the earlier soft-gate sweep failed that test.

Future development should collect trustworthy observation timestamp, source-time, poll age and update causality metadata, introduce a purely deterministic freshness-aware baseline, and only then test whether ML adds discrimination under **fresh** domain-disjoint validation. The real Open5GS control validates benign operation in its defined topology, not real forged-notification exploit detection.

## Evidence and reproducibility

- Script: `scripts/source_shift_preregistered.py` (causal source delay; feature recomputation per held-out run).
- Report artifacts: `source-shift-folds.csv`, `source-shift-summary.csv`, `source-shift-decision.json`.
- Environment/source via workflow run and exact head commit.
- Independent real Open5GS workflow: [run 38075878889](https://github.com/verge88/NFStatusNotify/actions/runs/38075878889) (status to be recorded independently; synthetic failure already definitive for preregistered superiority).
- No forged NFStatusNotify payload was sent. The underlying real-control traffic is benign UDM failover and the attack-like trace is an offline counterfactual post-effect.

Publication `main` and frozen evidence registry are unchanged.
