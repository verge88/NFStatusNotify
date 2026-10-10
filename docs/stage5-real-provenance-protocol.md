# Locked stage 5: observed-time provenance audit on real benign Open5GS

**This protocol is committed before implementation or any fresh real lab run.** Stacked research branch after PR #24. Stage 4's negative result is frozen; none of the previous synthetic test sets may be relabeled as a new independent validation.

## Question and boundary

Can the existing **benign** Open5GS A→B→A lab collect temporally attributable, causally eligible NRF, AUSF and actual SBI route evidence without fabricating source-origin times? Earlier `nrf_endpoint` was the **orchestration-expected endpoint**, not an independently measured NRF sample; AUSF endpoint was the latest parsed cache setup event; SBI route came from nearest pcap packet potentially *after* the observation epoch. A simple `t` logical tick in simulator is not a real timestamp. Recovery is marked by orchestrator phase, not by independently authenticated recovery telemetry. This stage is **instrumentation feasibility**, not classifier efficacy, intrusion detection proof or proof of trusted/attested provenance.

## Frozen additions

- During each of 11 benign auth probes, call existing **read-only** NRF discovery first; record poll start/end epoch and exact set of REGISTERED `nudm-ueau` endpoints, alongside pre-existing expected endpoint and probe start/finish epoch; record in a **separate sidecar** `nrf-observer-polls.jsonl` indexed by `(run_id,t)`.
- Preserve existing `observations-raw.csv`, enrichment, detector scoring, counterfactual replay, and threshold calibration. Sidecar **must never be copied into** the offline counterfactual, particularly not after its NRF state is artificially frozen.
- Join observed benign probe rows and sidecar deterministically; a failed/ambiguous discovery does **not** count as an observed NRF origin.
- For each benign row, derive an audit *score cutoff* from the actual probe finish time. A temporally eligible NRF record is present only if a successful NRF poll ended before the probe began AND its registered endpoint set matches exactly the expected singleton; record the **poll end time** (conservative availability time, not the unknown exact source event time).
- A temporally eligible AUSF cache record is the **last matching** `Setup NF EndPoint(addr)` log event with parsed UTC epoch <= score cutoff and with an endpoint equal to the enriched observed AUSF endpoint. Do **not** reuse the original enrichment's +0.5 second future-tolerant matching to call a cache event causal. Clock assumptions: Docker log system clock is approximately the runner UTC clock, log has millisecond precision, and year comes from observation timestamp. Do not claim it as attested or timestamp signed by AUSF.
- A temporally eligible route is an HTTP/2 `generate-auth-data` SBI **pcap event** whose capture epoch falls **within the actual probe [start,finish] interval** and `ip.dst:80` equals enriched route endpoint; use the nearest event to probe start within that interval; exclude anything after probe finish or before request start. Packet capture time is a collector/host observation timestamp, not evidence of route origination/inception.
- A temporally eligible notification is a matching pcap `nf-status-notify` event if independently decoded and from NRF IP to AUSF IP, <= cutoff. Absence of notification means no positive provenance for the event. `notify_subscription_valid` still lacks independently observed cryptographic validation: it MUST NOT be inferred trustworthy from pcap src/dst alone.
- Recovery `recovery_active` is orchestrator-label only; do not endorse it as trusted suppression context.
- Real detector scores remain **unchanged**. This audit never invokes the Stage 4 context gate on real data and never sends forged NFStatusNotify messages. It must report unsupported claims, not silently turn missing timestamps into benign evidence.

## Frozen test and decision

One **new** real Open5GS v2.7.7 A→B→A laboratory (11 probes) on independent Github workflow invocation; maintain pre-existing 0-alert benign sanity validation and offline counterfactual scoring. Report per-row origins (NRF poll end, AUSF log event, route pcap epoch, optional notification frame), ages vs score cutoff, eligibility/missingness, reasons for ineligibility, observer skew (route/cached state different observed capture ages), monotonicity and forbidden lookahead count; summarized CSV and JSON in artifact.

Declare `measurable_provenance_feasible=true` only if: exactly 11 valid benign rows; >=9/11 eligible provenance rows **separately** for NRF, AUSF and route; **0** eligible origins later than probe cutoff; all joined per-run probe timestamps monotonic; no unmatched, duplicated or cross-run joins; and all 11 NRF observed endpoint sets match expected singleton. These criteria are *audit coverage and temporal causality*, not FPR or attack Recall. If any fails, report negative and keep artifact. No rescue threshold tuning.

The real **source-time context detector validation remains false regardless of this decision**: timestamps are untrusted host-side measurements and historical recovery provenance is not independently authenticated; cannot establish whether the Stage 4 suppressor is safe. Even if coverage passes, promote neither Stage 4 H1 nor H2.

## Negative controls and independent audit tests

Synthetic test fixtures must catch future route packets, future AUSF cache log entries, stale nearest-match selection, missing/duplicate poll IDs, missing NRF singleton and inconsistent endpoint, timestamps after cutoff, and counterfactual provenance laundering. No future event may be backfilled; missing returns unavailable. Publication/main remain untouched; draft stacked PR only.

## Safe scope

Only isolated benign failover and read-only NRF discovery, pre-existing AUSF auth probes and passive pcap/log collection. No unauthorized traffic, forged notification, network exploit, or live attack injection. Keep raw evidence and machine-readable decisions, including failures.
