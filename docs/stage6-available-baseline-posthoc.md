# Post-hoc Stage 6 availability-aware deterministic comparator

**Exploratory and NOT part of the preregistered Stage 6 H1/H2/H3.** This comparator was proposed and implemented **after** inspecting the first Stage 6 heldout score table. It therefore cannot independently validate a learning advantage or change the locked H1/H2/H3 verdict.

## Why this comparator matters

The original `consensus_guard` requires two state-observer comparisons to reach its source multiplicity persistence signal. With `no_ausf` or `no_route`, one of these comparisons disappears; the original deterministic guard then often **abstains** rather than treating a persistent remaining NRF-vs-route or NRF-vs-AUSF discrepancy as attack evidence. A hybrid OR with PA-TEF will therefore appear to gain many points versus an *underpowered* partial-source baseline. This is a methodological confound noted by the user.

The new opt-in `available_source_consensus_support` retains the exact established consensus signal, and additionally allows a single independent surviving AUSF or Route observer with **observed NRF reference**, when its discrepancy persists at least the already validated **8 samples**, without recovery/authorized NRF-transition explanations. **Missing NRF does not create a state alert.** This is a development-only comparator, not a candidate promoted to production, and its eight-sample rule has not been freshly tuned on the heldout challenge.

## Reproducibility

- [Post-hoc workflow 38127741227](https://github.com/verge88/NFStatusNotify/actions/runs/38127741227), success, five comparator tests passed and Ruff success.
- [Artifact 11696969411](https://github.com/verge88/NFStatusNotify/actions/runs/38127741227/artifacts/11696969411): `available-baseline-by-scenario.csv`, `available-baseline-summary.csv`, `available-baseline-decision.json`.
- Dataset was **the same previously revealed** six new synthetic scenarios / 24 test seeds 300..323 / 90 observations / seven views as Stage 6. **It is no longer an untouched heldout set for this comparator**. No new real packets were sent.

| Source view | Original consensus Recall/FPR | Stronger available-source rule Recall/FPR | Full age/dropout hybrid Recall/FPR from first Stage 6 computed summary |
| --- | --- | --- | --- |
| no_ausf | 0% / 0% | **62.0690% / 0%** | **63.2184% / 0%** |
| no_route | 0% / 0% | **55.7471% / 0.8197%** | **56.8966% / 1.0929%** |
| no_nrf | 0% / 0% | 0% / 0% | 0% / 0% |
| original | 91.9540% / 0.8197% | unchanged | unchanged |
| route_lag4 | 87.3563% / 1.9126% | unchanged | unchanged |
| route_lag8 | 83.3333% / 3.0055% | unchanged | unchanged |

**Interpretation:** no-AUSF raw claimed ML advantage versus original abstaining rule (~63pp) collapses to **1.1494 percentage points** over an equally available-information deterministic eight-step persistence rule. In no-route the same modest 1.1494pp added recall comes with worse FPR: 0.8197% => 1.0929%. Neither case demonstrates a safe low-FPR learned-fusion superiority on novel benign skew. No threshold selection or test feedback from this diagnostic may affect the preregistered Stage 6 model.

This fairness comparator also shows why an unqualified claim that `patef_residual_guard` uniquely rescues missing-source detection would be misleading. A prospective new challenge with independently unseen source-unavailability families is required for future claims.
