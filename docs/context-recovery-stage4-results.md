# Stage 4: causal recovery/transition context — locked negative finding

**Outcome:** the precommitted semantic-context hypothesis H1 and incremental learned-fusion hypothesis H2 both **failed**. This does not mean the false-positive suppression is illusory; it means the measurable benefit is accompanied by unacceptable missed attack samples / delay and insufficient FPR budget transfer on the new challenge. The study is **synthetic oracle** evidence only, not deployed Open5GS validation.

## Locked protocol and provenance

- [Preregistered specification](context-recovery-stage4-protocol.md), commit `c34e9e7749761d411862d75cde8636b070679b47`, created before candidate implementation / tests / benchmark.
- [GitHub Actions challenge run 38079237792](https://github.com/verge88/NFStatusNotify/actions/runs/38079237792): **success**, meaning all pre-specified computations were executed.
- [Evidence artifact 11680270245](https://github.com/verge88/NFStatusNotify/actions/runs/38079237792/artifacts/11680270245): `stage4-scenario.csv`, `stage4-summary.csv`, `stage4-decision.json`, `stage4-manifest.json`. Includes per-case FP/TP, threshold, delay, episode coverage and source-specific explanations.
- [Full CI 38079258042](https://github.com/verge88/NFStatusNotify/actions/runs/38079258042): success.
- Training/calibration (run-disjoint) exclusively from original 12 scenarios, seeds 0–59; target FPR = 0.001; **one fitted model and one original-data threshold per detector**, reused across all challenge modes. Independent challenge: 5 novel benign and 5 novel attack scenario names, seeds 200–223, each 90 steps. This is novel scenario *combinations within the same synthetic simulator*, not a new deployment/domain.
- Exactly **16,200 benign and 5,400 attack-positive sample points per view**; 120 independently seeded synthetic attack runs total per view. All six views of one run reuse the same underlying observations and are correlated.
- Three ablations: `raw`, `state_only`, `state_and_context`; four detectors: `consensus_guard`, `patef_gate_only`, `patef_learned_only`, full `patef`. The context candidate removes a discrepancy only for the source with a trusted same-origin-tick recovery/transition explanation. It leaves independent other-source discrepancy and bad-notify evidence untouched.

## Primary comparison: gate-only

| Fixed view | State-only FPR | Context FPR | Worst context benign-scenario FPR | State-only Recall | Context Recall | Median detection delay (state → context) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| original | 0.002963 (48 FP) | 0.002963 (48 FP) | 0.022222 | 0.920000 | 0.893333 | 3 → 6 |
| route_lag4 | 0.026667 (432 FP) | 0.000000 (0 FP) | 0.000000 | 0.902222 | 0.822222 | 0 → 7 |
| both_lag2 | 0.023704 (384 FP) | 0.002963 (48 FP) | 0.022222 | 0.893333 | 0.848889 | 3 → 8 |
| route_lag8 | 0.041481 (672 FP) | 0.000000 (0 FP) | 0.000000 | 0.902222 | 0.768889 | 0 → 9 |
| route_jitter2_6 | 0.020741 (336 FP) | 0.000000 (0 FP) | 0.000000 | 0.888889 | 0.813333 | 0 → 6 |
| nrf_burst3 | 0.000000 (0 FP) | 0.000000 (0 FP) | 0.000000 | 0.920000 | 0.893333 | 3 → 6 |

False positives fall strongly under lagged route observation. However the price is not acceptable under the **prespecified** quality contract: for route_lag4 Recall drops **8.00 percentage points**, for route_lag8 **13.33 points** (the permitted loss was 3.00 points per view). Median detection delay rises from zero to 7–9 samples on those views. Additionally original and both_lag2 still have FPR **0.2963%** (target <=0.1%) and worst-scenario FPR **2.2222%**.

For each of the six views the context gate still detected **120/120 attacked runs**. The two mid-recovery persistence attack canaries each retained at least the preregistered 22/24 detected runs threshold. Yet `h1_all_attack_scenario_ratio=false`: some attack scenario loses too much *pointwise recall*, even when its run is eventually detected. This illustrates why run detection, pointwise recall and onset delay must be separately reported.

The [decision artifact](https://github.com/verge88/NFStatusNotify/actions/runs/38079237792/artifacts/11680270245) records:
- `h1_all_fpr_budgets_met=false`;
- `h1_all_sample_recall_noninferiority=false`;
- `h1_all_attack_scenario_ratio=false`;
- `h1_all_episode_coverage=true`;
- `h1_all_recovery_canaries=true`;
- `h1_prespecified_fp_reduction=true`;
- **`h1_success=false`**.

## ML incremental contribution — still absent

On the candidate `state_and_context` features, full PA-TEF and `patef_gate_only` have **identical summary-level FPR and Recall** for all six views (including the same 48 residual FPs in `original` and `both_lag2`). No ≥1 percentage-point learned Recall gain has occurred. The learned-only model may show high raw Recall on certain lagged views, but its FPR is too high; it cannot establish a low-FPR fusion contribution.

Locked decision: `h2_all_fpr_budgets_met=false`, `h2_recall_gain_at_least_1pp=false`, **`h2_success=false`**.

## Diagnostic interpretation and security caveat

The source-specific recovery/NRF transition explanation is causally local to a *trusted acquisition tick*. Under this **oracle provenance** assumption, it suppresses recovery-induced stale-route conflicts much more strongly than state-value alignment alone. But post-recovery attacks, and especially attacks overlapping real recovery, can also be suppressed for some samples because context alone does not prove whether a conflict was malicious. This is **not a deployable detection strategy without independent recovery authenticity and a precise threat model**. An attacker able to forge or influence the recovery/transition provenance would invalidate the trust boundary altogether.

The null observations / FPR counts are heavily correlated within scenario and run. Zero empirical FP does not prove population FPR below 0.1%; attack coverage of 120/120 synthetic runs is not proof of detection across other network implementations.

## Boundary to real Open5GS

A separate real Open5GS A→B→A control uses the unchanged v2 detectors; it cannot evaluate new context alignment because authenticated per-source acquisition time and recovery event-time provenance have **not** been instrumented in the real adapter. Its attack-like trace is an offline counterfactual post-effect, not a forged NFStatusNotify payload delivered over the network. The protocol prohibited any such traffic.

**Promotion decision:** keep PR Draft, do not merge to `main`, preserve both rejected hypotheses and negative safety tradeoff. The next research step would require independently measured provenance in actual capture code and a new preregistered test under a threat model that includes recoveries overlapping attacks, rather than picking a threshold on these viewed challenge scenarios.


## Independent real Open5GS sanity control — completed (unchanged detectors)

[Real Open5GS A→B→A run 38079258150](https://github.com/verge88/NFStatusNotify/actions/runs/38079258150): **success**. [Evidence artifact 11680395724](https://github.com/verge88/NFStatusNotify/actions/runs/38079258150/artifacts/11680395724). Open5GS v2.7.7, 11 valid observation points of genuine **benign** failover/recovery.

Every baseline scored the same benign control with **0 alerts among 11 observations**: semantic_guard, consensus_guard, patef_gate_only, patef_learned_only and full patef. The replay of an **offline counterfactual post-effect** derived from that benign trace had five attack-active points in **one** episode. Consensus, gate-only, learned-only and full PA-TEF scored **5/5 detected**, with 0 benign alerts and median delay 0 samples; semantic_guard detected 0/5. These are *five samples of one episode*, not five independent attacks, and are **not** a live forged NFStatusNotify payload delivery.

The laboratory did **not** execute the new `context_aligned_features` function. The source-time/recovery oracle required by that function was absent from recorded trusted acquisition metadata. Accordingly the external control proves only continued operation of previous baselines, **not** real-world validity of H1 or H2. Zero observed alerts on one short trace does not prove a population FPR ≤0.1%.

This negative research result is final under the locked protocol; no changes to models/thresholds or a post-hoc positive reinterpretation are authorized.
