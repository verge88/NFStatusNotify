# PA-TEF: specialized NFStatusNotify detector

PA-TEF (Provenance-Aware Temporal Evidence Fusion) targets the **post-effect**
of forged `NFStatusNotify`: the NRF view can remain unchanged while AUSF
local UDM state and/or actual routing change.

It is not a replacement for sender authentication or subscription validation.
Those remain preventive controls. PA-TEF is a detection layer for cases where
the notification was already accepted or where only partial telemetry is
available.

## Architecture

PA-TEF uses four independent experts:

1. **State expert** — NRF↔AUSF and NRF↔route disagreement, persistence and
   provenance coverage.
2. **Notify expert** — trusted sender/subscription semantics and recent
   `NFStatusNotify` evidence.
3. **Temporal expert** — state transitions without a recent NRF update,
   persistence, time-since-update and recovery dynamics.
4. **Context expert** — recovery/update context used to suppress legitimate
   transient mismatches.

Each expert is a small gradient-boosted model. The fusion model never trains on
expert predictions from the same runs that trained those experts: group
out-of-fold predictions are produced with `run_id` as the split unit. After
stacking, experts are refitted on all training runs.

If a source is unavailable, its expert is gated to probability `0.5`
(neutral evidence) and the availability mask is supplied to the fusion model.
Missing telemetry is therefore not silently interpreted as normal.

A held-out calibration set trains a sigmoid/Platt calibrator. The operational
alarm threshold is then selected from the benign calibration distribution for
the requested empirical FPR.

## Semantic transition guard

The final risk is not allowed to rely on model probability alone. PA-TEF
requires semantic support from at least one of these conditions:

- a recently observed invalid/untrusted notification;
- a persistent state conflict that remains unexplained by an NRF transition;
- a cache transition without a recent legitimate NRF transition.

A legitimate transition can be established either by explicit
`nrf_update_seen` telemetry or by an observed change in `nrf_endpoint`.
The endpoint-change detector remembers the last observed NRF value across
missing samples. This recovers the common case where the update event itself was
lost but the next NRF snapshot exposes the new endpoint.

The grace window is 12 samples, matching the longest temporal aggregation
window. `recovery_active` is also treated as a benign transition context.
These contexts suppress state-divergence risk, but they do **not** suppress
strong bad-notification evidence.

This guard is intentionally domain-semantic rather than learned from one
scenario template. It was added after scenario-disjoint validation showed that
a purely learned fusion over-alerted on previously unseen delayed updates,
missing telemetry and recovery windows.

## Fair deterministic baseline

The semantic transition guard is also exposed as the standalone
`semantic_guard` detector. It uses exactly the same `semantic_attack_support()`
signal as PA-TEF but contains no learned expert or fusion model.

This comparison is mandatory for interpreting the research hypothesis. If
PA-TEF and `semantic_guard` have the same recall/FPR under scenario-disjoint
evaluation, the observed gain comes from the domain semantics rather than from
ML. That is a valid negative result: the detector should then remain primarily
deterministic unless later experiments show a reproducible ML increment.

The benchmark writes the PA-TEF minus semantic-guard recall/FPR deltas to
`hypothesis-check.json`; hypothesis status is reported but is not used to make
CI pass or fail.

## Output

`risk_report()` returns:

- `risk_score` — calibrated model risk gated by semantic support;
- `confidence` — evidence coverage, not attack probability;
- `semantic_support` — the 0–1 semantic gate applied to model risk;
- per-expert probabilities;
- `dominant_evidence` such as persistent unexplained state divergence or an
  untrusted/unbound notification.

## Evaluation protocol

The implementation reports:

- Recall@FPR=0.1%;
- empirical test FPR;
- ROC-AUC and PR-AUC;
- median detection delay;
- attack-run coverage;
- per-scenario metrics;
- scenario-disjoint holdout metrics;
- source ablations: no NRF, AUSF, route or notify telemetry.

The real Open5GS GitHub Actions recovery scenario is also scored as an external
benign control. The later A→B→A failover experiment additionally records real
NRF state, AUSF cache evidence and the actual UDM route.

## Current hard-generalization result

The original seven-scenario benchmark was too easy for the deterministic
semantic support: `semantic_guard` and PA-TEF produced identical decisions.
The benchmark now includes benign single-source observer skew plus persistent
single-source and dual-source divergence. Benign skew intentionally overlaps
the semantic support of a real persistent divergence for its first samples.

On the fixed 60-seed, 90-step, 12-scenario benchmark at target FPR 0.1%:

- ordinary run-level split: PA-TEF FPR 0 and Recall 0.794357;
- ordinary run-level split: semantic guard FPR 0 and Recall 0;
- scenario-disjoint PA-TEF pooled FPR 0.009938 and Recall 0.944970;
- scenario-disjoint semantic guard pooled FPR 0 and Recall 0;
- PA-TEF worst unseen benign-scenario FPR is 0.055556;
- minimum PA-TEF recall across unseen attack scenarios is 0.890909.

Adding source-symmetric conflict topology improved PA-TEF unseen recall from
0.450667 to 0.944970 without changing the pooled unseen FPR. This is evidence
that the learned model can transfer persistence/topology structure across
cache-only and route-only divergence, but it still over-alerts on an unseen
single-source observer skew.

Accordingly, the current ML result is **not deployable at the stated low-FPR
objective**. The candidate exceeds the 0.1% FPR budget by roughly an order of
magnitude on scenario-disjoint evaluation. The benchmark therefore reports
both strict dominance and a separate `ml_advantage_at_target_fpr` status; a
positive recall gain is not counted as an advantage unless the candidate also
meets the common FPR budget.

The next useful provenance signal is source freshness/staleness. Without a
freshness observation, a short but real single-source divergence is
information-theoretically difficult to distinguish online from a stale
single-source observer snapshot before enough persistence accumulates.

## Scientific interpretation

The current PA-TEF implementation remains a research comparator, not a
deployable superiority claim. The stronger benchmark now demonstrates both a
real learned generalization benefit (attack recall) and a decisive operational
failure (unseen benign FPR). A defensible novelty claim requires reducing that
FPR below the target without using the held-out scenario to tune the threshold,
and still beating the deterministic semantic guard under leak-free source
ablations and real Open5GS controls.
