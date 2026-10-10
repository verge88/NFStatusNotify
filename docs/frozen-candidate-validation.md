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


## Independent validation result

The preregistered GitHub Actions run `38060262689` completed successfully with
**8/8 valid fresh Open5GS laboratories**. Every replicate recorded the same
frozen candidate configuration SHA256:

`a2eaa557372337db75def2e741780b0414ad07979f8fb1d1177b92a34855338b`.

The paired result was identical in all eight independent runs:

| Metric | Reference 2/12 | Candidate 1/8 | Candidate − reference |
| --- | ---: | ---: | ---: |
| Sample recall | 0.800 | **1.000** | **+0.200** |
| Empirical FPR | 0.000 | **0.000** | 0.000 |
| Median detection delay | 1 sample | **0 samples** | **−1 sample** |
| Attack runs detected | 8/8 | **8/8** | — |
| Strict sample-level external target | 0/8 | **8/8** | — |
| Benign alert-free real traces | 8/8 | **8/8** | — |

For both recall and detection delay the candidate won all 8 paired comparisons,
with no losses or ties. The one-sided exact sign-test probability is
`0.00390625` for each endpoint. The Wilson 95% interval for an observed 8/8
paired win proportion is [0.6756, 1.0000].

Because all replicate outcomes were identical, the replicate-level SD and
bootstrap interval for the paired recall improvement collapse to +0.2, and the
paired delay improvement collapses to −1 sample. This demonstrates
repeatability under the fixed laboratory protocol; it does not imply zero
uncertainty in other deployments or implementations.

### Preregistered decision

All six preregistered replacement conditions were satisfied:

1. 8/8 requested runs were valid (minimum required: 6);
2. candidate was benign-alert-free in all 8 real traces;
3. candidate FPR was 0 in every run, no higher than reference and below the
   target 0.001;
4. candidate detected every attack run;
5. candidate mean sample recall 1.0 was strictly greater than reference 0.8;
6. candidate median delay 0 was no worse than reference delay 1.

The candidate also met the unchanged strict sample-level external target in
8/8 runs, whereas the reference met it in 0/8.

Under the preregistered rule, the 1/8 candidate is therefore eligible to replace
2/12 as the default operating point. Promotion should be a separate repository
change so that the preregistration/validation commit history remains auditable.

Aggregate artifact:
`frozen-candidate-validation-38060262689` (artifact ID `11673191863`).


## Promotion status

The candidate satisfied all preregistered criteria in run `38060262689`.
A separate promotion change moves the default `consensus_guard` operating
point from the historical 2/12 reference to the validated 1/8 setting. The
historical constants remain available so prior results stay reproducible.


### Post-promotion verification

The promoted 1/8 default was subsequently checked through the ordinary
repository workflows:

- benchmark `38061618580`: run-level recall 0.953918/FPR 0/delay 0 and
  scenario-disjoint recall 0.949091/FPR 0;
- real failover `38061618558`: benign alerts 0; counterfactual recall 1.0,
  FPR 0, delay 0, strict external target met;
- benign telemetry degradation `38061618577`: 4/4 valid runs × 15 variants,
  with zero consensus alerts in every variant.

Thus the promoted default is validated both by the preregistered paired series
and by the repository's standard post-promotion evaluation paths.
