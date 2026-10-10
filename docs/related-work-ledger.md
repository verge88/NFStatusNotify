# Related-work and novelty ledger

Search cutoff: **2026-10-10**.

This document is a structured related-work ledger for the publication. It is
not presented as a formally exhaustive systematic literature review. Its
purpose is to make novelty claims auditable and to prevent broad statements
such as "the first ML detector for 5G Core security".

## Search scope

The literature scan used combinations of the following concepts:

- 5G Core / 5GC / Service-Based Architecture / SBA;
- anomaly detection / attack detection / intrusion detection;
- provenance / multi-source / logs / metrics / traffic;
- temporal sequence / temporal graph / HTTP/2;
- Network Function interactions;
- distributed state / consistency;
- NRF / AUSF / UDM;
- Open5GS.

Sources were cross-checked through publisher pages, DBLP, author/project pages,
and DOI metadata. Inclusion focused on work that is close to at least one of
the following axes:

1. runtime attack/anomaly detection inside the 5G Core;
2. temporal modelling of NF interactions or control-plane traffic;
3. provenance or multi-source evidence fusion;
4. real/open-source 5GC experimentation;
5. security analysis of NF authorization or notification-related behavior.

## Closest work

| Work | Primary observation | Temporal | Provenance / multi-source | Runtime 5GC testbed | Evaluation emphasis | Difference from this work |
| --- | --- | --- | --- | --- | --- | --- |
| **PROV5GC** — Pacherkar & Yan, WiSec 2024, DOI 10.1145/3643833.3656129 | provenance graph of 5GC activity | graph epochs / event structure | **yes: provenance graphs** | yes | attack detection + attribution | models causal/provenance activity graphs; does not formulate NRF authority, NF consumer cache, and actual downstream route as competing semantic views of one state |
| **5GCGuard** — Tan et al., IEEE TCCN 2025, DOI 10.1109/TCCN.2025.3539660 | NF interaction sequences | **yes: deep sequence model** | not the primary abstraction | cloud-native 5G testbed | abnormal NF interaction detection | learns normal interaction sequences; this work instead tests semantic state agreement across independently observed control/cache/route views |
| **Granomaly** — Fritz et al., NOMS 2025, DOI 10.1109/NOMS57970.2025.11073582 | SBI/control-plane packet edges | **yes: temporal graph** | packet-derived graph structure | **Open5GS + UERANSIM** | one-class temporal link anomaly detection | detects anomalous communication edges; it does not compare the semantic value of NRF registry state, local consumer state and the route actually used |
| **5GGuardian** — Wehbe et al., Computers & Security 148 (2025), DOI 10.1016/j.cose.2024.104114 | HTTP/2 stream / NF service features | **yes: time-series transformer** | traffic feature fusion | Free5GC + UERANSIM | HTTP/2 stream multiplexing attacks; reported average F1 around 0.98 | protocol/traffic anomaly detection rather than distributed semantic-state consistency |
| **Two-Stage Multi-Source 5GC Detection** — Wang et al., CRESS 2025, DOI 10.1109/CRESS68073.2025.11452567 | NF logs + traffic + pod metrics | temporal alignment | **yes: heterogeneous source fusion** | 5GC experimental dataset | XGBoost anomaly detection + root-cause classification; F1-oriented | multi-source means telemetry modalities; this work treats sources as independent semantic witnesses of the *same control-plane state* and explicitly models missing witness availability |
| **5GAC-Analyzer** — Thorn et al., WiSec 2024, DOI 10.1145/3643833.3656134 | static NF implementation + 3GPP access-control policy | no runtime temporal detector | policy/program-analysis evidence | four 5GC implementations | over-privilege discovery | complements the threat model by finding NF authorization problems, but is static policy analysis rather than runtime state-consistency detection |
| **Open5GS NFStatusNotify advisory** — GHSA-fvpc-gmgr-qrg3, 2026 | AUSF callback acceptance, UDM cache, downstream auth route | persistence of poisoned live state | direct evidence across NRF/cache/route in vulnerability analysis | Open5GS v2.7.7 | vulnerability reproduction | establishes the concrete vulnerability/post-effect; it is not a detector or low-FPR consistency method |

Additional adjacent implementation/deployment security work includes Yang et
al., *Uncovering Security Vulnerabilities in Real-world Implementation and
Deployment of 5G Messaging Services*, WiSec 2024,
DOI 10.1145/3643833.3656131. It demonstrates the value of real-system security
measurement but targets RCS/IMS messaging rather than 5GC distributed-state
detection.

## What is **not** novel here

The paper should **not** claim novelty for any of the following by themselves:

- applying ML to 5G Core anomaly detection;
- using temporal models for NF/control-plane behavior;
- using provenance graphs in 5G Core security;
- combining more than one telemetry source;
- using Open5GS for security experiments;
- discovering the NFStatusNotify cache-poisoning vulnerability itself;
- observing that control-plane attacks can alter downstream behavior.

All of these have direct prior or contemporaneous precedent.

## Scoped novelty candidates

Within the searched set, the defensible contribution is the **combination and
problem formulation**, not any single primitive.

### N1 — Cross-view semantic state consistency

The monitored object is not a packet, request sequence, process metric, or
generic provenance graph. The detector asks whether three independently
observable representations of one service-routing decision agree:

