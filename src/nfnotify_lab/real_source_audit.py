"""Real Open5GS passive evidence provenance audit, not detector-grade attestation.

All times are observations of events or completed polls from runner/container
clocks, not cryptographically guaranteed source origination timestamps.
The actual notification subscription validity cannot be inferred from pcap.
"""
from __future__ import annotations

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


def csv_rows(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=delimiter))


def cache_setup_events(path: Path, year: int) -> list[dict]:
    result = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = SETUP_RE.search(line)
        if m is None:
            continue
        ts = datetime(
            year,
            int(m["month"]), int(m["day"]), int(m["hour"]),
            int(m["minute"]), int(m["second"]), int(m["millis"]) * 1000,
            tzinfo=timezone.utc,
        ).timestamp()
        result.append({"epoch": ts, "endpoint": m["endpoint"]})
    return sorted(result, key=lambda item: item["epoch"])


def packet_events(path: Path) -> list[dict]:
    events = []
    for row in csv_rows(path, delimiter="\t"):
        try:
            epoch = float(row["frame.time_epoch"])
        except (ValueError, TypeError, KeyError):
            continue
        events.append({
            "epoch": epoch,
            "src": row.get("ip.src", ""),
            "dst": row.get("ip.dst", ""),
            "path": row.get("http2.headers.path", ""),
        })
    return events


def load_polls(path: Path) -> dict[tuple[str, int], dict]:
    polls = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (str(row["run_id"]), int(row["t"]))
        if key in polls:
            raise ValueError(f"duplicate source poll key: {key}")
        polls[key] = row
    return polls


def nearest_eligible_route(
    packets: list[dict], start: float, end: float, enriched_endpoint: str,
) -> dict | None:
    matches = [
        p for p in packets
        if start <= p["epoch"] <= end
        and p["dst"] + ":80" == enriched_endpoint
        and "generate-auth-data" in p["path"]
    ]
    return min(matches, key=lambda x: abs(x["epoch"] - start)) if matches else None


