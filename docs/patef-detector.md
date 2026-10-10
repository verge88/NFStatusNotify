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

## Scientific interpretation

The current PA-TEF implementation is a specialized research method, not by
itself a claim of dissertation novelty. A defensible novelty claim should be
based on reproducible gains over rules, Isolation Forest and the single-model
provenance baseline under matched low-FPR operation, especially in
scenario-disjoint evaluation, source ablations and real recovery controls.
