# Frozen 1/8 candidate: independent real validation plan

This document is part of the preregistration record for the development-selected
consensus candidate. It is committed before the fresh real attack-like validation
runs are started.

## Frozen configurations

Reference:

- dual-source persistence: 2 samples;
- single-source persistence: 12 samples.

Candidate:

- dual-source persistence: 1 sample;
- single-source persistence: 8 samples.

The candidate was selected as the sole Pareto point in the predefined
development-only sensitivity grid from GitHub Actions run 38058210231.
No real attack-like validation result from the study defined here was available
when the candidate was frozen.

The machine-readable record is configs/consensus-candidate.yaml. Every
replicate records the SHA256 hash of that exact file, and the aggregate job
rejects mixed hashes.

## Independent experimental unit

Eight fresh GitHub-hosted Open5GS v2.7.7 laboratories are requested. Each run
creates new NRF/AUSF/UDM processes, new UDM-A and UDM-B registrations, a fresh
packet capture, and a fresh legitimate A→B→A failover trace.

The real trace is benign. The attack-like test remains a safe counterfactual
post-effect: real AUSF-cache and actual-route observations are retained while
the NRF view is frozen to the pre-failover endpoint during the failover window.
No forged NFStatusNotify message is sent.

At least six valid real-evidence runs are required for aggregation. Detector
outcomes never determine run validity.

## Calibration

Reference and candidate are calibrated independently but identically:

- target FPR: 0.001;
- synthetic development scenarios: the repository DEFAULT_SCENARIOS;
- training seeds: 60;
- 90 samples per synthetic run;
- random state: 42;
- threshold selected only from the calibration split.

The real benign and counterfactual rows are not used for threshold selection.

## Preregistered endpoints

For every valid run:

- real benign alert count;
- counterfactual sample recall;
- counterfactual FPR;
- attack-run detection;
- median detection delay.

Paired candidate-minus-reference differences are recorded for sample recall,
FPR, delay, and benign alerts.

## Preregistered interpretation rule

The 1/8 candidate may replace the 2/12 reference only if all of the following
hold in the independent series:

1. at least 6/8 requested runs have valid NRF/AUSF/route evidence;
2. the candidate is benign-alert-free in every valid real trace;
3. candidate empirical counterfactual FPR is not higher than reference FPR and
   does not exceed the target FPR;
4. candidate detects every attack run;
5. mean candidate sample recall is strictly greater than reference recall;
6. median candidate detection delay is no worse than reference delay.

The existing strict sample-level external target (sample recall 1.0 at FPR
<= 0.001) is also reported unchanged. Meeting the run-level conditions alone
does not redefine that target.

Because n is small, paired sign-test p-values and Wilson intervals are reported
descriptively and are not used as a gate that can override the criteria above.

## Safety boundary

This validation tests detection of a distributed-state post-effect derived from
real Open5GS telemetry. It does not implement or deliver a forged
NFStatusNotify exploit payload.
