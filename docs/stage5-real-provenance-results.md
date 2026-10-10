# Stage 5 result — real Open5GS measured-time provenance feasibility

**Prospective locked decision: PASS for measured evidence coverage.**
**NOT** a validation of PA-TEF, Stage 4 causal recovery suppression or cryptographically authenticated source-origin time.

## Sequence and reproducibility

1. The pre-implementation [stage-5 protocol](stage5-real-provenance-protocol.md) was committed at `70aab2688b469267f7c05e04f2b9d8ac58caaeab` **before code and new lab runs**.
2. The new real A→B→A [Open5GS workflow #38081088137](https://github.com/verge88/NFStatusNotify/actions/runs/38081088137) completed successfully; Open5GS v2.7.7.
3. [Artifact #11681000009](https://github.com/verge88/NFStatusNotify/actions/runs/38081088137/artifacts/11681000009) holds both the original real traffic evidence and newly introduced:
   - `nrf-observer-polls.jsonl`: 11 read-only NRF discovery calls before 11 auth probes, containing observed REGISTERED UDM endpoints and host poll start/end plus probe boundaries;
   - `real-provenance-audit/source-time-audit.csv`: per-row availability epochs, ages, provenance eligibility, unavailable reasons and source types;
   - `real-provenance-audit/source-time-decision.json`: fixed locked acceptance calculation.
4. [Full CI #38081088134](https://github.com/verge88/NFStatusNotify/actions/runs/38081088134): **64 tests passed**, Ruff passed. Tests explicitly reject future packet evidence, future AUSF cache events, duplicate/missing run/time joins, ambiguous NRF discovery and NRF polls occurring after probes. Tests verify that provenance is not added to the offline counterfactual.

## Frozen decision and exact observed metrics

| Audit item | Preregistered bound | Real result |
| --- | --- | --- |
| Genuine benign observation count | 11 | **11** |
| NRF eligible real discovery-poll timestamps | >=9/11 | **11/11** |
| AUSF eligible cache setup timestamps | >=9/11 | **11/11** |
| Route eligible SBI pcap observation timestamps | >=9/11 | **11/11** |
| NRF singleton response agrees with control-expected endpoint | all 11 | **11/11** |
| Eligible evidence originating after probe score cutoff | 0 | **0** |
| Timestamp ordering monotone within run | true | **true** |
| Poll-to-observation (run_id,t) one-to-one | true | **true** |
| `measurable_provenance_feasible` | all clauses pass | **true** |

A successful audit records acquisition **availability times**, not registration/state inception times. NRF timestamp is the *read-only poll completion epoch*; AUSF timestamp is the *event time in the cache log*; route timestamp is the *host packet capture time during the probe*. The NRF singleton check demonstrates the orchestrator's expected endpoint is independently observed at those 11 poll instants — a stronger source basis than the previous phase-only column.

The collection still assumes compatible host and Docker log UTC clocks, lacks a bounded clock-skew analysis and includes no signed or independently authenticated source events. The audit therefore explicitly sets:
- `provenance_cryptographically_attested=false`;
- `recovery_context_independently_trusted=false`;
- `context_detector_real_validation=false`;
- `real_attack_injection_executed=false`;
- `counterfactual_provenance_laundered=false`.

**Do not substitute the measured timestamps into the experimental Stage 4 gate as if they were trusted capture-time provenance**. Context recovery is still the orchestrator's label, not an independently verified recovery stream, and a source's latest cache setup record does not necessarily prove that its state persisted unchanged between this event and the scoring cutoff.

## Separate, unchanged external detector sanity controls

From the same Open5GS workflow:
- On 11 genuinely benign real A→B→A observations, `semantic_guard`, `consensus_guard`, `patef_gate_only`, `patef_learned_only`, and full `patef` each produced **0 alerts**.
- The existing derived offline counterfactual post-effect had five attack-active **sample points in one episode**. `consensus_guard`, `patef_gate_only`, `patef_learned_only` and full `patef` each detected **5/5**, without benign alerts; `semantic_guard` detected 0/5. This is not genuine attack network traffic; no forged NFStatusNotify was sent.
- All thresholds/models for the detector controls were unchanged. Their outputs are not evidence that any new Stage 4 or Stage 5 detector can outperform the exact deterministic gate.

Zero benign alerts on 11 correlated points is far too little to bound a deployment false-positive rate <=0.1%. Likewise five points are not five independent attacks.

## Scientific conclusion and next-stage prerequisites

Real telemetry availability is **feasible in this limited benign laboratory**, but Stage 4's previous negative finding remains negative. Source origin, source observation/availability and controller phase context must be treated as separate concepts.

A prospective next stage would add separately instrumented source-snapshot validity intervals, independent recovery/NRF state transition observations with explicit trust provenance and clock skew controls, then use a new preregistered attack-during-recovery challenge to test a conservative detector that does not silently suppress conflicts. It must explicitly compare gate-only to learned full fusion with an unchanged low-FPR constraint, independent new heldouts and eventual real non-synthetic post-effect capture.

**Decision:** keep as Draft experimental PR; do not merge into `main`. The locked Stage 5 success is instrumentation feasibility only.
