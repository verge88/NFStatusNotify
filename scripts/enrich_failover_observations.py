#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--routes", required=True)
    parser.add_argument("--notifications", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    rows = read_csv(Path(args.raw))
    routes = read_csv(Path(args.routes), delimiter="\t")
    notifications = read_csv(Path(args.notifications), delimiter="\t")
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))

    for row in rows:
        epoch = float(row["epoch"])
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
        "baseline_nrf": phase_values("nrf_endpoint", "baseline"),
        "baseline_ausf": phase_values("ausf_endpoint", "baseline"),
        "baseline_route": phase_values("route_endpoint", "baseline"),
        "failover_nrf": phase_values("nrf_endpoint", "failover"),
        "failover_ausf": phase_values("ausf_endpoint", "failover"),
        "failover_route": phase_values("route_endpoint", "failover"),
        "recovery_nrf": phase_values("nrf_endpoint", "recovery"),
        "recovery_ausf": phase_values("ausf_endpoint", "recovery"),
        "recovery_route": phase_values("route_endpoint", "recovery"),
    }
    out.with_name("evidence-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
