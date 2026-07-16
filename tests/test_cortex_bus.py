"""Cortex bus W1 (substrate) — durable, per-entity-ordered, fail-soft outbox.

Carries cold-path OBSERVATIONS off the hot path; never authority (that stays
synchronous on the verifier's return value — guarded in W3). W1 wires no
producers or consumers; these tests exercise the substrate directly.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios import config
from aios.core.events import CanonicalEvent, EventPhase, TrustLevel
from aios.runtime.cortex_bus import BusEvent, CortexBus


def _bus(tmp_path: Path) -> CortexBus:
    return CortexBus(db_path=tmp_path / "bus.db")


def _event(event_type: str, signature: str, payload: dict) -> CanonicalEvent:
    return CanonicalEvent(
        event_type=event_type,
        phase=EventPhase.NARRATIVE.value,
        status="observed",
        trust=TrustLevel.ADVISORY.value,
        source="tests.test_cortex_bus",
        session_id=signature,
        payload=payload,
    )


def _append(
    bus: CortexBus, event_type: str, signature: str, payload: dict
) -> int:
    return bus.append(_event(event_type, signature, payload))


def test_connect_closes_the_underlying_connection_after_the_with_block(
    tmp_path: Path,
) -> None:
    # Regression: ``with self._connect() as conn:`` only commits-or-rolls-back
    # -- it never closes the connection, leaking one open sqlite3 connection
    # per call. After the fix, the connection must be closed by the time the
    # ``with`` block exits.
    bus = _bus(tmp_path)
    with bus._connect() as conn:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


# --- Task 1: config -----------------------------------------------------------

def test_cortex_bus_defaults_are_on_and_bounded() -> None:
    # Wonder phase: the bus is on by default (W2 cold-path dispatcher active).
    assert config.CORTEX_BUS is True
    assert str(config.CORTEX_BUS_DB).endswith("cortex_bus.db")
    assert config.CORTEX_BUS_RETENTION_MAX > 0
    assert config.CORTEX_BUS_RETENTION_DAYS > 0


# --- Task 2: durable append ---------------------------------------------------

def test_append_is_durable_and_returns_monotonic_ids(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    first = _append(bus, "turn.completed", "session-1", {"n": 1})
    second = _append(bus, "fact.proposed", "operator", {"n": 2})
    assert second > first
    assert bus.pending_count() == 2

    # Durability: a fresh instance on the same file still sees the pending rows.
    reopened = CortexBus(db_path=tmp_path / "bus.db")
    assert reopened.pending_count() == 2


def test_append_requires_the_canonical_event_schema(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    canonical = CanonicalEvent(
        event_type="turn.completed",
        phase=EventPhase.NARRATIVE.value,
        status="completed",
        trust=TrustLevel.VERIFIED.value,
        source="test.cortex_bus",
        session_id="session-1",
        payload={"n": 1},
    )

    event_id = bus.append(canonical)

    assert event_id > 0
    assert bus.peek_pending()[0].payload["eventType"] == "turn.completed"
    with pytest.raises(TypeError):
        bus.append("turn.completed", "session-1", {"n": 2})


def test_append_round_trips_the_event_payload(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    eid = _append(
        bus, "turn.completed", "session-1", {"latency_ms": 12.5, "ok": True}
    )
    pending = bus.peek_pending()
    assert len(pending) == 1
    event = pending[0]
    assert isinstance(event, BusEvent)
    assert event.id == eid
    assert event.event_type == "turn.completed"
    assert event.signature == "session-1"
    assert event.payload["payload"] == {"latency_ms": 12.5, "ok": True}


def test_empty_or_bad_append_is_rejected(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    with pytest.raises(ValueError):
        _append(bus, "", "session-1", {})
    with pytest.raises(ValueError):
        _append(bus, "turn.completed", "", {})
    assert bus.pending_count() == 0


# --- Task 3: dispatch, ordering, replay --------------------------------------

def test_dispatch_delivers_pending_and_marks_them(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    seen: list[BusEvent] = []
    bus.subscribe(seen.append)

    _append(bus, "turn.completed", "session-1", {"n": 1})
    _append(bus, "turn.completed", "session-1", {"n": 2})
    dispatched = bus.dispatch_pending()

    assert dispatched == 2
    assert [e.payload["payload"]["n"] for e in seen] == [1, 2]
    assert bus.pending_count() == 0
    # A second drain delivers nothing (already dispatched).
    assert bus.dispatch_pending() == 0


def test_per_entity_ordering_is_preserved(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    order: list[tuple[str, int]] = []
    bus.subscribe(lambda e: order.append((e.signature, e.payload["payload"]["n"])))

    # Interleaved appends across two signatures.
    _append(bus, "turn.completed", "A", {"n": 1})
    _append(bus, "fact.proposed", "B", {"n": 1})
    _append(bus, "turn.completed", "A", {"n": 2})
    _append(bus, "fact.proposed", "B", {"n": 2})
    bus.dispatch_pending()

    a_events = [n for sig, n in order if sig == "A"]
    b_events = [n for sig, n in order if sig == "B"]
    assert a_events == [1, 2]  # within a signature: append order
    assert b_events == [1, 2]


def test_a_failing_handler_leaves_its_event_pending_for_replay(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    calls: list[int] = []

    def flaky(event: BusEvent) -> None:
        calls.append(event.id)
        if len(calls) == 1:
            raise RuntimeError("transient")

    bus.subscribe(flaky)
    _append(bus, "turn.completed", "session-1", {"n": 1})

    # First drain: handler throws → event stays pending (not marked dispatched).
    bus.dispatch_pending()
    assert bus.pending_count() == 1
    # Second drain: replays the same event (at-least-once), now succeeds.
    bus.dispatch_pending()
    assert bus.pending_count() == 0
    assert len(calls) == 2  # delivered twice — handlers must be idempotent


# --- Task 4: durability across a simulated crash -----------------------------

def test_crash_between_append_and_dispatch_replays_on_restart(tmp_path: Path) -> None:
    db = tmp_path / "bus.db"
    # Process 1 appends, then "crashes" before any dispatch.
    producer = CortexBus(db_path=db)
    _append(producer, "turn.completed", "session-1", {"n": 1})
    del producer

    # Process 2 starts fresh, subscribes, and drains — the observation survived.
    consumer = CortexBus(db_path=db)
    seen: list[BusEvent] = []
    consumer.subscribe(seen.append)
    assert consumer.dispatch_pending() == 1
    assert seen[0].payload["payload"]["n"] == 1


# --- Task 5: retention sweep + fail-soft --------------------------------------

def test_sweep_ages_out_old_dispatched_but_keeps_pending(tmp_path: Path) -> None:
    # append's fail-soft cap already bounds COUNT, so sweep's real job is the
    # TIME window: age out dispatched rows older than retention_days, never
    # touching a pending one.
    import sqlite3

    bus = CortexBus(db_path=tmp_path / "bus.db", retention_days=7)
    bus.subscribe(lambda e: None)
    old_id = _append(bus, "turn.completed", "s", {"n": 1})
    bus.dispatch_pending()  # dispatched (fresh timestamp)
    _append(bus, "turn.completed", "s", {"n": 99})  # stays pending

    # Backdate the dispatched row well past the window.
    with sqlite3.connect(bus.db_path) as conn:
        conn.execute(
            "UPDATE cortex_events SET dispatched_at = datetime('now', '-30 days') "
            "WHERE id = ?",
            (old_id,),
        )
        conn.commit()

    removed = bus.sweep()
    assert removed == 1  # the aged dispatched row is gone
    # The still-pending event is never swept, regardless of age.
    assert bus.pending_count() == 1
    assert bus.peek_pending()[0].payload["payload"]["n"] == 99


def test_sweep_reclaims_when_retention_max_is_lowered(tmp_path: Path) -> None:
    # The count-branch's real use: a bus whose retention_max was lowered (config
    # change) has more dispatched rows than the new cap — sweep reclaims them.
    bus = CortexBus(db_path=tmp_path / "bus.db", retention_max=100)
    bus.subscribe(lambda e: None)
    for i in range(5):
        _append(bus, "turn.completed", "s", {"n": i})
    bus.dispatch_pending()  # 5 dispatched, under the cap of 100

    bus.retention_max = 2  # operator lowered the cap
    removed = bus.sweep()
    assert removed == 3  # keep the newest 2 dispatched, drop the older 3


def test_full_bus_of_pending_fails_soft_dropping_oldest(tmp_path: Path) -> None:
    bus = CortexBus(db_path=tmp_path / "bus.db", retention_max=2)
    # Never dispatched, so nothing is eligible for normal retention — the cap
    # must still hold by dropping the OLDEST pending, never raising.
    first = _append(bus, "turn.completed", "s", {"n": 1})
    _append(bus, "turn.completed", "s", {"n": 2})
    _append(bus, "turn.completed", "s", {"n": 3})  # exceeds cap of 2

    ids = [e.id for e in bus.peek_pending()]
    assert first not in ids  # oldest dropped
    assert bus.pending_count() == 2  # cap held, no exception raised


# --- Task 6: wake-hint + poll_once -------------------------------------------

def test_hint_is_raised_on_append_and_cleared_on_poll(tmp_path: Path) -> None:
    bus = CortexBus(db_path=tmp_path / "bus.db")
    seen: list[BusEvent] = []
    bus.subscribe(seen.append)

    assert bus.hint_pending() is False
    _append(bus, "turn.completed", "s", {"n": 1})
    assert bus.hint_pending() is True  # producer raised the wake-hint

    drained = bus.poll_once()
    assert drained == 1
    assert bus.hint_pending() is False  # poll consumed the hint
    assert seen[0].payload["payload"]["n"] == 1


def test_authority_event_types_are_refused_at_append(tmp_path: Path) -> None:
    """THE LAW, structural: no authority family may ride the bus — enforced at
    the substrate boundary so a future producer cannot quietly route a decision
    through the observation tier (the adversarial W2 review's blocking ask)."""
    bus = _bus(tmp_path)
    for forbidden in (
        "skill.promoted",
        "autonomy.credited",
        "approval.decided",
        "verdict.recorded",
        "zone.classified",
        "grant.issued",
    ):
        with pytest.raises(ValueError):
            _append(bus, forbidden, "session-1", {})
    assert bus.pending_count() == 0  # nothing slipped through
    # Observations still flow.
    assert _append(bus, "turn.completed", "session-1", {}) > 0


def test_poll_once_drains_even_without_a_hint(tmp_path: Path) -> None:
    # The hint is an optimization; a poll with no hint still drains (safety net).
    db = tmp_path / "bus.db"
    producer = CortexBus(db_path=db)
    _append(producer, "turn.completed", "s", {"n": 1})
    producer.hint_path.unlink(missing_ok=True)  # simulate a lost hint

    consumer = CortexBus(db_path=db)
    consumer.subscribe(lambda e: None)
    assert consumer.hint_pending() is False
    assert consumer.poll_once() == 1  # drained anyway
