#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CURL_IMAGE = os.environ.get("CURL_IMAGE", "curlimages/curl:8.10.1")
NETWORK = os.environ.get("OPEN5GS_NETWORK", "open5gs")
NRF_BASE = "http://nrf.open5gs.org:80"
AUSF_BASE = "http://ausf.open5gs.org:80"


def run(
    cmd: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def docker_ip(name: str) -> str:
    return run(
        [
            "docker",
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            name,
        ]
    ).stdout.strip()


def h2_get(url: str) -> str:
    return run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            NETWORK,
            CURL_IMAGE,
            "--http2-prior-knowledge",
            "-fsS",
            "--max-time",
            "6",
            "-H",
            "accept: application/json",
            url,
        ]
    ).stdout


def h2_post(url: str, body: dict[str, Any], timeout: int = 4) -> tuple[str, int]:
    payload = json.dumps(body, separators=(",", ":"))
    result = run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            NETWORK,
            CURL_IMAGE,
            "--http2-prior-knowledge",
            "-sS",
            "--max-time",
            str(timeout),
            "-H",
            "content-type: application/json",
            "-H",
            "accept: application/json",
            "-X",
            "POST",
            "--data-binary",
            "@-",
            "-w",
            "\n__HTTP_CODE__:%{http_code}\n",
            url,
        ],
        input_text=payload,
        check=False,
    )
    code = 0
    marker = "__HTTP_CODE__:"
    text = result.stdout
    if marker in text:
        data, tail = text.rsplit(marker, 1)
        text = data.strip()
        try:
            code = int(tail.strip().splitlines()[0])
        except (ValueError, IndexError):
            code = 0
    return text, code


def discovery() -> list[dict[str, Any]]:
    payload = json.loads(
        h2_get(
            f"{NRF_BASE}/nnrf-disc/v1/nf-instances"
            "?target-nf-type=UDM&requester-nf-type=AUSF"
        )
    )
    items = payload.get("nfInstances") if isinstance(payload, dict) else None
    return [item for item in (items or []) if isinstance(item, dict)]


def service_endpoint(instance: dict[str, Any]) -> str | None:
    for service in instance.get("nfServices") or []:
        if not isinstance(service, dict) or service.get("serviceName") != "nudm-ueau":
            continue
        for endpoint in service.get("ipEndPoints") or []:
            if not isinstance(endpoint, dict):
                continue
            host = endpoint.get("ipv4Address") or endpoint.get("ipv6Address")
            port = endpoint.get("port") or 80
            if host:
                return f"{host}:{port}"
    return None


def registered_endpoints() -> set[str]:
    endpoints: set[str] = set()
    for item in discovery():
        if str(item.get("nfStatus", "")).upper() != "REGISTERED":
            continue
        endpoint = service_endpoint(item)
        if endpoint:
            endpoints.add(endpoint)
    return endpoints


def instance_id_for_endpoint(endpoint: str) -> str | None:
    for item in discovery():
        if str(item.get("nfStatus", "")).upper() != "REGISTERED":
            continue
        if service_endpoint(item) == endpoint:
            value = item.get("nfInstanceId")
            return str(value) if value else None
    return None


def wait_endpoint(endpoint: str, present: bool = True, attempts: int = 50) -> None:
    for _ in range(attempts):
        try:
            if (endpoint in registered_endpoints()) == present:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(
        f"UDM endpoint condition not met: endpoint={endpoint}, present={present}"
    )


def auth_probe(tag: str, out: Path) -> tuple[float, int]:
    epoch = time.time()
    body = {
        "supiOrSuci": "suci-0-001-01-0-0-0-0000000001",
        "servingNetworkName": "5G:mnc001.mcc001.3gppnetwork.org",
    }
    response, code = h2_post(
        f"{AUSF_BASE}/nausf-auth/v1/ue-authentications",
        body,
        timeout=4,
    )
    (out / f"probe-{tag}.json").write_text(
        json.dumps(
            {"epoch": epoch, "status": code, "request": body, "response": response},
            indent=2,
        ),
        encoding="utf-8",
    )
    return epoch, code