1. **control authority:** UDM endpoint registered/discovered through NRF;
2. **consumer state:** UDM endpoint held by AUSF;
3. **real effect:** endpoint actually used for the downstream authentication
   request.

This converts a security post-effect into a distributed-state consistency
problem.

### N2 — Source provenance as evidential strength

Source masks are not only imputation metadata. They determine which consistency
claims can be made. A disagreement confirmed by two independent state
observers has greater evidential strength than a disagreement visible in only
one observer.

The resulting `consensus_guard` uses asymmetric persistence:

- trusted/untrusted notification-semantic violation: immediate evidence;
- corroborated dual-source state divergence: short persistence;
- single-source state divergence: longer persistence.

### N3 — Low-FPR evaluation under observer uncertainty

The primary operating constraint is FPR 0.1%, with:

- run-disjoint train/calibration/test;
- scenario-disjoint holdout;
- missing-source ablation performed before feature engineering;
- calibration-tie diagnostics;
- benign real telemetry-loss/lag controls;
- explicit detection-delay measurement.

This differs from evaluations whose headline metric is accuracy/F1 on a fixed
attack dataset.

### N4 — Negative ML result as part of the contribution

The repository does not assume that learned fusion is automatically superior.
PA-TEF is retained as a comparator and, in several external/held-out settings,
does not satisfy the low-FPR requirement even when its ranking metrics are
strong.

The publication contribution can therefore include the empirical finding that
**domain-semantic source consensus can be more reliable than learned anomaly
fusion at an ultra-low operational FPR**.

### N5 — Preregistered parameter promotion with real validation

The original 2/12 persistence setting was not retrospectively called optimal.
A development-only sweep selected 1/8, the candidate was frozen before new real
runs, and an independent 8-run Open5GS series applied preregistered replacement
criteria before promotion. Post-promotion standard workflows then repeated the
benchmark and real controls.

This methodology strengthens the evidential claim even though preregistration
itself is not an algorithmic novelty.

## Safe novelty wording

Recommended wording:

> We formulate detection of 5G SBA post-effects as a provenance-aware
> cross-view state-consistency problem over control authority, consumer cache,
> and actual service routing. We introduce a deterministic source-consensus
> detector whose temporal persistence depends on independent corroboration, and
> evaluate it under scenario-disjoint and incomplete-telemetry conditions at a
> target FPR of 0.1%.

Recommended empirical wording:

> In the literature set reviewed through 2026-10-10, we did not identify prior
> 5G Core detection work that jointly treats NRF state, NF consumer cache, and
> the actual downstream route as independent semantic witnesses of the same
> routing state while explicitly conditioning consistency evidence on source
> availability.

Avoid:

- "the first 5G Core anomaly detector";
- "the first provenance-aware 5G detector";
- "the first multi-source detector";
- "the first temporal detector";
- "the first Open5GS security detector";
- "we detect the real forged NFStatusNotify attack" unless the experiment
  actually delivers the exploit rather than evaluating its real-derived
  post-effect.

## References

1. H. S. Pacherkar and G. Yan. **PROV5GC: Hardening 5G Core Network Security
   with Attack Detection and Attribution Based on Provenance Graphs.** ACM
   WiSec 2024. DOI: 10.1145/3643833.3656129.
2. Y. Tan, J. Liu, Y. Li, and J. Wang. **Deep Learning-Based Proactive Anomaly
   Detection for 5G Core Control Plane Network Function Interactions.** IEEE
   TCCN 11(6), 2025. DOI: 10.1109/TCCN.2025.3539660.
3. T. Fritz, A. Schwankner, J.-H. Wissing, R. Buchta, and G. Dreo Rodosek.
   **Granomaly: A Framework for Anomaly Detection in 5G Core Network Control
   Plane Traffic with Temporal Graph Neural Networks.** NOMS 2025.
   DOI: 10.1109/NOMS57970.2025.11073582.
4. N. Wehbe, H. A. Alameddine, M. Pourzandi, and C. Assi. **Empowering 5G SBA
   Security: Time Series Transformer for HTTP/2 Anomaly Detection.** Computers
   & Security 148, 2025, 104114. DOI: 10.1016/j.cose.2024.104114.
5. X. Wang, X. Liao, J. Yang, R. Feng, and J. Xu. **A Two-Stage Anomaly
   Detection Framework for 5G Core Networks Based on Multi-Source Data.**
   CRESS 2025, pp. 139-146. DOI: 10.1109/CRESS68073.2025.11452567.
6. S. Thorn, K. V. English, K. R. B. Butler, and W. Enck. **5GAC-Analyzer:
   Identifying Over-Privilege Between 5G Core Network Functions.** ACM WiSec
   2024. DOI: 10.1145/3643833.3656134.
7. Y. Yang, Y. Zhang, T. Wan, C. Wang, H. Duan, J. Chen, and Y. Li.
   **Uncovering Security Vulnerabilities in Real-world Implementation and
   Deployment of 5G Messaging Services.** ACM WiSec 2024.
   DOI: 10.1145/3643833.3656131.
8. Open5GS Security Advisory **GHSA-fvpc-gmgr-qrg3**, 2026:
   https://github.com/open5gs/open5gs/security/advisories/GHSA-fvpc-gmgr-qrg3
