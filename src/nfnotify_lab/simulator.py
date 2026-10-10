from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd


LEGIT_UDM = "udm-a"
ALT_UDM = "udm-b"
ROGUE_UDM = "udm-x"


@dataclass(frozen=True)
class Scenario:
    name: str
    attack: bool = False
    legit_update_at: int | None = None
    notify_delay: int = 1
    recovery_start: int | None = None
    recovery_end: int | None = None
    forged_notify_at: int | None = None
    silent_divergence_at: int | None = None
    silent_divergence_sources: tuple[str, ...] = ()
    observer_skew_at: int | None = None
    observer_skew_duration: int = 0
    observer_skew_sources: tuple[str, ...] = ()
    missing_sources: tuple[str, ...] = ()
    missing_probability: float = 0.0


DEFAULT_SCENARIOS: tuple[Scenario, ...] = (
    Scenario("stable"),
    Scenario("legit_update", legit_update_at=35, notify_delay=1),
    Scenario("delayed_notify", legit_update_at=35, notify_delay=8),
    Scenario("udm_recovery", recovery_start=30, recovery_end=45),
    Scenario(
        "cache_observer_skew",
        observer_skew_at=30,
        observer_skew_duration=6,
        observer_skew_sources=("ausf",),
    ),
    Scenario(
        "route_observer_skew",
        observer_skew_at=30,
        observer_skew_duration=6,
        observer_skew_sources=("route",),
    ),
    Scenario("forged_notify", attack=True, forged_notify_at=35),
    Scenario(
        "forged_notify_missing",
        attack=True,
        forged_notify_at=35,
        missing_sources=("notify",),
        missing_probability=0.65,
    ),
    Scenario(
        "silent_dual_divergence",
        attack=True,
        silent_divergence_at=35,
        silent_divergence_sources=("ausf", "route"),
    ),
    Scenario(
        "persistent_cache_divergence",
        attack=True,
        silent_divergence_at=35,
        silent_divergence_sources=("ausf",),
    ),
    Scenario(
        "persistent_route_divergence",
        attack=True,
        silent_divergence_at=35,
        silent_divergence_sources=("route",),
    ),
    Scenario(
        "legit_update_missing",
        legit_update_at=35,
        notify_delay=4,
        missing_sources=("nrf", "notify"),
        missing_probability=0.35,
    ),
)


def _drop(rng: np.random.Generator, source: str, scenario: Scenario) -> bool:
    return source in scenario.missing_sources and rng.random() < scenario.missing_probability


def _attack_start(scenario: Scenario) -> int | None:
    if scenario.forged_notify_at is not None:
        return scenario.forged_notify_at
    return scenario.silent_divergence_at


def _observer_skew_active(scenario: Scenario, t: int) -> bool:
    if scenario.observer_skew_at is None or scenario.observer_skew_duration <= 0:
        return False
    return scenario.observer_skew_at <= t < (
        scenario.observer_skew_at + scenario.observer_skew_duration
    )


def simulate_run(
    scenario: Scenario,
    seed: int,
    steps: int = 90,
) -> pd.DataFrame:
    """Generate one isolated, synthetic observation run.

    Attack scenarios reproduce only state consequences inside the simulator.
    They do not send traffic to Open5GS or craft an exploit payload.

    Observer-skew scenarios alter only the reported AUSF/route observation for
    a short benign window while the underlying simulated state stays unchanged.
    """
    rng = np.random.default_rng(seed)
    nrf_endpoint = LEGIT_UDM
    ausf_endpoint = LEGIT_UDM
    route_endpoint = LEGIT_UDM
    target_endpoint = LEGIT_UDM
    attack_start = _attack_start(scenario)

    rows: list[dict[str, object]] = []
    for t in range(steps):
        nrf_update_seen = 0
        notify_seen = 0
        notify_subscription_valid = 1
        notify_sender_trusted = 1
        recovery_active = 0
        attack_active = int(attack_start is not None and t >= attack_start)

        if scenario.legit_update_at is not None and t == scenario.legit_update_at:
            target_endpoint = ALT_UDM
            nrf_endpoint = target_endpoint
            nrf_update_seen = 1

        if scenario.legit_update_at is not None:
            notify_t = scenario.legit_update_at + scenario.notify_delay
            if t == notify_t:
                notify_seen = 1
                ausf_endpoint = target_endpoint
                route_endpoint = target_endpoint

        if scenario.recovery_start is not None and scenario.recovery_end is not None:
            if scenario.recovery_start <= t < scenario.recovery_end:
                recovery_active = 1
                if t == scenario.recovery_start:
                    route_endpoint = ""
            elif t == scenario.recovery_end:
                route_endpoint = nrf_endpoint
                ausf_endpoint = nrf_endpoint

        if scenario.forged_notify_at is not None and t == scenario.forged_notify_at:
            notify_seen = 1
            notify_subscription_valid = 0
            notify_sender_trusted = 0
            ausf_endpoint = ROGUE_UDM
            route_endpoint = ROGUE_UDM

        if (
            scenario.silent_divergence_at is not None
            and t == scenario.silent_divergence_at
        ):
            if "ausf" in scenario.silent_divergence_sources:
                ausf_endpoint = ROGUE_UDM
            if "route" in scenario.silent_divergence_sources:
                route_endpoint = ROGUE_UDM

        observed_ausf = ausf_endpoint
        observed_route = route_endpoint
        if _observer_skew_active(scenario, t):
            if "ausf" in scenario.observer_skew_sources:
                observed_ausf = ALT_UDM
            if "route" in scenario.observer_skew_sources:
                observed_route = ALT_UDM

        nrf_available = int(not _drop(rng, "nrf", scenario))
        ausf_available = int(not _drop(rng, "ausf", scenario))
        route_available = int(not _drop(rng, "route", scenario))
        notify_available = int(not _drop(rng, "notify", scenario))

        rows.append(
            {
                "run_id": f"{scenario.name}-{seed}",
                "scenario": scenario.name,
                "seed": seed,
                "t": t,
                "label": int(scenario.attack),
                "attack_active": attack_active,
                "attack_start": attack_start if scenario.attack else -1,
                "nrf_endpoint": nrf_endpoint if nrf_available else None,
                "ausf_endpoint": observed_ausf if ausf_available else None,
                "route_endpoint": observed_route if route_available else None,
                "nrf_update_seen": nrf_update_seen if nrf_available else np.nan,
                "notify_seen": notify_seen if notify_available else np.nan,
                "notify_subscription_valid": (
                    notify_subscription_valid if notify_available else np.nan
                ),
                "notify_sender_trusted": (
                    notify_sender_trusted if notify_available else np.nan
                ),
                "recovery_active": recovery_active,
                "m_nrf": nrf_available,
                "m_ausf": ausf_available,
                "m_route": route_available,
                "m_notify": notify_available,
            }
        )

    return pd.DataFrame(rows)


def simulate_dataset(
    scenarios: Iterable[Scenario] = DEFAULT_SCENARIOS,
    seeds: Iterable[int] = range(100),
    steps: int = 90,
) -> pd.DataFrame:
    frames = [simulate_run(s, seed=seed, steps=steps) for s in scenarios for seed in seeds]
    return pd.concat(frames, ignore_index=True)
