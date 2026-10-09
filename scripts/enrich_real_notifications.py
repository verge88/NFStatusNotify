#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_rows(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=delimiter))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", required=True)
    parser.add_argument("--notifications", required=True)
    parser.add_argument("--meta", required=True)
    args = parser.parse_args()

    observations_path = Path(args.observations)
    notifications_path = Path(args.notifications)
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    observations = read_rows(observations_path)

    for row in observations:
        row["m_notify"] = "1"
        row["notify_seen"] = "0"
        row["notify_subscription_valid"] = "1"
        row["notify_sender_trusted"] = "1"

    notifications: list[dict[str, str]] = []
    if notifications_path.exists() and notifications_path.stat().st_size:
        notifications = read_rows(notifications_path, delimiter="\t")

    trusted = 0
    matched = 0
    nrf_ip = meta["nrf_ip"]
    ausf_ip = meta["ausf_ip"]

    for packet in notifications:
        path = packet.get("http2.headers.path", "")
        if "nf-status-notify" not in path:
            continue
        try:
            event_epoch = float(packet.get("frame.time_epoch", ""))
        except ValueError:
            continue
        if not observations:
            continue

        nearest = min(observations, key=lambda row: abs(float(row["epoch"]) - event_epoch))
        distance = abs(float(nearest["epoch"]) - event_epoch)
        if distance > 3.5:
            continue

        src = packet.get("ip.src", "")
        dst = packet.get("ip.dst", "")
        is_trusted = src == nrf_ip and dst == ausf_ip
        nearest["notify_seen"] = "1"
        nearest["notify_sender_trusted"] = "1" if is_trusted else "0"
        nearest["notify_subscription_valid"] = "1"
        matched += 1
        if is_trusted:
            trusted += 1

    write_rows(observations_path, observations)
    summary = {
        "notification_frames": matched,
        "trusted_nrf_to_ausf_frames": trusted,
        "pcap_rows_decoded": len(notifications),
        "nrf_ip": nrf_ip,
        "ausf_ip": ausf_ip,
        "observation_rows": len(observations),
    }
    observations_path.with_name("notification-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
