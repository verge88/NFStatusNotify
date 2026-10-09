# Real Open5GS observations in GitHub Actions

Workflow: `.github/workflows/open5gs-real-lab.yml`.

The workflow builds **Open5GS v2.7.7** from source inside an ephemeral GitHub
runner using the pinned `docker-open5gs` revision
`10295cfecb2f86f88944df1728127853eb4d6a1f`.

## What the run does

1. Starts real NRF, AUSF and UDM processes in an isolated Docker network.
2. Queries the NRF discovery service over real HTTP/2 SBI.
3. Creates a legitimate NRF subscription for UDM registration/deregistration
   events with the real AUSF `nf-status-notify` callback URI.
4. Captures SBI traffic on the Docker bridge.
5. Gracefully stops the real UDM, samples NRF state, then restarts UDM.
6. Decodes `NFStatusNotify` frames with `tshark`.
7. Collects Open5GS logs and requires an AUSF `(NRF-notify)` log event.
8. Converts the real observations into the same CSV/feature schema used by the
   synthetic research harness.

No forged notification is sent in this workflow. It is a **benign/recovery
control experiment** intended to measure legitimate transient inconsistency and
false-positive behaviour.

## Artifact contents

The `open5gs-real-observations-<run_id>` artifact includes:

- `observations.csv` — time-aligned real NRF and packet-capture observations;
- `derived/features.csv` — features consumed by the detector pipeline;
- `nrf-snapshots/*.json` — raw NRF discovery responses;
- `sbi.pcap` — packet capture from the isolated SBI bridge;
- `nfstatusnotify.tsv` — decoded callback frames;
- `http2-requests.tsv` — decoded HTTP/2 request timeline;
- `logs/{nrf,ausf,udm}.log` — native Open5GS logs where available;
- `semantic-evidence.log` — filtered NRF/AUSF semantic events;
- `lab-meta.json` and `notification-summary.json` — run metadata and checks.

The current real-data adapter deliberately marks direct AUSF-cache and actual
authentication-route state as unavailable (`m_ausf=0`, `m_route=0`) rather
than fabricating them. Those sources can be added later through an instrumented
AUSF build or an authorized authentication-path probe.
