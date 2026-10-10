#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SETUP_RE = re.compile(
    r"(?P<month>\d{2})/(?P<day>\d{2}) "
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<millis>\d{3}).*"
    r"Setup NF EndPoint\(addr\) \[(?P<endpoint>[^\]]+)\]"
)


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def nearest(rows: list[dict[str, str]], epoch: float, limit: float) -> dict[str, str] | None:
    candidates: list[tuple[float, dict[str, str]]] = []
    for row in rows:
        try:
            distance = abs(float(row.get("frame.time_epoch", "")) - epoch)
        except ValueError:
            continue
        if distance <= limit:
            candidates.append((distance, row))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def cache_events(path: Path, year: int, allowed: set[str]) -> list[tuple[float, str]]:
    events: list[tuple[float, str]] = []
    for line in path.read_text(errors="replace").splitlines():
        match = SETUP_RE.search(line)
        if not match:
            continue
        endpoint = match.group("endpoint")
        if endpoint not in allowed:
            continue
        dt = datetime(
            year,
            int(match.group("month")),
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second")),
            int(match.group("millis")) * 1000,
            tzinfo=timezone.utc,
        )
        events.append((dt.timestamp(), endpoint))
    return sorted(events)


def latest_cache(events: list[tuple[float, str]], epoch: float) -> str | None:
    candidates = [event for event in events if event[0] <= epoch + 0.5]
    return candidates[-1][1] if candidates else None


def make_counterfactual(
    rows: list[dict[str, str]],
    baseline_endpoint: str,
    replicate_id: int,
) -> list[dict[str, str]]:
    attack_start = min(int(row["t"]) for row in rows if row["phase"] == "failover")
    counter: list[dict[str, str]] = []
    for source in rows:
        row = dict(source)
        row["run_id"] = f"counterfactual-real-effect-{replicate_id}"
        row["scenario"] = "counterfactual_real_state_divergence"
        row["attack_start"] = str(attack_start)

        if row["phase"] == "failover":
            row["label"] = "1"
            row["attack_active"] = "1"
            row["nrf_endpoint"] = baseline_endpoint
            row["nrf_update_seen"] = "0"
            row["recovery_active"] = "0"

            # Missing notification telemetry: no synthetic sender/status claims.
            row["m_notify"] = "0"
            row["notify_seen"] = ""
            row["notify_subscription_valid"] = ""
            row["notify_sender_trusted"] = ""
        else:
            row["label"] = "0"
            row["attack_active"] = "0"

        counter.append(row)
    return counter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--routes", required=True)
    parser.add_argument("--notifications", required=True)
    parser.add_argument("--ausf-log", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--counterfactual", required=True)
    args = parser.parse_args()

    rows = read_csv(Path(args.raw))
    routes = read_csv(Path(args.routes), delimiter="\t")
    notifications = read_csv(Path(args.notifications), delimiter="\t")
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))

    first_dt = datetime.fromisoformat(rows[0]["timestamp"])
    allowed = {meta["udm_a"], meta["udm_b"]}
    cache = cache_events(Path(args.ausf_log), first_dt.year, allowed)
    if not cache:
        raise RuntimeError("no UDM cache endpoint events found in AUSF log")

    for row in rows:
        epoch = float(row["epoch"])

        ausf_endpoint = latest_cache(cache, epoch)
        if ausf_endpoint:
            row["ausf_endpoint"] = ausf_endpoint
            row["m_ausf"] = "1"
        else:
            row["ausf_endpoint"] = ""
            row["m_ausf"] = "0"

        route = nearest(routes, epoch, 5.0)
        if route and route.get("ip.dst"):
            row["route_endpoint"] = f"{route['ip.dst']}:80"
            row["m_route"] = "1"
        else:
            row["route_endpoint"] = ""
            row["m_route"] = "0"

        notify = nearest(notifications, epoch, 4.0)
        if notify:
            row["notify_seen"] = "1"
            row["notify_sender_trusted"] = (
                "1"
                if notify.get("ip.src") == meta["nrf_ip"]
                and notify.get("ip.dst") == meta["ausf_ip"]
                else "0"
            )
            row["notify_subscription_valid"] = "1"
        else:
            row["notify_seen"] = "0"
            row["notify_sender_trusted"] = "1"
            row["notify_subscription_valid"] = "1"

    out = Path(args.out)
    write_csv(out, rows)

    counter = make_counterfactual(
        rows,
        baseline_endpoint=meta["udm_a"],
        replicate_id=int(meta.get("replicate_id", 0)),
    )
    write_csv(Path(args.counterfactual), counter)

    def phase_values(column: str, phase: str) -> list[str]:
        return sorted(
            {
                row[column]
                for row in rows
                if row["phase"] == phase and row.get(column)
            }
        )

    summary = {
        "udm_a": meta["udm_a"],
        "udm_b": meta["udm_b"],
        "cache_events": [
            {"epoch": epoch, "endpoint": endpoint} for epoch, endpoint in cache
        ],
        "baseline_nrf": phase_values("nrf_endpoint", "baseline"),
        "baseline_ausf": phase_values("ausf_endpoint", "baseline"),
        "baseline_route": phase_values("route_endpoint", "baseline"),
        "failover_nrf": phase_values("nrf_endpoint", "failover"),
        "failover_ausf": phase_values("ausf_endpoint", "failover"),
        "failover_route": phase_values("route_endpoint", "failover"),
        "recovery_nrf": phase_values("nrf_endpoint", "recovery"),
        "recovery_ausf": phase_values("ausf_endpoint", "recovery"),
        "recovery_route": phase_values("route_endpoint", "recovery"),
        "counterfactual_method": (
            "real AUSF/route retained; NRF frozen to pre-failover UDM-A during "
            "failover; notification source marked unavailable"
        ),
    }
    out.with_name("evidence-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
