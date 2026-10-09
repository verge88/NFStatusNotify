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
    missing_sources: tuple[str, ...] = ()
    missing_probability: float = 0.0


DEFAULT_SCENARIOS: tuple[Scenario, ...] = (
    Scenario("stable"),
    Scenario("legit_update", legit_update_at=35, notify_delay=1),
    Scenario("delayed_notify", legit_update_at=35, notify_delay=8),
    Scenario("udm_recovery", recovery_start=30, recovery_end=45),
    Scenario("forged_notify", attack=True, forged_notify_at=35),
    Scenario(
        "forged_notify_missing",
        attack=True,
        forged_notify_at=35,
        missing_sources=("notify",),
        missing_probability=0.65,
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


def simulate_run(
    scenario: Scenario,
    seed: int,
    steps: int = 90,
) -> pd.DataFrame:
    """Generate one isolated, synthetic observation run.

    The forged-notification scenario reproduces only the *state consequence* of
    cache poisoning inside the simulator. It does not send traffic to Open5GS or
    craft an exploit payload.
    """
    rng = np.random.default_rng(seed)
    nrf_endpoint = LEGIT_UDM
    ausf_endpoint = LEGIT_UDM
    route_endpoint = LEGIT_UDM
    target_endpoint = LEGIT_UDM

    rows: list[dict[str, object]] = []
    for t in range(steps):
        nrf_update_seen = 0
        notify_seen = 0
        notify_subscription_valid = 1
        notify_sender_trusted = 1
        recovery_active = 0
        attack_active = 0

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

        if scenario.forged_notify_at is not None and t >= scenario.forged_notify_at:
            attack_active = 1

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
                "attack_start": scenario.forged_notify_at if scenario.attack else -1,
                "nrf_endpoint": nrf_endpoint if nrf_available else None,
                "ausf_endpoint": ausf_endpoint if ausf_available else None,
                "route_endpoint": route_endpoint if route_available else None,
                "nrf_update_seen": nrf_update_seen if nrf_available else np.nan,
                "notify_seen": notify_seen if notify_available else np.nan,
                "notify_subscription_valid": (
                    notify_subscription_valid if notify_available else np.nan
                ),
                "notify_sender_trusted": notify_sender_trusted if notify_available else np.nan,
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
