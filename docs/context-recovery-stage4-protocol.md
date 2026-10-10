# Locked stage 4: causal alignment of recovery and transition context

**This protocol is committed before implementation, test execution or benchmark inspection.** The previous frozen source-time study is negative (PR #23, run 38076969650). This is a prospective new **synthetic challenge**, not retrospective improvement on its held-out data. The explanatory `udm_recovery` failure and `delayed_notify` failure are already known from post-hoc run 38077772309; acknowledge that the hypothesis is informed by prior tests, even though new scenario families and seeds are unused.

## Causal question and hypotheses

Historical route and AUSF snapshots are compared at their capture tick (stage 3). However, `recovery_active` and `recent_nrf_update_seen_12` still describe **arrival time**, not the explanatory context at capture time. When historical recovery / authorized NRF transitions arrive late, a legitimate state mismatch can outlive the current grace window. Hypothesis H1: suppressing **only** a source-specific conflict whose *trusted observation-time* recovery or authorized NRF transition explains it reduces false alarms, without globally blocking unrelated independent sources. Hypothesis H2: PA-TEF's learned fusion adds measurable classification advantage over the exact context-aware gate.

The newly introduced context is a **trusted causal oracle in the simulator**; the lab does not presently export independently attested per-source capture timestamps or cryptographically trusted recovery provenance. In a real deployment this requires independently measured and trusted source metadata. Do not claim a production or real-exploit result.

## Fixed algorithm, including its falsification risks

- Comparator A: `raw` = current arrival-time features, no event-time alignment.
- Comparator B: `state_only` = existing causal source-time state alignment from PR #23.
- Candidate C: `state_and_context` = state alignment plus context at **each source's own origin tick**, independent for route and AUSF. If a source's exact origin tick has an already observed trusted `recovery_active=1`, or the NRF-observed `recent_nrf_update_seen_12=1` / `recent_nrf_endpoint_changed_12=1` at that origin tick, mark only that source's **state delta** as explained `0`. Never globally suppress conflicts in the other source. The corroborating NRF state at the exact tick must be available, as required by state alignment. If context is missing, the discrepancy remains unchanged (fail open / unknown is not benign). No use of test labels, attack onset or future samples in inference.
- The `bad_notify` independent evidence remains untouched. Do not modify PA-TEF training, weights, thresholds, `recovery_active`, `notify_seen`, masks or the global semantics. All downstream persistence and temporal features are recomputed after correcting source delta.
- This context rule is a **semantic detector change**, not trained ML. It may be overly trusting: an actual divergent route during genuine recovery might be suppressed. The explicit mid-recovery attack canaries below test that risk.
- No hyperparameter sweeps. History limit is the current 12-tick NRF transition window, fixed by repository. Source lag views are fixed below.

## Dataset and leakage controls

- Training/calibration pool: default 12 repository scenarios, 60 seeds 0..59, 90 steps, original pristine features. Training/calibration GroupShuffleSplit by **run_id**, seed 42, per `split_by_run`; train/calibration runs disjoint. No challenge scenario or seed may be present in either partition. Fit the 4 detectors once; use the same calibration threshold determined on original pristine held-in source data, fixed target FPR 0.001, on all views and methods.
- Primary **unseen scenario-family** challenge uses 10 prespecified, newly named scenario families (5 benign and 5 attack), 24 *new* seeds 200..223 each, 90 steps. These scenario combinations and seeds were never in prior benchmark runs. The underlying simulator and transition definitions are reused, thus results are synthetic and not a new production domain.
- Five new benign families: `recovery_end38` (start30/end38); `recovery_end55` (30/55); `recovery_update_35` (recovery30..45, legitimate NRF update35 + notification delay4); `delayed_notify_14` (legitimate update35, notification delay14); `update_then_recovery_40` (legitimate update30, notify delay8, recovery40..55).
- Five new attack families: `post_recovery_route_47`, `post_recovery_cache_47`, `post_recovery_dual_47` (recovery30..45; permanent injected **simulated post-effect** at t47), `during_recovery_route_42`, `during_recovery_dual_42` (recovery30..45; persistent simulated post-effect from t42, with route/cache discrepancy persisting after recovery). **Special offline construction for two mid-recovery attack canaries**: before feature construction, overwrite the specified observation endpoints with synthetic `udm-x` at all t >=42, respecting source masks, to ensure the positive label corresponds to a persistent effect, not a spontaneously reverted attack. This never emits network traffic.
- Fixed observer views: `original`, `route_lag4`, `both_lag2`, `route_lag8`, `route_jitter2_6`, `nrf_burst3`. No hyperparameter or scenario changes after inspection.
- Validate frame alignment (run_id,t,labels), strict origin<=arrival, no cross-run history or backward imputation, and no labels accessed in the transformation. The attacker cannot mutate trusted recovery provenance under this model; limitation must be explicit.

## Baselines, metrics, success/failure

The detector set is `consensus_guard`, `patef_gate_only`, `patef_learned_only` (gate and consensus metafeature removed), and full `patef`. Each detector scores every frame for raw/state_only/state_and_context.

Report per (scenario,view,method,detector): FP, TP, benign/attack sample counts, pooled FPR, *worst benign scenario FPR*, sample Recall, minimum attack scenario Recall, median attack episode detection delay, **detected / total independent attack runs** (separately), fixed calibration threshold, source-specific suppression counts and source provenance missingness. Also specifically report attack recall on the **during-recovery** canaries, not only pooled across attacks. No view is an independent replication of the same underlying 240 runs.

**H1 pass requires ALL**:
1. Context-aware `patef_gate_only` achieves pooled FPR <=0.001 AND worst benign scenario FPR <=0.001 in all six views.
2. It strictly reduces false positive samples vs state_only on `route_lag4` AND `both_lag2`, with no increased FP counts in any other view.
3. In each view sample recall loses at most 0.03 absolute vs state_only gate; **every attacking scenario** retains at least 80% of the state_only gate's sample recall when reference recall >0.
4. At least 95% of 120 independent attacking challenge runs detected on every view, and **both mid-recovery attack canaries** retain >=90% run detection each.

**H2 pass requires** full PA-TEF with context to meet same FPR budgets in every view, Recall not below exact context gate in ANY view, no extra median delay, and >=0.01 absolute Recall gain in a stressed view. Declare no ML gain otherwise.

The benchmark workflow should **always publish measured results even when H1/H2 fail**. Failed hypotheses do not imply failed CI.

## Real-world boundary and replication

Separate fresh benign Open5GS A→B→A run is an unmodified sanity control for existing detectors and existing offline counterfactual post-effects. Since authenticated source-timestamps and recovery provenance are unavailable, do not claim the new candidate was tested on a real Open5GS replay. No forged NFStatusNotify exploit messages, no unauthorized live network interaction, no merge into main. A negative H1 or H2 must remain a clear negative result in a Draft PR.

Future independent confirmation would require native source/acquisition-time instrumentation and held-out new implementation/topology.
