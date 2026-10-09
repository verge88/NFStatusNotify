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
AUSF_CALLBACK = "http://ausf.open5gs.org:80/nnrf-nfm/v1/nf-status-notify"


def run(cmd: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def docker_ip(name: str) -> str:
    result = run(
        [
            "docker",
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            name,
        ]
    )
    return result.stdout.strip()


def h2_get(url: str) -> str:
    result = run(
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
    )
    return result.stdout


def h2_post_json(url: str, payload: dict[str, Any]) -> tuple[str, int]:
    body = json.dumps(payload, separators=(",", ":"))
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
            "8",
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
        input_text=body,
        check=False,
    )
    marker = "__HTTP_CODE__:"
    code = 0
    text = result.stdout
    if marker in text:
        payload_text, tail = text.rsplit(marker, 1)
        text = payload_text.strip()
        try:
            code = int(tail.strip().splitlines()[0])
        except (ValueError, IndexError):
            code = 0
    if result.returncode != 0:
        raise RuntimeError(f"curl POST failed: {result.stderr.strip()}")
    return text, code


def discovery(nf_type: str, requester: str) -> tuple[dict[str, Any], str]:
    url = (
        f"{NRF_BASE}/nnrf-disc/v1/nf-instances"
        f"?target-nf-type={nf_type}&requester-nf-type={requester}"
    )
    raw = h2_get(url)
    return json.loads(raw), raw


def instances(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        value = payload.get("nfInstances")
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        for child in payload.values():
            found = instances(child)
            if found:
                return found
    if isinstance(payload, list):
        dicts = [x for x in payload if isinstance(x, dict) and "nfInstanceId" in x]
        if dicts:
            return dicts
        for child in payload:
            found = instances(child)
            if found:
                return found
    return []


def first_instance(payload: Any, nf_type: str) -> dict[str, Any] | None:
    candidates = instances(payload)
    for item in candidates:
        if str(item.get("nfType", "")).upper() == nf_type.upper():
            return item
    return candidates[0] if candidates else None


def endpoint(instance: dict[str, Any] | None) -> str | None:
    if not instance:
        return None
    services = instance.get("nfServices") or []
    ordered = sorted(
        [s for s in services if isinstance(s, dict)],
        key=lambda s: 0 if s.get("serviceName") == "nudm-ueau" else 1,
    )
    for service in ordered:
        for ip_ep in service.get("ipEndPoints") or []:
            if not isinstance(ip_ep, dict):
                continue
            host = ip_ep.get("ipv4Address") or ip_ep.get("ipv6Address")
            port = ip_ep.get("port")
            if host:
                return f"{host}:{port}" if port else str(host)
    addrs = instance.get("ipv4Addresses") or instance.get("ipv6Addresses") or []
    if addrs:
        return str(addrs[0])
    return instance.get("fqdn")


def wait_for(nf_type: str, requester: str, attempts: int = 60) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            payload, _ = discovery(nf_type, requester)
            inst = first_instance(payload, nf_type)
            if inst and str(inst.get("nfStatus", "")).upper() == "REGISTERED":
                return inst
        except Exception as exc:
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"{nf_type} did not become REGISTERED; last_error={last_error}")


def create_subscription(out: Path) -> dict[str, Any]:
    ausf = wait_for("AUSF", "UDM")
    ausf_id = str(ausf["nfInstanceId"])
    body = {
        "nfStatusNotificationUri": AUSF_CALLBACK,
        "reqNfInstanceId": ausf_id,
        "reqNfType": "AUSF",
        "subscrCond": {"nfType": "UDM"},
        "reqNotifEvents": ["NF_REGISTERED", "NF_DEREGISTERED"],
    }
    response, code = h2_post_json(f"{NRF_BASE}/nnrf-nfm/v1/subscriptions", body)
    (out / "subscription-request.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
    (out / "subscription-response.txt").write_text(response + "\n", encoding="utf-8")
    if code != 201:
        raise RuntimeError(f"NRF subscription creation returned HTTP {code}: {response}")
    return {"ausf_instance_id": ausf_id, "http_status": code}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("no observations")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def lab_run(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    snapshots = out / "nrf-snapshots"
    snapshots.mkdir(exist_ok=True)

    nrf_ip = docker_ip("nrf")
    ausf_ip = docker_ip("ausf")
    udm_ip = docker_ip("udm")

    initial_udm = wait_for("UDM", "AUSF")
    wait_for("AUSF", "UDM")
    subscription = create_subscription(out)

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"real-udm-recovery-{run_stamp}"
    rows: list[dict[str, Any]] = []
    previous_state: tuple[str | None, str | None] | None = None
    t = 0

    def sample(phase: str, recovery_active: int) -> None:
        nonlocal t, previous_state
        epoch = time.time()
        timestamp = datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
        try:
            payload, raw = discovery("UDM", "AUSF")
            nrf_available = 1
        except Exception as exc:
            payload = {}
            raw = json.dumps({"query_error": str(exc)})
            nrf_available = 0

        (snapshots / f"{t:03d}-{phase}.json").write_text(raw, encoding="utf-8")
        inst = first_instance(payload, "UDM") if nrf_available else None
        current_endpoint = endpoint(inst)
        status = str(inst.get("nfStatus")) if inst else None
        state = (current_endpoint, status)
        changed = int(previous_state is not None and state != previous_state)
        previous_state = state

        rows.append(
            {
                "run_id": run_id,
                "scenario": "real_udm_recovery",
                "seed": 0,
                "t": t,
                "epoch": f"{epoch:.6f}",
                "timestamp": timestamp,
                "phase": phase,
                "label": 0,
                "attack_active": 0,
                "attack_start": -1,
                "nrf_endpoint": current_endpoint or "",
                "ausf_endpoint": "",
                "route_endpoint": "",
                "nrf_update_seen": changed if nrf_available else "",
                "notify_seen": "",
                "notify_subscription_valid": "",
                "notify_sender_trusted": "",
                "recovery_active": recovery_active,
                "m_nrf": nrf_available,
                "m_ausf": 0,
                "m_route": 0,
                "m_notify": 0,
            }
        )
        t += 1

    for _ in range(4):
        sample("baseline", 0)
        time.sleep(2)

    run(["docker", "stop", "-t", "8", "udm"])
    for _ in range(7):
        sample("udm_down", 1)
        time.sleep(2)

    run(["docker", "start", "udm"])
    for _ in range(9):
        sample("udm_recovery", 1)
        time.sleep(2)

    recovered = wait_for("UDM", "AUSF", attempts=20)
    sample("recovered", 0)

    write_csv(out / "observations.csv", rows)
    meta = {
        "run_id": run_id,
        "open5gs_version": os.environ.get("OPEN5GS_VERSION", "v2.7.7"),
        "nrf_ip": nrf_ip,
        "ausf_ip": ausf_ip,
        "udm_ip": udm_ip,
        "initial_udm_instance_id": initial_udm.get("nfInstanceId"),
        "recovered_udm_instance_id": recovered.get("nfInstanceId"),
        "subscription": subscription,
        "samples": len(rows),
        "safety": "legitimate NRF subscription plus UDM stop/restart; no forged NFStatusNotify payload",
    }
    (out / "lab-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run",))
    parser.add_argument("--out", default="artifacts/open5gs-real")
    args = parser.parse_args()
    if args.command == "run":
        lab_run(Path(args.out))


if __name__ == "__main__":
    main()
