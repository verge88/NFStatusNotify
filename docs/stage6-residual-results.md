# Stage 6 — PA-TEF as consensus-OR residual: completed preregistered **negative overall** result

**Research conclusion:** The revised detector genuinely **preserves all `consensus_guard` alert decisions by construction**, and achieves a diagnostic 63.2184% pointwise Recall at zero observed false positives in the `no_ausf` view. **All three locked promotion hypotheses H1, H2 and H3 fail on the new challenge.** Especially, the unchanged deterministic rule already violates the budget under previously unseen extended benign skew; a strict OR cannot resolve this impossibility. Freshness+dropout adds **no measured improvement over the simpler residual hybrid** on any of the seven views. A stronger *post-hoc* availability-aware rule explains nearly all the apparent ML gain under no AUSF.

## Provenance and execution

1. [Stage 6 frozen protocol](stage6-residual-protocol.md), committed **before implementation / experiment** at `6d71ffc2b276975b42fec0b5bffdc2a85443e35e`.
2. [Successful locked Stage 6 experiment run 38127636415](https://github.com/verge88/NFStatusNotify/actions/runs/38127636415), experiment commit `d143a10fe9753e0b4a9e3a3790df0dc4a0a0c8b4`. The first runs #38127253420 and #38127310008 failed at an unused import lint check and at the **result JSON writer**, respectively. The latter **completed numeric model scoring** before a `numpy.bool_` JSON-serialization error. The fix exclusively changed JSON serialization; no model/training/scenario/FPR threshold/test labels were changed between inspected numeric output and successful run.
3. [Primary artifact 11697009513](https://github.com/verge88/NFStatusNotify/actions/runs/38127636415/artifacts/11697009513): `stage6-scenarios.csv`, `stage6-summary.csv`, `stage6-mask-thresholds.csv`, `stage6-bootstrap.csv`, `stage6-episode-delay.csv`, `stage6-decision.json`, `stage6-config.json`.
4. [Full project CI 38127309911](https://github.com/verge88/NFStatusNotify/actions/runs/38127309911) passed **73 tests**. Targeted tests assert equality to the original guard for OR baseline positives, group-specific calibration and unknown-mask abstention, no future source-age origin, tie-safe threshold selection and no cross-run sequential lookahead.
5. Synthetic training source scenario families: the 12 original scenarios, **parent run seeds 0–29 training**, **30–39 calibration**; heldout test: **six new scenario names and seeds 300–323**, none trained/calibrated; 90 time observations/run; **8,784 benign samples and 4,176 attack-active samples per observer view**, with 72 new benign parent runs and 72 new attacked parent runs (six families ×24 parent runs). Seven observer views are different corruptions of **the same 144 parent runs**, **not independent test populations**. Per-run/bootstrap artifact stratifies by scenario.

## Frozen model construction

The opt-in `PatefResidualGuard` runs an exact **`consensus_attack_support(x)>0` OR a learned residual on guard-silent rows**. The residual uses the existing PA-TEF expert models with a fusion meta-vector that already contains `consensus_support`, normalized single/dual/source persistence and conflict fraction. It optionally adds source-origin age with unknown marker. Synthetic capture ticks at or before the observer tick are used only if actually present, never defaulting unknown age to fresh.

Four training view copies and one seeded source-dropout copy per training parent run retain the **same parent run_id** in GroupKFold. Calibration is performed on **disjoint calibration parents**. Mondrian-like cutoffs by NRF/AUSF/Route/Notify availability mask use only benign, guard-silent positions and the maximum conservative threshold across existing calibration benign scenario groups. Unsupported masks abstain. These cutoffs are **empirical heuristics**, not conformal distribution-free guarantees across unseen benign classes or correlated timestamps.

The sequential ablation is **fixed causal rolling max-3 of learned scores**, not a CUSUM, SPRT or optimal sequential likelihood-ratio implementation. The rule still fires immediately under OR. No genuine observer IDs, UDM response codes, SUPI routing identities or NRF retry counts were invented; acquisition ages remain synthetic oracles. Training with additional observer dropout cannot make uncollected real provenance trusted.

## Frozen head-to-head: original `consensus_guard` versus source-age+dropout hybrid

Each view has **8,784 benign** and **4,176 attack-positive** temporal samples. Listed FPRs are empirical fractions of samples, **not run-independent uncertainty bounds**.

| Observer view | Baseline FPR | Hybrid FPR | Baseline Recall | Hybrid Recall | Added ML alert points | Unseen view budget 0.1%? |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| original | 0.8197% (72 FP) | 0.8197% | 91.9540% | 91.9540% | 0 | **No** |
| route_lag4 | 1.9126% (168 FP) | 1.9126% | 87.3563% | 87.3563% | 0 | **No** |
| both_lag2 | 1.3661% (120 FP) | 1.3661% | 88.5057% | 88.5057% | 0 | **No** |
| route_lag8 | 3.0055% (264 FP) | 3.0055% | 83.3333% | 83.3333% | 0 | **No** |
| no_ausf | 0% (0 FP) | **0% (0 FP)** | 0% | **63.2184%** | 2,640 | Yes, empirically |
| no_route | 0% (0 FP) | **1.0929% (96 FP)** | 0% | 56.8966% | 2,472 | **No** |
| no_nrf | 0% | 0% | 0% | 0% | 0 | Yes, but no attack detection |

For all 7 views the hybrid preserved the **entire guard positive set**, hence no guard-induced deterioration in pointwise attack Recall or delay. However `consensus_guard` by itself exceeded 0.1% FPR in four views, making the OR construction **provably unable** to satisfy 0.1% there without changing the base rule. This does **not** permit a post-hoc relaxation of the FPR criterion. In `no_route`, additional residual alarms themselves increase FPR above 0.1%.

A separate PA-TEF learned-only arm showed higher pointwise Recall on several views but much higher FPR, e.g. no_ausf Recall 70.115% / FPR 1.093%, and no_route Recall 63.793% / FPR 2.732%.

The **`residual_no_age_no_dropout` and `residual_age_dropout` arms matched exactly in pooled FP, TP and delay on all seven views**. There is therefore **no incremental measured advantage from source-age oracle or random dropout in this experiment**. The fixed rolling-max-3 diagnostic did not improve Recall on any view; for `no_route` it increased FP from **96 to 144** (FPR 1.639%). Do not interpret it as a validated CUSUM or SPRT improvement.

## Machine-readable locked decision

According to [`stage6-decision.json`](https://github.com/verge88/NFStatusNotify/actions/runs/38127636415/artifacts/11697009513):

- `truth_free_guard_union_guarantee=true` — exact decision inclusion for the same observed feature rows.
- `h1_success=false`: per-mask/view FPR targets fail on novel benign skew, despite exact guard non-regression.
- `h2_two_attack_scenarios_strictly_improved=true` and `h2_run_bootstrap_stressed_gain_at_least_1pp=true` **relative to the original abstaining `consensus_guard`**, but **`h2_success=false`** because the safety prerequisite H1 failed. The bootstrap resamples whole independent parent runs by scenario, not pointwise observations; details/intervals are stored in `stage6-bootstrap.csv`.
- `h3_success=false`: no_ausf passes (Recall >0.62, FPR=0); no_route fails (Recall=0.56897 and FPR=0.01093); no_nrf retains no state detection.
- Five calibration masks required residual abstention in each residual arm (`calibration_has_residual_abstentions`). Sparse calibration masks cannot honestly support 0.1% target claims.

No heldout-based threshold tuning was performed, and the benchmark exited successfully even with scientifically negative findings.

## Additional post-hoc fairness comparator — do NOT conflate with H1/H2/H3

The `no_ausf` original consensus has Recall=0 chiefly because its single-surviving-observer rule abstains. At the user's suggestion, **after seeing** the locked test output, we added an explicit **exploratory** `available_source_consensus_support` comparator: allow NRF+one available AUSF or Route state observer to evidence conflict after the already validated 8-sample persistence threshold; never infer NRF when absent; preserve all original guard alerts. This comparator is not preregistered and its use of the exposed Stage 6 test scenarios is not an independent confirmatory experiment.

- [Detailed post-hoc report](stage6-available-baseline-posthoc.md).
- [Successful job 38127741227](https://github.com/verge88/NFStatusNotify/actions/runs/38127741227), [artifact 11696969411](https://github.com/verge88/NFStatusNotify/actions/runs/38127741227/artifacts/11696969411), five targeted tests.
- **no_ausf:** availability-aware deterministic Recall **62.0690%**, FPR **0%**, versus residual ML Recall **63.2184%**, FPR **0%**. Apparent ML improvement vs original abstaining rule falls from +63.22 pp to only **+1.1494 pp** over a competent available-source rule.
- **no_route:** availability-aware deterministic Recall **55.7471%**, FPR **0.8197%**, versus residual ML **56.8966%**, FPR **1.0929%**. The extra ~1.15 pp Recall trades worse false alarms and both violate low-FPR target.

The post-hoc comparator demonstrates that the apparent huge no_ausf gain cannot fairly be attributed solely to learned fusion. Further untouched challenge scenarios and independent provenance are required to validate an incremental ML benefit.

## Promotion decision and missing items from requested roadmap

**Do not merge into `main`**. Keep this research PR in Draft. The positive achievement is the correct **OR invariant** and measured partial-source learned-residual recovery, not a proven FPR-constrained superiority. In this code branch, native measured observer identities, SUPI response/routing features, and independent UDM response codes remain **unavailable**; source age is not attested outside synthetic simulation. Source-specific learned sub-experts and a true calibrated CUSUM/SPRT are **not yet implemented**; the current rolling-max ablation should not be represented as one. Real controlled AUSF pause/partition/stale-cache perturbations were **not run** as part of this Stage 6 study, which is entirely synthetic.

The next preregistered comparison should test the stronger available-source rule as primary baseline on **new unexposed scenario classes**, with trusted/freshness source evidence from genuine instrumentation and conservative per-run FPR constraints. Preserving all rule positives and requiring FPR<=0.001 is impossible under unseen long benign skew unless the rule itself changes; that would require a *different* proposal with a new preregistration and a tradeoff for baseline non-regression.
