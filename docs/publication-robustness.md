# Publication robustness experiments

This document records two experiments added before publication: a development-only
persistence sensitivity analysis and a real Open5GS benign telemetry-degradation
matrix.

## 1. Consensus persistence sensitivity

The detector implementation exposes the two persistence parameters. At the
time of the sensitivity sweep, the conservative operating point was 2/12.
Following the preregistered independent validation in run `38060262689`, the
validated operating point promoted for subsequent experiments is:

- single-source persistence: 8 samples;
- dual-source persistence: 1 sample.

The historical 2/12 reference remains explicitly reproducible.

The sweep is intentionally restricted to synthetic/development data. No real
Open5GS test labels are used to choose a parameter pair.

### Grid

Single-source persistence: 4, 6, 8, 10, 12, 16 samples.

Dual-source persistence: 1, 2, 3, 4 samples.

Every setting is evaluated using the same target FPR of 0.1% under both the
ordinary run-disjoint split and the scenario-disjoint protocol.

GitHub Actions run: `38058210231`.
Artifact: `consensus-sensitivity-38058210231` (ID `11671748356`).

### Result

The existing 2/12 reference remains valid but is not Pareto-optimal on the
development benchmark:

| Setting (dual/single) | Scenario-disjoint FPR | Attack recall | Median delay |
| --- | ---: | ---: | ---: |
| 2/12 reference | 0.000 | 0.9140 | 1 |
| 1/8 development Pareto point | 0.000 | 0.9491 | 0 |

On the ordinary run-disjoint split, the corresponding recall values are 0.9223
for 2/12 and 0.9539 for 1/8, both at empirical FPR 0.

A clear calibration cliff appears for single-source persistence 4 or 6: benign
observer-skew produces enough high-score calibration samples that the low-FPR
threshold moves above the useful score range, giving zero attack recall for all
four dual-source settings. From single-source persistence 8 upward, all attack
runs are detected; increasing the single-source persistence then monotonically
trades sample recall for additional conservatism. Increasing dual-source
persistence from 1 to 4 adds approximately 0–3 samples of median delay and
reduces recall.

The publication must therefore not describe 2/12 as an optimized setting.
It is the pre-existing conservative reference. The 1/8 point is a
development-selected candidate and requires independent attack-like real
validation before replacing the reference.

## 2. Real benign telemetry-degradation matrix

The real experiment does not alter the Open5GS network state or inject a
malicious SBI message. Each replicate first executes and validates a legitimate
UDM-A → UDM-B → UDM-A failover. Detector telemetry is then degraded offline
while the underlying real trace remains benign.

Four fresh GitHub-hosted Open5GS v2.7.7 laboratories are used.

GitHub Actions run: `38058506496`.
Aggregate artifact: `open5gs-benign-degradation-study-38058506496`
(ID `11671419283`).

### Observer views

Each of the four real traces is evaluated under 15 views:

- full telemetry;
- complete loss of NRF, AUSF, route, or notify telemetry;
- three-sample burst loss for NRF, AUSF, route, or notify;
- simultaneous three-sample NRF+notify burst loss;
- AUSF observation lag of 2 or 4 samples;
- route observation lag of 2 or 4 samples;
- trusted notification delay of 2 samples.

Missing data is represented through the existing source masks and NaN values;
it is not converted into "consistent" evidence. Lag variants preserve the real
trace and only delay the observer view.

### Result

All 4/4 real laboratories produced valid A→B→A NRF/AUSF/actual-route evidence.
For every one of the 15 variants, all three evaluated methods
(`semantic_guard`, `consensus_guard`, and PA-TEF) were alert-free in all
four independent runs.

For `consensus_guard`:

- 15/15 variants: 4/4 alert-free runs;
- mean alert rate: 0 for every variant;
- maximum observed risk: 0 for every variant.

The same zero-alert outcome was observed for the two comparators in this
specific benign matrix.

The Wilson 95% interval for an observed 4/4 alert-free proportion is
[0.5101, 1.0000]. The 15 degradation views derived from one run are correlated,
so 60 view-level cases must not be treated as 60 independent Bernoulli trials.
The independent experimental unit remains the fresh Open5GS run.

The matrix therefore provides evidence of robustness to the tested observation
loss/lag mechanisms, but does not establish a production false-positive bound.

## Interpretation for publication

These experiments strengthen two claims and weaken one possible claim:

1. Persistence is causally important: too-short single-source persistence makes
   the ultra-low-FPR calibration unusable.
2. The detector family remains benign on four independent real Open5GS traces
   under substantial observer loss and short observer lag.
3. The exact default pair 2/12 is not empirically optimal on the development
   benchmark and should not be presented as such.

The 2/12 configuration remains the conservative pre-existing reference. The
1/8 point was selected on development data and then evaluated in a separately
preregistered real attack-like validation collected after selection
(run `38060262689`). It satisfied all replacement criteria in 8/8 fresh
Open5GS runs, so subsequent experiments use 1/8 as the validated default while
retaining 2/12 as a historical comparator.


## 3. Post-promotion verification

After the frozen 1/8 candidate satisfied all preregistered replacement criteria
in run `38060262689`, the repository promoted 1/8 to the default operating
point while retaining explicit historical 2/12 constants.

The promoted default was then re-evaluated through the repository's ordinary
pipelines rather than through the frozen-candidate scorer.

### Synthetic benchmark

Run `38061618580`:

- run-disjoint Recall@target-FPR: **0.953918**;
- run-disjoint FPR: **0**;
- median detection delay: **0**;
- attack runs detected: **58/58**;
- scenario-disjoint pooled recall: **0.949091**;
- scenario-disjoint pooled FPR: **0**;
- worst-scenario FPR: **0**;
- minimum attack-scenario recall: **0.872727**;
- attack runs detected across scenario holdouts: **300/300**.

### Real failover control

Run `38061618558`:

- real benign A→B→A trace: 0 consensus alerts;
- real-derived counterfactual: sample recall **1.0**;
- empirical FPR: **0**;
- attack-run detection rate: **1.0**;
- median detection delay: **0**;
- strict external target: **met**.

The same trace remained non-alerting for semantic_guard and PA-TEF, while those
two comparators did not detect the counterfactual at their low-FPR thresholds.

### Real degraded-telemetry control

Run `38061618577` repeated the 4-run × 15-view benign degradation matrix
after promotion. All 4 fresh laboratories were valid. The promoted
`consensus_guard` remained alert-free for every degradation variant in every
run; the aggregate worst-case mean alert rate and maximum risk were both 0.

These post-promotion reruns ensure that the published default is the same
operating point used by the main benchmark and real-control workflows.
