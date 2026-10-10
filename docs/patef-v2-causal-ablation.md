# PA-TEF v2 causal ablation

This note records the exploratory PA-TEF v2 work performed after the frozen
publication artifact. It is diagnostic evidence, not a replacement for the
frozen publication claims.

## Motivation

PA-TEF v2 substantially improved the original PA-TEF low-FPR results by
replacing coverage-weighted semantic support with a provenance-normalized
eligibility gate. The improvement needed a causal ablation because a hybrid
model should not attribute deterministic gate behavior to learned fusion.

Three variants were therefore evaluated:

- `patef_gate_only`: the provenance-normalized eligibility gate with no ML;
- `patef_learned_only`: PA-TEF experts/fusion/calibration with no decision
  gate and with `consensus_support` removed from the meta-features;
- `patef`: the complete PA-TEF v2 hybrid.

The learned-only variant deliberately removes the consensus meta-feature so the
comparison does not leak the deterministic consensus rule back into the ML
baseline.

## Hard-generalization benchmark

Run: `38071193369`.

| Detector | Run FPR | Run recall | Scenario FPR | Scenario recall | Worst scenario FPR | Delay |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| consensus_guard | 0 | 0.953918 | 0 | 0.949091 | 0 | 0 |
| patef_gate_only | 0 | 0.960502 | 0 | 0.956364 | 0 | 0 |
| patef_learned_only | 0 | 0.960502 | 0.026087 | 0.956364 | 0.100000 | 0 |
| PA-TEF v2 | 0 | 0.960502 | 0 | 0.956364 | 0 | 0 |

The complete hybrid and gate-only detector have identical classification
metrics. The learned-only model retains the same attack recall and very strong
ranking quality (run ROC-AUC 0.999757, PR-AUC 0.999204), but its threshold does
not transfer to unseen benign scenarios.

The learned-only false positives are concentrated in held-out semantic regimes:

- `udm_recovery`: FPR 0.10;
- `cache_observer_skew`: FPR 0.0667;
- `route_observer_skew`: FPR 0.0667.

These scenarios are absent from training in their respective scenario-disjoint
folds. The deterministic gate encodes the causal/provenance prior needed to
classify those unseen regimes safely.

## Source ablations

The same pattern appears in source ablations. Full PA-TEF v2 follows the
gate-only decision envelope. Learned-only may slightly increase recall under
partial telemetry, but can spend or exceed the ultra-low-FPR budget:

- no NRF: learned-only recall 0.0498, FPR 0.00123;
- no AUSF: learned-only recall 0.7790, FPR 0.00113;
- no route: learned-only recall 0.7843, FPR 0;
- no notify: learned-only recall 0.9605, FPR 0.

This does not establish an operational advantage over the gate.

## Real Open5GS failover

Run: `38071534151`.

On the real benign A→B→A trace, gate-only, learned-only, and full PA-TEF v2 all
produced zero alerts.

On the real-derived counterfactual:

- gate-only: recall 1.0, FPR 0, delay 0;
- learned-only: recall 1.0, FPR 0, delay 0;
- full PA-TEF v2: recall 1.0, FPR 0, delay 0.

The hybrid again has no incremental classification gain over gate-only on this
external trace.

## Real benign degradation

Run: `38070957921`.

Four fresh Open5GS runs and all 15 benign telemetry-degradation variants were
alert-free for gate-only, learned-only, and full PA-TEF v2. Learned-only benign
scores remained finite and small rather than being suppressed by a gate, which
confirms that this result is not an artifact of masking its output.

## Permissive soft-gate sweep

Run: `38072376936`.

To test whether learned fusion could add value inside a wider semantic
eligibility region, single-source persistence was swept from 1 to 7 while
keeping dual-source persistence at 1. The learned model was fitted once per
split/fold and reused for every gate setting.

Scenario-disjoint hybrid results:

| Single persistence | FPR | Recall | Worst FPR |
| ---: | ---: | ---: | ---: |
| 1 | 0.014907 | 0.956364 | 0.066667 |
| 2 | 0.012422 | 0.956364 | 0.055556 |
| 3 | 0.009938 | 0.956364 | 0.044444 |
| 4 | 0.007453 | 0.956364 | 0.033333 |
| 5 | 0.004969 | 0.956364 | 0.022222 |
| 6 | 0.002484 | 0.956364 | 0.011111 |
| 7 | 0.000000 | 0.956364 | 0.000000 |

Recall never increases when the gate is relaxed. The learned layer therefore
does not recover additional attacks; it only inherits additional false
positives until the gate reaches the original seven-sample persistence.

Gate-only settings 1–6 are calibrated above their binary positive score and
therefore obtain zero recall at the target FPR. This confirms that persistence
is necessary, but does not establish an incremental learned-fusion benefit.

## Interpretation

PA-TEF v2 is a better *hybrid detector* than the original PA-TEF, but the
current experiments do not support the claim that learned evidence fusion adds
classification power beyond the provenance-normalized gate.

The defensible conclusions are:

1. Learned fusion has excellent within/distribution ranking quality.
2. Learned-only threshold transfer fails on unseen recovery/observer-skew
   regimes.
3. The provenance-normalized deterministic gate is necessary and sufficient
   for the observed low-FPR classification improvement.
4. Full PA-TEF v2 currently reproduces gate-only classification decisions.
5. Future ML work should target domain/source invariance rather than further
   relaxing the semantic gate.

The v2 branch should therefore remain experimental unless the paper explicitly
describes PA-TEF as a gated hybrid and reports the gate-only ablation.