def audit_rows(
    observations: list[dict[str, str]],
    polls: dict[tuple[str, int], dict],
    route_events: list[dict],
    notification_events: list[dict],
    cache_events: list[dict],
    *,
    nrf_ip: str,
    ausf_ip: str,
) -> tuple[list[dict], dict]:
    actual = {(row["run_id"], int(row["t"])) for row in observations}
    if len(actual) != len(observations):
        raise ValueError("duplicate real observation key")
    if set(polls) != actual:
        raise ValueError(
            f"nonbijective observer poll join: missing={len(actual - set(polls))}, "
            f"extra={len(set(polls) - actual)}"
        )

    result = []
    monotonic = True
    last_cutoff = {}
    for observation in observations:
        key = (observation["run_id"], int(observation["t"]))
        poll = polls[key]
        start = float(poll["probe_start_epoch"])
        end = float(poll["probe_end_epoch"])
        nrf_start = float(poll["poll_start_epoch"])
        nrf_end = float(poll["poll_end_epoch"])
        row_epoch = float(observation["epoch"])
        monotonic &= key[0] not in last_cutoff or (
            end >= last_cutoff[key[0]]
        )
        last_cutoff[key[0]] = end

        expected = observation["nrf_endpoint"]
        discovered = sorted(set(poll.get("registered_udm_endpoints") or []))
        nrf_verified = bool(
            poll.get("poll_error") is None
            and poll.get("provenance_attested") is False
            and nrf_start <= nrf_end <= start <= end
            and abs(start - row_epoch) <= 0.1
            and poll["expected_endpoint"] == expected
            and discovered == [expected]
        )
        nrf_origin = nrf_end if nrf_verified else None

        valid_cache = [
            ev for ev in cache_events
            if ev["epoch"] <= end
        ]
        latest_cache = valid_cache[-1] if valid_cache else None
        ausf_verified = bool(
            latest_cache is not None
            and latest_cache["endpoint"] == observation["ausf_endpoint"]
            and observation["m_ausf"] == "1"
        )
        ausf_origin = latest_cache["epoch"] if ausf_verified else None

        route = nearest_eligible_route(
            route_events, start, end, observation["route_endpoint"]
        )
        route_origin = route["epoch"] if route is not None else None

        # A NOTIFY event is a packet observation, not proof of genuine signing
        # or subscription authorization.
        notification = [
            ev for ev in notification_events
            if ev["epoch"] <= end
            and end - ev["epoch"] <= 5.0
            and ev["src"] == nrf_ip and ev["dst"] == ausf_ip
            and "nf-status-notify" in ev["path"]
        ]
        notification_origin = (
            max(notification, key=lambda x: x["epoch"])["epoch"]
            if observation["notify_seen"] == "1" and notification else None
        )
        chosen = {
            "nrf": nrf_origin,
            "ausf": ausf_origin,
            "route": route_origin,
        }
        invalid_future = sum(
            origin is not None and origin > end
            for origin in (*chosen.values(), notification_origin)
        )
        if invalid_future:
            raise AssertionError(f"future evidence included in {key}")
        result.append({
            "run_id": key[0],
            "t": key[1],
            "phase": observation["phase"],
            "score_cutoff_epoch": end,
            "nrf_poll_start_epoch": nrf_start,
            "nrf_poll_end_epoch": nrf_end,
            "nrf_registered_endpoint_set": ";".join(discovered),
            "nrf_expected_endpoint": expected,
            "nrf_origin_epoch": nrf_origin,
            "nrf_eligible": int(nrf_verified),
            "nrf_age_seconds": end - nrf_origin if nrf_origin is not None else None,
            "nrf_failure_reason": (
                "" if nrf_verified else (
                    poll.get("poll_error") or "ambiguous_or_noncausal_discovery"
                )
            ),
            "ausf_origin_epoch": ausf_origin,
            "ausf_eligible": int(ausf_verified),
            "ausf_age_seconds": end - ausf_origin if ausf_origin is not None else None,
            "ausf_failure_reason": "" if ausf_verified else "no_matching_past_cache_event",
            "route_origin_epoch": route_origin,
            "route_eligible": int(route is not None),
            "route_age_seconds": end - route_origin if route_origin is not None else None,
            "route_failure_reason": "" if route is not None else "no_matching_packet_in_probe_interval",
            "notify_event_origin_epoch": notification_origin,
            "notification_subscription_attested": 0,
            "recovery_label_source": "orchestrator_not_independent",
            "source_time_attested": 0,
            "eligible_future_count": invalid_future,
        })

    coverage = {
        source: sum(row[f"{source}_eligible"] for row in result)
        for source in ("nrf", "ausf", "route")
    }
    count = len(result)
    coverage_ok = count == 11 and all(x >= 9 for x in coverage.values())
    timestamps_ok = monotonic and all(
        row["eligible_future_count"] == 0 for row in result
    )
    poll_matches = all(row["nrf_eligible"] == 1 for row in result)
    outcome = {
        "rows": count,
        "eligible_rows": coverage,
        "eligible_origin_after_cutoff": sum(
            row["eligible_future_count"] for row in result
        ),
        "monotonic_probe_cutoffs": monotonic,
        "all_11_nrf_singleton_observed": poll_matches,
        "valid_one_to_one_poll_join": True,
        "coverage_threshold_each": 9,
        "coverage_pass": coverage_ok,
        "causal_timestamps_pass": timestamps_ok,
        "measurable_provenance_feasible": bool(
            coverage_ok and timestamps_ok and poll_matches
        ),
        "provenance_cryptographically_attested": False,
        "recovery_context_independently_trusted": False,
        "context_detector_real_validation": False,
        "real_attack_injection_executed": False,
        "scope": "single genuine benign A-to-B-to-A failover, passive collection",
        "known_clock_limitation": (
            "Host pcap event and container cache-log timestamps assumed on compatible "
            "UTC clocks; no signed source-origin time or clock-offset bound"
        ),
        "counterfactual_provenance_laundered": False,
    }
    return result, outcome


def run_audit(
    observations: Path, polls: Path, routes: Path,
    notifications: Path, ausf_log: Path, meta: Path,
) -> tuple[list[dict], dict]:
    rows = csv_rows(observations)
    cfg = json.loads(meta.read_text(encoding="utf-8"))
    year = datetime.fromisoformat(rows[0]["timestamp"]).year
    return audit_rows(
        rows, load_polls(polls),
        packet_events(routes), packet_events(notifications),
        cache_setup_events(ausf_log, year),
        nrf_ip=cfg["nrf_ip"], ausf_ip=cfg["ausf_ip"],
    )


def write_audit(path: Path, rows: list[dict], decision: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with (path / "source-time-audit.csv").open(
        "w", newline="", encoding="utf-8"
    ) as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (path / "source-time-decision.json").write_text(
        json.dumps(decision, indent=2), encoding="utf-8"
    )
