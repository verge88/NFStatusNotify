# Replicated real Open5GS failover study

This experiment estimates run-to-run variability of the real Open5GS
A→B→A UDM failover control instead of relying on one laboratory execution.

## Replication design

The GitHub Actions workflow `Open5GS replicated failover study` starts eight
independent matrix jobs. Each replicate runs on a fresh GitHub-hosted
`ubuntu-24.04` runner and creates a fresh isolated Open5GS laboratory:

- Open5GS v2.7.7;
- independently started NRF, AUSF, UDM-A and UDM-B containers;
- fresh NF registration state and UDM NF instance identifiers;
- independent packet capture and AUSF log collection;
- the same baseline → UDM-B failover → UDM-A recovery protocol;
- the same real-derived counterfactual construction and detector calibration.

The fixed protocol makes the replicates comparable. Fresh runners and fresh NF
registrations provide process-level replication, but the eight observations
should not be interpreted as a random sample of every possible production 5G
deployment.

## Metrics retained per replicate

For each detector the study records:

- benign alerts on the real A→B→A trace;
- counterfactual sample recall and FPR;
- attack-run detection rate;
- median detection delay;
- threshold and maximum risk.

The study also records infrastructure variability:

- cache-event count;
- decoded NRF notification count;
- decoded authentication-route count;
- failover, recovery and total experiment durations;
- UDM-A and UDM-B NF instance identifiers.

## Dispersion and uncertainty

Continuous replicate-level metrics are reported with:

- mean and sample standard deviation;
- median, Q1, Q3 and IQR;
- minimum and maximum;
- percentile bootstrap 95% confidence intervals for the mean and median
  (10,000 resamples, deterministic analysis seed).

Binary replicate outcomes such as attack-run detection and benign alert-free
execution use Wilson 95% confidence intervals. Wilson intervals are reported
because n=8 is too small for a normal approximation to a binomial proportion.

The bootstrap and Wilson intervals quantify the uncertainty of this laboratory
replication set. They are exploratory intervals, not a claim that eight
containerized Open5GS runs establish population-level production performance.

## Missing or failed replicates

The matrix uses `fail-fast: false`. A detector alert does not invalidate a
replicate and is retained as a result. A replicate is excluded only if the
underlying real laboratory evidence is invalid or incomplete, for example if
the expected NRF/AUSF/actual-route A→B→A sequence cannot be reconstructed.

The aggregate job requires at least six valid runs out of eight and reports the
actual valid replicate count. This prevents silent selection of only successful
detector outcomes while still allowing one or two infrastructure failures to be
reported rather than destroying the entire study.

## Outputs

The aggregate artifact contains:

- `replicate-detector-metrics.csv`;
- `replicate-infrastructure.csv`;
- `replicate-dispersion.csv`;
- `replicate-infrastructure-stats.csv`;
- `replicate-proportions.csv`;
- `replicate-study-summary.json`;
- `replicate-study-summary.md`.

Raw evidence for every replicate is uploaded separately so the aggregate
statistics can be independently recomputed.


## Observed results

GitHub Actions run `38055330313` completed successfully with **8/8 valid
independent laboratory instantiations**. Across the eight runs the laboratory
recorded 8 unique UDM-A NF instance IDs and 8 unique UDM-B NF instance IDs
(16/16 unique identifiers in total).

Detector outcomes were identical across all eight replicates:

| Detector | Mean sample recall ± SD | Mean FPR | Attack runs detected | Median delay | Benign alert-free runs |
| --- | ---: | ---: | ---: | ---: | ---: |
| `consensus_guard` | 0.800 ± 0.000 | 0.000 | 8/8 | 1 sample | 8/8 |
| `semantic_guard` | 0.000 ± 0.000 | 0.000 | 0/8 | n/a | 8/8 |
| `patef` | 0.000 ± 0.000 | 0.000 | 0/8 | n/a | 8/8 |

For `consensus_guard`, attack-run detection and benign alert-free execution
were both 8/8. The Wilson 95% interval for each observed proportion is
**[0.6756, 1.0000]**. The strict sample-level external target was met in 0/8
runs, with Wilson 95% interval **[0.0000, 0.3244]**, because the intentional
one-sample persistence delay keeps sample recall at 0.8 rather than 1.0.

Because detector outcomes were identical in all eight runs, their replicate-level
SD, IQR and bootstrap intervals collapse to the observed point values. This is
evidence of repeatability under this fixed protocol, not evidence of zero
uncertainty in other deployments.

Infrastructure timing showed measurable run-to-run variation:

| Metric | Mean ± SD | Median | IQR | Range | Bootstrap mean 95% CI |
| --- | ---: | ---: | ---: | --- | --- |
| Failover duration | 27.229 ± 1.041 s | 26.935 s | 0.200 s | 26.461–29.760 s | 26.761–28.000 s |
| Recovery duration | 15.804 ± 0.427 s | 15.656 s | 0.072 s | 15.492–16.834 s | 15.609–16.120 s |
| Total experiment duration | 59.892 ± 1.846 s | 59.325 s | 0.553 s | 58.243–64.230 s | 58.973–61.260 s |

Decoded evidence was highly stable: notification frames were 4/4/…/4 in every
replicate and authentication-route frames were 11 in every replicate.
AUSF cache-event count varied from 6 to 8 (mean 7.25, SD 1.04, median 8,
IQR 2), showing that internal event logging can vary even when the reconstructed
semantic A→B→A state sequence and detector result remain unchanged.

The aggregate artifact is
`open5gs-replicate-study-38055330313` (artifact ID `11671791532`).
Raw evidence for all eight runs is stored in the corresponding per-replicate
artifacts from the same workflow run.
