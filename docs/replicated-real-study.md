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
