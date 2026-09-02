"""The production worker foundry records lifecycle on the durable bus.

Organ 12. `WorkerFoundryAuthority` has always accepted a `bus=` and `_set_state`
has always appended a `CanonicalEvent` to it -- but `aios/api/deps.py::
get_worker_foundry` never passed one. So the FastAPI-facing singleton dropped
every worker admission and lifecycle transition on restart, while
`CouncilOrchestrator` -- which does pass `bus=self.bus` -- kept them. One organ,
two production paths, only one of them durable.

The 2026-09-01 ledger recount is what surfaced it: organ 12 could not honestly
discharge C3/C4 as "owns no durable store" while a durability seam existed and
was simply unwired. An N/A-BY-DESIGN there would have recorded the inconsistency
as a design decision. Wiring it is the honest fix.

This test pins the WIRING, not the environment. `get_cortex_observation_bus()`
returns the app-lifespan global, which is None until startup runs, so asserting
on a real bus here would assert something about the harness rather than about
`deps.py`. Instead the accessor is replaced with one returning a real
`CortexBus`, and the foundry is required to carry it through.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.api import deps
from aios.runtime.cortex_bus import CortexBus


@pytest.fixture(autouse=True)
def _reset_foundry_singleton():
    """`_worker_foundry` is a cached global; a stale one hides the wiring."""
    deps._worker_foundry = None
    yield
    deps._worker_foundry = None


def test_the_production_foundry_is_built_with_the_observation_bus(
    tmp_path: Path, monkeypatch
) -> None:
    """The fix: whatever the accessor yields must reach the foundry."""
    bus = CortexBus(db_path=tmp_path / "cortex.db")
    monkeypatch.setattr(deps, "get_cortex_observation_bus", lambda: bus)

    foundry = deps.get_worker_foundry(emergency_stop=deps.get_emergency_stop())

    assert foundry._bus is bus, (
        "deps.get_worker_foundry built the production WorkerFoundry without the "
        "cortex observation bus, so worker admission and lifecycle transitions "
        "are dropped on restart"
    )


def test_a_foundry_without_a_bus_is_still_constructible(
    tmp_path: Path, monkeypatch
) -> None:
    """The bus stays optional -- wiring it must not make startup fail-hard.

    `get_cortex_observation_bus()` returns None before app startup and whenever
    AIOS_CORTEX_BUS is disabled. The foundry must tolerate that rather than
    raising, or a disabled bus would take the API down.
    """
    monkeypatch.setattr(deps, "get_cortex_observation_bus", lambda: None)

    foundry = deps.get_worker_foundry(emergency_stop=deps.get_emergency_stop())

    assert foundry is not None
    assert foundry._bus is None
