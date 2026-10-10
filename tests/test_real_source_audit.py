from __future__ import annotations

import pytest

from nfnotify_lab.real_source_audit import audit_rows, load_polls


def _fixture():
    observations, polls, routes = [], {}, []
    for t in range(11):
        epoch = 100.0 + 10.0 * t
        key = ("real-legit-failover-0", t)
        observations.append({
            "run_id": key[0],
            "t": str(t),
            "phase": "baseline" if t < 3 else "failover",
            "epoch": str(epoch),
            "nrf_endpoint": "udm-a:80",
            "ausf_endpoint": "udm-a:80",
            "route_endpoint": "udm-a:80",
            "m_ausf": "1",
            "notify_seen": "0",
        })
        polls[key] = {
            "run_id": key[0],
            "t": t,
            "expected_endpoint": "udm-a:80",
            "registered_udm_endpoints": ["udm-a:80"],
            "poll_start_epoch": epoch - 2.0,
            "poll_end_epoch": epoch - 1.0,
            "probe_start_epoch": epoch,
            "probe_end_epoch": epoch + 2.0,
            "poll_error": None,
            "provenance_attested": False,
        }
        routes.append({
            "epoch": epoch + 0.5,
            "src": "ausf",
            "dst": "udm-a",
            "path": "/nudm-ueau/v1/generate-auth-data",
        })
    cache = [{"epoch": 95.0, "endpoint": "udm-a:80"}]
    return observations, polls, routes, cache


def _run(observations, polls, routes, cache, notifications=()):
    return audit_rows(
        observations, polls, routes, list(notifications), cache,
        nrf_ip="nrf", ausf_ip="ausf",
    )


def test_true_benign_provenance_meets_locked_coverage_and_never_attests():
    observations, polls, routes, cache = _fixture()
    points, summary = _run(observations, polls, routes, cache)
    assert len(points) == 11
    assert summary["eligible_rows"] == {"nrf": 11, "ausf": 11, "route": 11}
    assert summary["measurable_provenance_feasible"]
    assert not summary["provenance_cryptographically_attested"]
    assert not summary["context_detector_real_validation"]
    assert all(p["source_time_attested"] == 0 for p in points)
    assert all(p["route_origin_epoch"] <= p["score_cutoff_epoch"] for p in points)


def test_future_route_packet_is_rejected_not_backfilled():
    observations, polls, routes, cache = _fixture()
    routes = [r for r in routes if r["epoch"] != 100.5]
    routes.append({
        "epoch": 103.0,
        "src": "ausf",
        "dst": "udm-a",
        "path": "/nudm-ueau/v1/generate-auth-data",
    })
    points, outcome = _run(observations, polls, routes, cache)
    assert points[0]["route_origin_epoch"] is None
    assert points[0]["route_eligible"] == 0
    assert outcome["eligible_rows"]["route"] == 10


def test_future_cache_setup_does_not_become_historical_origin():
    observations, polls, routes, _ = _fixture()
    points, decision = _run(
        observations, polls, routes,
        [{"epoch": 103.0, "endpoint": "udm-a:80"}],
    )
    assert points[0]["ausf_origin_epoch"] is None
    assert points[0]["ausf_eligible"] == 0
    assert decision["eligible_rows"]["ausf"] == 10


def test_missing_or_duplicate_sidecar_join_fails_closed(tmp_path):
    observations, polls, routes, cache = _fixture()
    missing = dict(polls)
    missing.pop(("real-legit-failover-0", 3))
    with pytest.raises(ValueError, match="nonbijective"):
        _run(observations, missing, routes, cache)
    p = tmp_path / "polls.jsonl"
    import json

    sample = next(iter(polls.values()))
    p.write_text(json.dumps(sample) + "\n" + json.dumps(sample) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_polls(p)


def test_nrf_ambiguous_and_inconsistent_discovery_fails_coverage():
    observations, polls, routes, cache = _fixture()
    polls[("real-legit-failover-0", 0)]["registered_udm_endpoints"] = [
        "udm-a:80", "udm-b:80"
    ]
    points, verdict = _run(observations, polls, routes, cache)
    assert points[0]["nrf_eligible"] == 0
    assert not verdict["all_11_nrf_singleton_observed"]
    assert not verdict["measurable_provenance_feasible"]


def test_poll_future_interval_rejected():
    observations, polls, routes, cache = _fixture()
    polls[("real-legit-failover-0", 2)]["poll_end_epoch"] = 125.0
    points, result = _run(observations, polls, routes, cache)
    assert points[2]["nrf_eligible"] == 0
    assert not result["measurable_provenance_feasible"]


def test_notification_not_attested_or_inferred_from_future_packet():
    observations, polls, routes, cache = _fixture()
    observations[0]["notify_seen"] = "1"
    notifications = [{
        "epoch": 103.0, "src": "nrf", "dst": "ausf",
        "path": "/nnrf-nfm/v1/nf-status-notify",
    }]
    points, _ = _run(observations, polls, routes, cache, notifications)
    assert points[0]["notify_event_origin_epoch"] is None
    assert points[0]["notification_subscription_attested"] == 0


def test_no_observed_source_provenance_in_offline_counterfactual():
    from pathlib import Path
    import runpy

    namespace = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts"
            / "enrich_failover_observations.py")
    )
    observations, _, _, _ = _fixture()
    for item in observations:
        item.update({
            "label": "0",
            "attack_active": "0",
            "attack_start": "-1",
            "m_notify": "1",
            "notify_sender_trusted": "1",
            "notify_subscription_valid": "1",
            "nrf_update_seen": "0",
            "recovery_active": "0",
        })
    observations[3]["phase"] = "failover"
    result = namespace["make_counterfactual"](
        observations, baseline_endpoint="udm-a:80", replicate_id=0
    )
    assert result[3]["scenario"] == "counterfactual_real_state_divergence"
    assert "nrf_origin_epoch" not in result[3]
    assert "route_origin_epoch" not in result[3]
    assert result[3]["m_notify"] == "0"
