# Event-time freshness experiment: locked evaluation, negative outcome

**Status:** finished, negative. The fixed protocol was committed **before any code or experimental job** at `e51ca959f6835cc5509a49a22e28ac23e40efb5b`. The protocol is [freshness-eventtime-protocol.md](freshness-eventtime-protocol.md). This is an exploratory synthetic *oracle source-timestamp* experiment on reused scenario classes, NOT field validation and NOT an updated publication claim.

## Reproducibility and evidence

- [Event-time benchmark run 38076969650](https://github.com/verge88/NFStatusNotify/actions/runs/38076969650), success.
- [Complete source-time benchmark artifact 11678477802](https://github.com/verge88/NFStatusNotify/actions/runs/38076969650/artifacts/11678477802): `freshness-folds.csv`, `freshness-summary.csv`, `freshness-decision.json`, `study-config.json`.
- [Full CI 38076969620](https://github.com/verge88/NFStatusNotify/actions/runs/38076969620), success.
- Train/calibration seeds 0..59, heldout test seeds **100..139**, 12 scenario classes x 90 observations; leave-one-scenario-out training/calibration, frozen target FPR 0.001.
- For every view 32,200 benign and 11,000 attack-positive test samples. Exactly 200 attacking test runs were available per view (five attack scenario classes x 40 seeds). The views of each underlying run are NOT statistically independent.

## Deterministic gate-only: aligned versus unaligned

| View | Original FPR | Aligned FPR | Worst aligned benign FPR | Original Recall | Aligned Recall | Aligned median delay (samples) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| original | 0 | 0 | 0 | 0.956364 | 0.956364 | 0 |
| ausf_lag4 | 0 | 0 | 0 | 0.916727 | 0.916727 | 4 |
| route_lag4 | 0.004969 | 0.004969 | 0.044444 | 0.916727 | 0.916727 | 4 |
| both_lag2 | 0.002484 | 0.002484 | 0.022222 | 0.929273 | 0.929273 | 2 |
| notify_lag2 | 0 | 0 | 0 | 0.956364 | 0.956364 | 0 |
| nrf_burst3 | 0 | 0 | 0 | 0.929273 | 0.929273 | 2 |
| route_lag8 | 0.012422 | **0.014907** | 0.088889 | 0.889636 | 0.889636 | 6 |
| route_jitter2_6 | 0.003727 | 0.003727 | 0.033333 | 0.913091 | 0.913091 | 3 |

Notably, the aligned deterministic gate retained 160 false-positive points in route_lag4 (160/32,200), 80 in both_lag2, and **480 vs 400** unaligned in route_lag8. No precommitted false-positive reduction was achieved. However the same sample recall and detected-episode coverage remained. `freshness_success_on_synthetic_oracle=false`, `freshness_all_fpr_budgets_pass=false`, `freshness_prespecified_fp_improvement=false`.

In route_lag4, the worst individual held-out benign scenario had FPR 4.4444%, and in route_lag8 the worst had FPR 8.8889%. The actual population FPR for other 5G implementations is not estimated by these synthetic counts.

## Learned-fusion counterfactual and baselines

The aligned full PA-TEF still did **not** dominate aligned gate-only:
- Original: both Recall 0.956364, FPR 0.
- Route +4: both Recall 0.916727, FPR 0.004969.
- Both +2: full Recall 0.920000 **vs gate 0.929273** (−0.9273 percentage points), FPR 0.002484.
- NRF burst3: full 0.920000 **vs gate 0.929273**, FPR 0.
- Route +8: full and gate Recall 0.889636, FPR 0.014907.
- No stressed view exhibited >=1pp learned-fusion recall gain.
- Learned-only (with gate and consensus meta-feature removed) remained at original pooled FPR 0.026087 and worst-scenario FPR 0.10. No low-FPR learned-only victory.
- Consensus Guard also exceeded the threshold with unaligned route lag4 FPR 0.004969 and both lag2 FPR 0.002484.

For all views the four detector families reported attack-episode coverage **200/200**, but pointwise recall and delays varied. Detector run coverage does not imply full pointwise detection.

Locked JSON decisions: `learned_incremental_success_on_synthetic=false`, `learned_all_fpr_budgets_pass=false`, `learned_all_no_recall_loss=false`, `learned_gain_at_least_one_pp=false`. CI success means faithful execution, **not** a positive hypothesis result.

## Fresh Open5GS sanity controls (the source-time algorithm was not run on these)

Two independently created GitHub Open5GS v2.7.7 laboratories:
- [Run 38076887165](https://github.com/verge88/NFStatusNotify/actions/runs/38076887165), [artifact 11679282349](https://github.com/verge88/NFStatusNotify/actions/runs/38076887165/artifacts/11679282349), success;
- [Run 38076969653](https://github.com/verge88/NFStatusNotify/actions/runs/38076969653), [artifact 11678672111](https://github.com/verge88/NFStatusNotify/actions/runs/38076969653/artifacts/11678672111), success.

Each real A→B→A benign run had 11 valid observations and zero alerts for semantic_guard, consensus_guard, gate-only, learned-only and full PA-TEF. On a **separately generated offline post-effect counterfactual**, each of consensus_guard/gate-only/learned-only/full PA-TEF detected 5/5 positive time points (one episode/run), false-positive count 0, detection delay 0. Semantic Guard detected 0/5. **No forged NFStatusNotify message** was transmitted. Physical trusted timestamp provenance for each state snapshot was **not** collected, so these controls cannot validate the new freshness alignment. This limitation remains central.

## Why this is a valid negative result, and follow-up

The deterministic timestamp alignment changes some input discrepancy features: source-time unit tests verify at t=38 that a four-step stale route observation is compared with the previously captured t=34 NRF snapshot, rather than newer t=38 NRF. Yet at the held-out scenario/threshold decision layer this **fails to reduce false alarms** and can worsen them under severe lag. Thus fixing a local comparison feature is **not sufficient** to ensure robust end-to-end classification with persistence, provenance availability, temporal context and threshold calibration.

The exact residual false-positive mechanisms (which held-out benign scenarios, specific event windows and feature/gate interactions) must be isolated with a **separate post-hoc diagnostic** before any redesign. Do not retrospectively relabel the locked test a success, tune on its results, or claim learned improvement. A next new study would require trustworthy source capture timestamps in the real adapter and a newly preregistered independent evaluation with scenario/domain novelty.

No change to `main` or frozen publication evidence. Keep this branch and PR as a **draft negative finding**.


## Post-hoc failure localization (NOT an additional independent validation)

The separate [post-hoc job 38077772309](https://github.com/verge88/NFStatusNotify/actions/runs/38077772309) completed successfully; [artifact 11678794176](https://github.com/verge88/NFStatusNotify/actions/runs/38077772309/artifacts/11678794176) includes `false-alarm-by-scenario.csv`, point-level `false-alarm-points.csv` (timestamps, source origin times and gate features), and `error-attribution.json`. No detector was fitted to held-out scenarios or retuned.

**Residual false-positive attribution:**

| View | Unaligned false positives | Aligned false positives | Heldout benign scenario(s) |
| --- | ---: | ---: | --- |
| route_lag4 | 160 | 160 | `udm_recovery` (160/160) |
| both_lag2 | 80 | 80 | `udm_recovery` (80/80) |
| route_jitter2_6 | 120 | 120 | `udm_recovery` (120/120) |
| route_lag8 | 400 | 480 | `udm_recovery` (320 both), `delayed_notify` (80 unaligned, 160 aligned) |

Each named benign scenario has 40 runs x 90 samples = 3,600 samples. The `udm_recovery` case explains **all** FPs in route_lag4 and both_lag2. The source-time alignment introduced **80 additional false positives** in `delayed_notify` with eight-sample route lag.

**Mechanistic diagnosis (interpretation of measured outcome and simulator implementation, not independently validated causality):** The benign `udm_recovery` route has a temporary unavailable endpoint through the recovery interval, followed by recovery completion. A route observer lag causes a *historical during-recovery* route snapshot to arrive **after** the contemporaneous `recovery_active` flag is cleared. The algorithm aligns the NRF comparison but leaves recovery/context and temporal grace logic on the arrival-time axis. Thus it can raise false alerts against a semantically legitimate historical state. Similarly, the long route lag and delayed notification can cross the 12-step transition grace context. The data support prioritizing causal **alignment of both state and its explanatory transition/recovery context**, not changing just the state comparison.

These findings were obtained after observing the benchmark's negative result. They are useful for designing a future preregistered hypothesis, but must not be used to claim that any untested context-alignment change has already solved the problem.
