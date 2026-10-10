# Preregistered event-time provenance alignment: follow-up experiment

Protocol commit is created **before experiment implementation and execution**. This branch is a stacked exploratory study over PR #22; `main` and frozen publication evidence must not change.

## Motivation, sensor boundary and estimands

Run 38075933372 found 0.004969 pooled FPR / 0.044444 worst-scenario FPR under four-step route observer lag, and 0.002484 / 0.022222 under two-step dual-observer lag. PA-TEF v2 learned fusion did not beat its exact gate-only comparator. Hypothesis: comparing state observations obtained at **different source times** creates false conflicts. Test whether *causal event-time alignment*, with independently supplied authentic acquisition timestamps, prevents these false conflicts.

**Important external validity limitation:** the present real Open5GS laboratory does NOT measure authenticated source acquisition timestamps for all NRF/AUSF/route observer streams. The experiment injects trustworthy origin metadata in a synthetic sensor wrapper; this is an *oracle source-time provenance assumption* rather than an implemented Open5GS feature. No inference from attack label or hidden ground truth endpoint is permitted in the alignment algorithm. Nothing from real attack labels is used to train, calibrate, or select a threshold. Any positive synthetic result does NOT establish deployability.

## Fixed data and partition

- The same 12 predefined scenario classes, each 90 samples/run; train/calibration drawn from seeds 0..59.
- For each heldout scenario, do not train or calibrate on that scenario. The heldout evaluation uses **fresh seeds 100..139 only**, outside all training/calibration. These scenario classes are reused from earlier research, so these are not wholly novel classes and post-hoc generalization claims are prohibited.
- Train/calibration per other scenario: group-disjoint via `_split_scenario_holdout` on seeds 0..59, evaluation random state 42 and calibration fraction 0.25.
- The four comparators: consensus_guard, patef_gate_only, patef_learned_only (no consensus meta-feature), full patef. Every detector is fitted and threshold-calibrated **once per heldout scenario** using unmodified training and calibration only.
- For each test view, apply the same frozen fitted models/thresholds to **unaligned** and **aligned** feature frames. Build the unaligned feature frame exactly as in the previous experiment; the aligned frame rewrites *only* NRF-vs-AUSF and NRF-vs-route discrepancy feature inputs using NRF *observed history at source capture time*, then recomputes all downstream features causally. The actual current `nrf_endpoint`, `nrf_update_seen`, source masks, event notifications, labels, and recovery context are unchanged.
- Source capture time (`origin_t`) is attached at **acquisition**, then shifted together with each delayed endpoint. It is unknown (NaN) for an unobserved endpoint. Event-time lookup must never access future observations, cross run IDs, or forward-fill missing NRF values. Unavailable matched NRF snapshots imply unknown discrepancy, not benign evidence. The algorithm must not inspect labels, `attack_start`, `scenario` or future samples.

## Locked views

1. `original`: no additional degradation;
2. `ausf_lag4`: AUSF source delayed 4 samples;
3. `route_lag4`: route source delayed 4 samples;
4. `both_lag2`: AUSF and route delayed 2;
5. `notify_lag2`: notification delayed 2 (no endpoint alignment fix expected);
6. `nrf_burst3`: NRF unavailable t=34..36; missing prior history **must not be reconstructed**;
7. `route_lag8`: route delayed 8;
8. `route_jitter2_6`: route origin lag alternates 2 and 6, based only on `t` parity (a deterministic delayed observer; no future peeks).

## Precommitted metrics and decisions

For each detector/view/alignment, report FP, TP, benign/attack samples, pooled and worst benign-scenario FPR, pooled recall, minimum attack-scenario recall, attack-episode coverage, delay and all thresholds; output per-fold data and aggregate machine-readable JSON. Keep view-level results correlated.

Primary **semantic freshness benefit** succeeds only when the *aligned gate-only* versus *unaligned gate-only*:
- has pooled FPR <= 0.001 and worst-case benign scenario FPR <=0.001 in **all 8 views**;
- shows no more than 0.03 absolute recall decrease in **any view**;
- shows strict reduction of FP count in `route_lag4` and `both_lag2`;
- detects at least the same number of attack episodes as the unaligned gate in all views.

Secondary **incremental learned fusion** succeeds only if aligned full PA-TEF has pooled and worst-scenario FPR <=0.001 in every view, no pooled recall/median-delay loss to aligned gate-only in any view, plus >=0.01 absolute recall gain in >=1 stressed view. If the hybrid merely reproduces the gate, reject any learned-advantage claim.

A fresh real Open5GS benign A→B→A plus counterfactual control is run **unmodified**, and benign alerts / sample recall / delay reported. It does **not** validate the event-time alignment (source timestamp metadata unavailable in this laboratory), so the real result is an independent sanity control and not a criterion proving freshness benefit.

## Negative outcomes and ethics

Do not reinterpret empirical zero FPR on correlated synthetic samples as a proven population <0.1% rate. If any criterion fails, report the failures, even if an aggregate score improved. No tuning on heldout or real outcomes; any later refinement requires a separate locked study. Never send forged notifications or run unauthorized exploit traffic. Keep as draft stacked PR and do not merge into `main`.
