"""GAGOS's workshop writers run through the Worker Foundry (2026-11-10).

The consistency plan of 2026-11-04 asked for one engine for work. The workshop
ran its writers on a thread pool of its own; each is now a worker the Foundry
admits. Pinned here, with fake writers and no model:

* an engaged emergency stop admits no writer, and says so;
* writers run side by side, never more than the workshop's bound at once;
* each writer's lifecycle reaches the bus (requested to dissolved), named by
  the writer and the files it writes;
* one writer's failure never stops the others, and a writer past its timeout
  fails and frees its slot.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Any

from aios.application.workers.workshop_foundry import (
    WorkshopFoundry,
    WorkshopWriterTimedOut,
    WriterLeg,
)
from aios.core.events import CanonicalEventType


class _Stop:
    def __init__(self, engaged: bool = False) -> None:
        self.engaged = engaged

    def assert_operational(self) -> None:
        if self.engaged:
            raise RuntimeError("emergency stop engaged")


class _Bus:
    def __init__(self) -> None:
        self.events: list[Any] = []
        self._lock = threading.Lock()

    def append(self, event: Any) -> None:
        with self._lock:
            self.events.append(event)


def test_an_engaged_stop_admits_no_writer() -> None:
    ran: list[str] = []
    foundry = WorkshopFoundry(emergency_stop=_Stop(engaged=True), writers_at_once=2)
    outcomes = foundry.run_batch(
        "gagos-t",
        [WriterLeg("w1", ("a.jsx",), lambda: ran.append("w1"))],
    )
    assert ran == []
    assert len(outcomes) == 1 and "emergency stop" in str(outcomes[0])


def test_writers_run_side_by_side_within_the_bound() -> None:
    lock, now, most = threading.Lock(), [0], [0]

    def write() -> None:
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
        time.sleep(0.2)
        with lock:
            now[0] -= 1

    foundry = WorkshopFoundry(emergency_stop=_Stop(), writers_at_once=2)
    outcomes = foundry.run_batch(
        "gagos-t", [WriterLeg(f"w{i}", (f"f{i}.jsx",), write) for i in range(5)]
    )
    assert outcomes == [None] * 5
    assert most[0] == 2, "two at once: side by side, never more than the bound"


def test_each_writer_lifecycle_reaches_the_bus() -> None:
    bus = _Bus()
    foundry = WorkshopFoundry(emergency_stop=_Stop(), bus=bus, writers_at_once=2)
    assert foundry.run_batch(
        "gagos-2026-11-10T05",
        [
            WriterLeg("claude-sonnet-5-5", ("a.jsx",), lambda: None),
            WriterLeg("gpt-6-luna", ("b.py", "c.py"), lambda: None),
        ],
    ) == [None, None]
    by_worker: dict[str, list[str]] = {}
    for event in bus.events:
        by_worker.setdefault(event.worker_id, []).append(event.event_type)
    assert len(by_worker) == 2
    for kinds in by_worker.values():
        assert kinds == [
            CanonicalEventType.WORKER_REQUESTED.value,
            CanonicalEventType.WORKER_ADMITTED.value,
            CanonicalEventType.WORKER_STARTED.value,
            CanonicalEventType.WORKER_COMPLETED.value,
            CanonicalEventType.WORKER_DISSOLVED.value,
        ]
    assert {e.mission_id for e in bus.events} == {"gagos-2026-11-10T05"}
    assert Counter(e.payload["strategy"] for e in bus.events) == {"code": 10}
    assert {tuple(e.payload["scope"]["files"]) for e in bus.events} == {
        ("a.jsx",),
        ("b.py", "c.py"),
    }


def test_one_writers_failure_never_stops_the_others() -> None:
    ran: list[str] = []

    def boom() -> None:
        raise ValueError("the writer broke")

    foundry = WorkshopFoundry(emergency_stop=_Stop(), writers_at_once=1)
    outcomes = foundry.run_batch(
        "gagos-t",
        [
            WriterLeg("w1", ("a.jsx",), boom),
            WriterLeg("w2", ("b.jsx",), lambda: ran.append("w2")),
        ],
    )
    assert isinstance(outcomes[0], ValueError) and outcomes[1] is None
    assert ran == ["w2"]


def test_a_writer_past_its_timeout_fails_and_frees_its_slot() -> None:
    release = threading.Event()
    ran: list[str] = []
    foundry = WorkshopFoundry(emergency_stop=_Stop(), writers_at_once=1)
    try:
        outcomes = foundry.run_batch(
            "gagos-t",
            [
                WriterLeg("slow", ("a.jsx",), lambda: release.wait(3)),
                WriterLeg("next", ("b.jsx",), lambda: ran.append("next")),
            ],
            timeout_seconds=1,
        )
    finally:
        release.set()
    assert isinstance(outcomes[0], WorkshopWriterTimedOut)
    assert outcomes[1] is None and ran == ["next"]