def sample_phase(
    rows: list[dict[str, Any]],
    phase: str,
    endpoint: str,
    count: int,
    out: Path,
    recovery_active: int,
    update_first: int,
    replicate_id: int,
    observer_polls: list[dict[str, Any]],
) -> None:
    for index in range(count):
        # Read-only, real NRF discovery: capture the *availability interval*,
        # not a fabricated event-time that claims when registration happened.
        poll_start = time.time()
        observed_udms: list[str] = []
        poll_error: str | None = None
        try:
            observed_udms = sorted(registered_endpoints())
        except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
            poll_error = type(exc).__name__
        poll_end = time.time()
        epoch, code = auth_probe(f"{phase}-{index}", out)
        probe_end = time.time()
        observer_polls.append(
            {
                "run_id": f"real-legit-failover-{replicate_id}",
                "t": len(rows),
                "phase": phase,
                "expected_endpoint": endpoint,
                "registered_udm_endpoints": observed_udms,
                "poll_start_epoch": poll_start,
                "poll_end_epoch": poll_end,
                "probe_start_epoch": epoch,
                "probe_end_epoch": probe_end,
                "poll_error": poll_error,
                "origin_clock": "GitHub runner host wall clock / read-only NRF HTTP2",
                "provenance_attested": False,
            }
        )
        rows.append(
            {
                "run_id": f"real-legit-failover-{replicate_id}",
                "scenario": "real_legitimate_udm_failover",
                "seed": replicate_id,
                "t": len(rows),
                "epoch": f"{epoch:.6f}",
                "timestamp": datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
                "phase": phase,
                "probe_http_status": code,
                "label": 0,
                "attack_active": 0,
                "attack_start": -1,
                "nrf_endpoint": endpoint,
                "ausf_endpoint": "",
                "route_endpoint": "",
                "nrf_update_seen": update_first if index == 0 else 0,
                "notify_seen": 0,
                "notify_subscription_valid": 1,
                "notify_sender_trusted": 1,
                "recovery_active": recovery_active,
                "m_nrf": 1,
                "m_ausf": 0,
                "m_route": 0,
                "m_notify": 1,
            }
        )
        time.sleep(1)


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def experiment(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    replicate_id = int(os.environ.get("LAB_REPLICATE_ID", "0"))

    udm_a = f"{docker_ip('udm')}:80"
    wait_endpoint(udm_a, True)
    udm_a_instance_id = instance_id_for_endpoint(udm_a)

    rows: list[dict[str, Any]] = []
    observer_polls: list[dict[str, Any]] = []
    phase_epochs: dict[str, float] = {"baseline_start": time.time()}
    sample_phase(rows, "baseline", udm_a, 3, out, 0, 0, replicate_id, observer_polls)

    run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "udm-b",
            "--network",
            NETWORK,
            "--network-alias",
            "udm-b.open5gs.org",
            "-v",
            f"{Path.cwd() / 'lab/open5gs/udm-b.yaml'}:/etc/open5gs/custom/udm-b.yaml:ro",
            f"udm:{os.environ.get('OPEN5GS_VERSION', 'v2.7.7')}",
            "-c",
            "/etc/open5gs/custom/udm-b.yaml",
        ]
    )
    udm_b = f"{docker_ip('udm-b')}:80"
    wait_endpoint(udm_b, True)
    udm_b_instance_id = instance_id_for_endpoint(udm_b)

    run(["docker", "stop", "-t", "8", "udm"])
    wait_endpoint(udm_a, False)
    phase_epochs["failover_start"] = time.time()
    sample_phase(rows, "failover", udm_b, 5, out, 1, 1, replicate_id, observer_polls)

    run(["docker", "start", "udm"])
    wait_endpoint(udm_a, True)
    run(["docker", "stop", "-t", "8", "udm-b"])
    wait_endpoint(udm_b, False)
    phase_epochs["recovery_start"] = time.time()
    sample_phase(rows, "recovery", udm_a, 3, out, 1, 1, replicate_id, observer_polls)
    phase_epochs["experiment_end"] = time.time()

    write_rows(out / "observations-raw.csv", rows)
    with (out / "nrf-observer-polls.jsonl").open("w", encoding="utf-8") as fh:
        for record in observer_polls:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    meta = {
        "replicate_id": replicate_id,
        "nrf_ip": docker_ip("nrf"),
        "ausf_ip": docker_ip("ausf"),
        "udm_a": udm_a,
        "udm_b": udm_b,
        "udm_a_instance_id": udm_a_instance_id,
        "udm_b_instance_id": udm_b_instance_id,
        "rows": len(rows),
        "phase_epochs": phase_epochs,
        "safety": "legitimate NRF-visible UDM failover; no forged notifications",
    }
    (out / "failover-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run",))
    parser.add_argument("--out", default="artifacts/open5gs-failover")
    args = parser.parse_args()
    experiment(Path(args.out))


if __name__ == "__main__":
    main()
