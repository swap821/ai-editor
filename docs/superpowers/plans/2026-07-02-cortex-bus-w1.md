# Cortex Bus W1 (Substrate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the durable, cross-process, per-entity-ordered cortex-bus substrate — pure infrastructure with zero producers or consumers wired, default-off.

**Architecture:** A SQLite-backed outbox. `append()` durably writes an observation (commit) then touches a wake-hint file; `dispatch_pending()` drains undispatched rows in append (id) order — which preserves per-entity ordering — invoking in-process handlers idempotently and marking each dispatched only after its handlers succeed (at-least-once; replay-safe). A retention sweep bounds the table; a full table fails soft (drop-oldest, never block). Nothing appends or subscribes in W1 — this is the floor future observers stand on.

**Tech Stack:** Python 3.14, stdlib `sqlite3`, existing `aios.config` conventions, pytest.

**Ratified design:** `docs/superpowers/specs/2026-07-02-wonder-epoch-cortex-bus-design.md` §3–§4.

**Invariants (do not break):**
- The bus carries observations, never authority. No skill-promotion / autonomy / approval decision may flow through it (guarded in W3, not here).
- `test_aliveness_defaults.py` stays green: no wonder organ is enabled by W1.
- Frozen security spine untouched.
- Default off (`AIOS_CORTEX_BUS`): W1 changes no runtime behavior.

---

## File Structure

- **Create `aios/runtime/cortex_bus.py`** — the entire substrate: `BusEvent` dataclass, `CortexBus` class (append / subscribe / dispatch_pending / sweep / pending_count), self-contained SQLite schema + init. One responsibility: durable ordered observation delivery. No imports from `aios.memory` or the security spine.
- **Modify `aios/config.py`** — add `CORTEX_BUS` (bool, default False), `CORTEX_BUS_DB` (Path under `DATA_DIR`), `CORTEX_BUS_RETENTION_MAX` (int), `CORTEX_BUS_RETENTION_DAYS` (int), plus their `__all__` entries.
- **Create `tests/test_cortex_bus.py`** — the full behavioral suite.

Follow the existing `aios/council/council_state.py` pattern: a runtime SQLite store with its own `_init` creating its table, `config`-driven path, `get_connection`-style access via stdlib `sqlite3` with `row_factory`.

---

## Task 1: Config flags (default-off, no behavior change)

**Files:**
- Modify: `aios/config.py` (near the other runtime paths + the `__all__` list)
- Test: `tests/test_cortex_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cortex_bus.py
from aios import config


def test_cortex_bus_defaults_are_off_and_bounded() -> None:
    # W1 must change no behavior: the bus is opt-in.
    assert config.CORTEX_BUS is False
    assert str(config.CORTEX_BUS_DB).endswith("cortex_bus.db")
    assert config.CORTEX_BUS_RETENTION_MAX > 0
    assert config.CORTEX_BUS_RETENTION_DAYS > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py::test_cortex_bus_defaults_are_off_and_bounded -v --no-cov`
Expected: FAIL with `AttributeError: module 'aios.config' has no attribute 'CORTEX_BUS'`

- [ ] **Step 3: Add the config flags**

In `aios/config.py`, after the CRAG / curriculum / facts block (near the other `DATA_DIR`-derived paths), add:

```python
# ── Cortex bus (durable cold-path observation tier) ─────────────────────────
# The event tier for cold, re-derivable observers (self-model rebuild, future
# council triggers). Carries OBSERVATIONS, never authority (a decision stays
# synchronous on the verifier's return value). Default off — W1 is pure infra
# with no producers/consumers. See
# docs/superpowers/specs/2026-07-02-wonder-epoch-cortex-bus-design.md.
CORTEX_BUS: Final[bool] = _env_bool("AIOS_CORTEX_BUS", False)
CORTEX_BUS_DB: Final[Path] = DATA_DIR / "cortex_bus.db"
CORTEX_BUS_RETENTION_MAX: Final[int] = max(
    100, _env_int("AIOS_CORTEX_BUS_RETENTION", 10_000)
)
CORTEX_BUS_RETENTION_DAYS: Final[int] = max(
    1, _env_int("AIOS_CORTEX_BUS_RETENTION_DAYS", 7)
)
```

Add to the `__all__` list (alongside the other config names):

```python
    "CORTEX_BUS", "CORTEX_BUS_DB", "CORTEX_BUS_RETENTION_MAX",
    "CORTEX_BUS_RETENTION_DAYS",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py::test_cortex_bus_defaults_are_off_and_bounded -v --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aios/config.py tests/test_cortex_bus.py
git commit -m "feat(bus): cortex-bus config flags (default off)"
```

---

## Task 2: Durable append + BusEvent + pending_count

**Files:**
- Create: `aios/runtime/cortex_bus.py`
- Test: `tests/test_cortex_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cortex_bus.py
from pathlib import Path

import pytest

from aios.runtime.cortex_bus import BusEvent, CortexBus


def _bus(tmp_path: Path) -> CortexBus:
    return CortexBus(db_path=tmp_path / "bus.db")


def test_append_is_durable_and_returns_monotonic_ids(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    first = bus.append("turn.completed", "session-1", {"n": 1})
    second = bus.append("fact.proposed", "operator", {"n": 2})
    assert second > first
    assert bus.pending_count() == 2

    # Durability: a fresh instance on the same file still sees the pending rows.
    reopened = CortexBus(db_path=tmp_path / "bus.db")
    assert reopened.pending_count() == 2


def test_append_round_trips_the_event_payload(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    eid = bus.append("turn.completed", "session-1", {"latency_ms": 12.5, "ok": True})
    pending = bus.peek_pending()
    assert len(pending) == 1
    event = pending[0]
    assert isinstance(event, BusEvent)
    assert event.id == eid
    assert event.event_type == "turn.completed"
    assert event.signature == "session-1"
    assert event.payload == {"latency_ms": 12.5, "ok": True}


def test_empty_or_bad_append_is_rejected(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    with pytest.raises(ValueError):
        bus.append("", "session-1", {})
    with pytest.raises(ValueError):
        bus.append("turn.completed", "", {})
    assert bus.pending_count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py -k "append or round_trips" -v --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'aios.runtime.cortex_bus'`

- [ ] **Step 3: Write the minimal module**

```python
# aios/runtime/cortex_bus.py
"""Durable, cross-process, per-entity-ordered cortex bus (W1 substrate).

An outbox for COLD-PATH OBSERVATIONS — signals a re-derivable observer acts on
off the hot path (self-model rebuild, future council triggers). It carries what
HAPPENED, never what is PERMITTED: no authority-bearing decision (skill
promotion, autonomy, approval) may flow through it. Append is durable
(commit-then-notify); dispatch drains undispatched rows in append order,
preserving per-entity ordering, and marks each dispatched only after its
handlers succeed (at-least-once — handlers must be idempotent). W1 wires no
producers or consumers; it is the floor future observers stand on.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from aios import config


@dataclass(frozen=True)
class BusEvent:
    """One observation on the bus."""

    id: int
    event_type: str
    signature: str
    payload: dict[str, Any] = field(default_factory=dict)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS cortex_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type    TEXT NOT NULL,
    signature     TEXT NOT NULL,
    payload       TEXT NOT NULL,
    dispatched_at DATETIME
);
CREATE INDEX IF NOT EXISTS idx_cortex_pending
    ON cortex_events(dispatched_at, id);
"""


class CortexBus:
    """A durable SQLite outbox with idempotent, per-entity-ordered dispatch."""

    def __init__(
        self,
        db_path: Path = config.CORTEX_BUS_DB,
        *,
        retention_max: int = config.CORTEX_BUS_RETENTION_MAX,
        retention_days: int = config.CORTEX_BUS_RETENTION_DAYS,
        hint_path: Optional[Path] = None,
    ) -> None:
        self.db_path = db_path
        self.retention_max = max(1, int(retention_max))
        self.retention_days = max(1, int(retention_days))
        self.hint_path = hint_path or db_path.with_suffix(".hint")
        self._handlers: list[Callable[[BusEvent], None]] = []
        self._init()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def append(self, event_type: str, signature: str, payload: dict[str, Any]) -> int:
        """Durably append one observation; returns its id. Touches the hint file."""
        event_type = (event_type or "").strip()
        signature = (signature or "").strip()
        if not event_type or not signature:
            raise ValueError("cortex event requires a non-empty event_type and signature")
        body = json.dumps(dict(payload or {}), ensure_ascii=False)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO cortex_events (event_type, signature, payload) "
                "VALUES (?, ?, ?)",
                (event_type, signature, body),
            )
            conn.commit()
            event_id = int(cur.lastrowid)
        self._touch_hint()
        return event_id

    def _touch_hint(self) -> None:
        try:
            self.hint_path.parent.mkdir(parents=True, exist_ok=True)
            self.hint_path.write_text("1", encoding="utf-8")
        except OSError:
            pass  # the hint is an optimization; polling still drains the outbox

    def peek_pending(self, limit: int = 1000) -> list[BusEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, event_type, signature, payload FROM cortex_events "
                "WHERE dispatched_at IS NULL ORDER BY id ASC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def pending_count(self) -> int:
        with self._connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM cortex_events WHERE dispatched_at IS NULL"
                ).fetchone()["n"]
            )


def _row_to_event(row: sqlite3.Row) -> BusEvent:
    return BusEvent(
        id=int(row["id"]),
        event_type=str(row["event_type"]),
        signature=str(row["signature"]),
        payload=json.loads(row["payload"]),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py -k "append or round_trips" -v --no-cov`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add aios/runtime/cortex_bus.py tests/test_cortex_bus.py
git commit -m "feat(bus): durable append + BusEvent + pending_count"
```

---

## Task 3: subscribe + dispatch_pending (per-entity order, mark dispatched)

**Files:**
- Modify: `aios/runtime/cortex_bus.py`
- Test: `tests/test_cortex_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cortex_bus.py
def test_dispatch_delivers_pending_and_marks_them(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    seen: list[BusEvent] = []
    bus.subscribe(seen.append)

    bus.append("turn.completed", "session-1", {"n": 1})
    bus.append("turn.completed", "session-1", {"n": 2})
    dispatched = bus.dispatch_pending()

    assert dispatched == 2
    assert [e.payload["n"] for e in seen] == [1, 2]
    assert bus.pending_count() == 0
    # A second drain delivers nothing (already dispatched).
    assert bus.dispatch_pending() == 0


def test_per_entity_ordering_is_preserved(tmp_path: Path) -> None:
    bus = _bus(tmp_path)
    order: list[tuple[str, int]] = []
    bus.subscribe(lambda e: order.append((e.signature, e.payload["n"])))

    # Interleaved appends across two signatures.
    bus.append("turn.completed", "A", {"n": 1})
    bus.append("fact.proposed", "B", {"n": 1})
    bus.append("turn.completed", "A", {"n": 2})
    bus.append("fact.proposed", "B", {"n": 2})
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
    bus.append("turn.completed", "session-1", {"n": 1})

    # First drain: handler throws → event stays pending (not marked dispatched).
    bus.dispatch_pending()
    assert bus.pending_count() == 1
    # Second drain: replays the same event (at-least-once), now succeeds.
    bus.dispatch_pending()
    assert bus.pending_count() == 0
    assert len(calls) == 2  # delivered twice — handlers must be idempotent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py -k "dispatch or ordering or replay" -v --no-cov`
Expected: FAIL with `AttributeError: 'CortexBus' object has no attribute 'subscribe'`

- [ ] **Step 3: Add subscribe + dispatch_pending**

In `aios/runtime/cortex_bus.py`, add these methods to `CortexBus` (after `pending_count`):

```python
    def subscribe(self, handler: Callable[[BusEvent], None]) -> None:
        """Register an in-process handler. Handlers MUST be idempotent (an event
        may be delivered more than once on replay) and MUST NOT carry authority."""
        self._handlers.append(handler)

    def dispatch_pending(self, limit: int = 1000) -> int:
        """Drain undispatched events in append (id) order — preserving per-entity
        ordering — calling every handler, then marking each dispatched ONLY if all
        its handlers succeeded. A handler that raises leaves its event pending for
        the next drain (at-least-once). Returns the count marked dispatched.

        NOTE (W1): draining in id order is a global single pass, which trivially
        preserves the per-entity ordering handlers rely on. Concurrent
        per-signature dispatch (so a slow handler on one signature cannot delay
        another) is a future optimization; it is not needed until a real handler
        proves slow, and W1 wires none.
        """
        dispatched = 0
        for event in self.peek_pending(limit=limit):
            try:
                for handler in self._handlers:
                    handler(event)
            except Exception:  # noqa: BLE001 - a bad handler must not sink the bus
                logger.warning(
                    "cortex handler failed for event %s (%s); leaving pending",
                    event.id,
                    event.event_type,
                )
                continue
            with self._connect() as conn:
                conn.execute(
                    "UPDATE cortex_events SET dispatched_at = CURRENT_TIMESTAMP "
                    "WHERE id = ?",
                    (event.id,),
                )
                conn.commit()
            dispatched += 1
        return dispatched
```

Add the logger near the top of the module (after the imports):

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py -k "dispatch or ordering or replay" -v --no-cov`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add aios/runtime/cortex_bus.py tests/test_cortex_bus.py
git commit -m "feat(bus): idempotent per-entity dispatch with replay-on-failure"
```

---

## Task 4: Durability across a simulated crash (append, no dispatch, reopen, drain)

**Files:**
- Test: `tests/test_cortex_bus.py` (no production change — this proves the outbox contract)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cortex_bus.py
def test_crash_between_append_and_dispatch_replays_on_restart(tmp_path: Path) -> None:
    db = tmp_path / "bus.db"
    # Process 1 appends, then "crashes" before any dispatch.
    producer = CortexBus(db_path=db)
    producer.append("turn.completed", "session-1", {"n": 1})
    del producer

    # Process 2 starts fresh, subscribes, and drains — the observation survived.
    consumer = CortexBus(db_path=db)
    seen: list[BusEvent] = []
    consumer.subscribe(seen.append)
    assert consumer.dispatch_pending() == 1
    assert seen[0].payload["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py::test_crash_between_append_and_dispatch_replays_on_restart -v --no-cov`
Expected: PASS immediately (the durable outbox from Tasks 2–3 already satisfies this). If it FAILS, the durability contract is broken — fix `append`/`dispatch_pending` before proceeding. This task is the explicit durability guard; keep it even though it needs no new production code.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cortex_bus.py
git commit -m "test(bus): durability guard — observations replay across restart"
```

---

## Task 5: Retention sweep + fail-soft on a full bus

**Files:**
- Modify: `aios/runtime/cortex_bus.py`
- Test: `tests/test_cortex_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cortex_bus.py
def test_sweep_drops_old_dispatched_but_keeps_pending(tmp_path: Path) -> None:
    bus = CortexBus(db_path=tmp_path / "bus.db", retention_max=3)
    bus.subscribe(lambda e: None)
    for i in range(3):
        bus.append("turn.completed", "s", {"n": i})
    bus.dispatch_pending()  # all 3 dispatched
    bus.append("turn.completed", "s", {"n": 99})  # 1 pending

    removed = bus.sweep()
    assert removed >= 1  # at least the over-cap dispatched rows are gone
    # The still-pending event is never swept.
    assert bus.pending_count() == 1
    assert bus.peek_pending()[0].payload["n"] == 99


def test_full_bus_of_pending_fails_soft_dropping_oldest(tmp_path: Path) -> None:
    bus = CortexBus(db_path=tmp_path / "bus.db", retention_max=2)
    # Never dispatched, so nothing is eligible for normal retention — the cap
    # must still hold by dropping the OLDEST pending, never raising.
    first = bus.append("turn.completed", "s", {"n": 1})
    bus.append("turn.completed", "s", {"n": 2})
    bus.append("turn.completed", "s", {"n": 3})  # exceeds cap of 2

    ids = [e.id for e in bus.peek_pending()]
    assert first not in ids  # oldest dropped
    assert bus.pending_count() == 2  # cap held, no exception raised
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py -k "sweep or fails_soft" -v --no-cov`
Expected: FAIL with `AttributeError: 'CortexBus' object has no attribute 'sweep'`

- [ ] **Step 3: Add sweep + fail-soft enforcement in append**

In `aios/runtime/cortex_bus.py`, add a `sweep` method to `CortexBus`:

```python
    def sweep(self) -> int:
        """Retention: delete DISPATCHED events beyond the count cap or older than
        the day window. Pending events are never swept. Returns rows removed."""
        with self._connect() as conn:
            removed = conn.execute(
                "DELETE FROM cortex_events WHERE dispatched_at IS NOT NULL AND ("
                "  dispatched_at < datetime('now', ?)"
                "  OR id NOT IN ("
                "    SELECT id FROM cortex_events WHERE dispatched_at IS NOT NULL "
                "    ORDER BY id DESC LIMIT ?"
                "  )"
                ")",
                (f"-{self.retention_days} days", self.retention_max),
            ).rowcount
            conn.commit()
        return int(removed)
```

Then enforce the cap fail-soft inside `append`, right after the `INSERT ... conn.commit()` (before `self._touch_hint()`), still inside the `with self._connect() as conn:` block — replace the existing append body's commit section with:

```python
            cur = conn.execute(
                "INSERT INTO cortex_events (event_type, signature, payload) "
                "VALUES (?, ?, ?)",
                (event_type, signature, body),
            )
            event_id = int(cur.lastrowid)
            # Fail-soft cap: never let the outbox grow unbounded. Prefer dropping
            # dispatched rows; if the whole table is pending and still over cap,
            # drop the OLDEST pending (and log) rather than raise or block a turn.
            total = int(conn.execute("SELECT COUNT(*) AS n FROM cortex_events").fetchone()["n"])
            overflow = total - self.retention_max
            if overflow > 0:
                dropped = conn.execute(
                    "DELETE FROM cortex_events WHERE id IN ("
                    "  SELECT id FROM cortex_events "
                    "  ORDER BY (dispatched_at IS NULL), id ASC LIMIT ?"
                    ")",
                    (overflow,),
                ).rowcount
                if dropped:
                    logger.warning(
                        "cortex bus over cap (%d/%d) — dropped %d oldest event(s)",
                        total, self.retention_max, dropped,
                    )
            conn.commit()
```

Note: `ORDER BY (dispatched_at IS NULL), id ASC` drops dispatched rows first (the `IS NULL` boolean sorts `0` before `1`), then the oldest pending only if the table is still over cap — exactly the fail-soft priority.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py -k "sweep or fails_soft" -v --no-cov`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add aios/runtime/cortex_bus.py tests/test_cortex_bus.py
git commit -m "feat(bus): retention sweep + fail-soft drop-oldest on a full bus"
```

---

## Task 6: Wake-hint consume + a thin drain-once loop step

**Files:**
- Modify: `aios/runtime/cortex_bus.py`
- Test: `tests/test_cortex_bus.py`

The 250ms timing loop itself is not unit-tested (timing tests are flaky). Instead we test the MECHANISM the loop uses: a `poll_once()` that consumes the hint and drains, and a `hint_pending()` predicate.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cortex_bus.py
def test_hint_is_raised_on_append_and_cleared_on_poll(tmp_path: Path) -> None:
    bus = CortexBus(db_path=tmp_path / "bus.db")
    seen: list[BusEvent] = []
    bus.subscribe(seen.append)

    assert bus.hint_pending() is False
    bus.append("turn.completed", "s", {"n": 1})
    assert bus.hint_pending() is True  # producer raised the wake-hint

    drained = bus.poll_once()
    assert drained == 1
    assert bus.hint_pending() is False  # poll consumed the hint
    assert seen[0].payload["n"] == 1


def test_poll_once_drains_even_without_a_hint(tmp_path: Path) -> None:
    # The hint is an optimization; a poll with no hint still drains (safety net).
    db = tmp_path / "bus.db"
    producer = CortexBus(db_path=db)
    producer.append("turn.completed", "s", {"n": 1})
    producer.hint_path.unlink(missing_ok=True)  # simulate a lost hint

    consumer = CortexBus(db_path=db)
    consumer.subscribe(lambda e: None)
    assert consumer.hint_pending() is False
    assert consumer.poll_once() == 1  # drained anyway
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py -k "hint or poll_once" -v --no-cov`
Expected: FAIL with `AttributeError: 'CortexBus' object has no attribute 'hint_pending'`

- [ ] **Step 3: Add hint_pending + poll_once**

In `aios/runtime/cortex_bus.py`, add to `CortexBus`:

```python
    def hint_pending(self) -> bool:
        """True if a producer has touched the wake-hint since the last poll."""
        return self.hint_path.exists()

    def poll_once(self) -> int:
        """One dispatcher tick: clear the wake-hint, then drain. Draining always
        runs (even with no hint) so a lost hint never strands an observation —
        the hint only lets the loop wake EARLY, it is never the sole trigger."""
        try:
            self.hint_path.unlink(missing_ok=True)
        except OSError:
            pass
        return self.dispatch_pending()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py -k "hint or poll_once" -v --no-cov`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add aios/runtime/cortex_bus.py tests/test_cortex_bus.py
git commit -m "feat(bus): wake-hint consume + poll_once drain tick"
```

---

## Task 7: Full-gate verification + closeout

**Files:**
- No production change — verification + continuity.

- [ ] **Step 1: Run the whole cortex-bus suite**

Run: `.venv\Scripts\python -m pytest tests/test_cortex_bus.py -v --no-cov --basetemp=C:/Users/kumar/pt`
Expected: PASS (all ~13 tests)

- [ ] **Step 2: Confirm no behavior changed — aliveness posture still caged**

Run: `.venv\Scripts\python -m pytest tests/test_aliveness_defaults.py -v --no-cov --basetemp=C:/Users/kumar/pt`
Expected: PASS (CORTEX_BUS is not asserted there, and no wonder organ flipped)

- [ ] **Step 3: Full backend gate (branch coverage, real exit code)**

Run: `.venv\Scripts\python -m pytest --cov --cov-report=term --cov-fail-under=85 --basetemp=C:/Users/kumar/pt -p no:cacheprovider -q; echo EXIT:$?`
Expected: `EXIT:0`, coverage ≥ 85% (branch), `aios/runtime/cortex_bus.py` ≥ 90%.

- [ ] **Step 4: Update continuity + hand off**

Update `.aios/state/RESUME.md` (W1 landed, W2 next per the spec sequencing), append one `experiences.jsonl` line, `memory_store` a `gagos-cortex-bus-w1` note, and `agent_coord.py handoff` hash-pinned for review. Do NOT commit the handoff docs into a feature commit; keep them separate. Do NOT start W2 — it is a separate review gate.

- [ ] **Step 5: Report to the operator**

State: W1 landed and pushed (or ready to push, per the operator's push preference), the cortex-bus coverage number, that `test_aliveness_defaults` is still green (nothing enabled), and that W2 (self-model observer) awaits a separate go.

---

## Self-Review (run against the spec §3–§4)

- **Spec coverage:** outbox append-then-commit (T2) ✓ · 250ms poll + wake-hint mechanism (T6; the timing loop wrapper is trivial and built at W2 wiring time) ✓ · per-entity ordering (T3) ✓ · at-least-once + idempotent replay (T3, T4) ✓ · bounded + retention sweep (T5) ✓ · fail-soft drop-oldest (T5) ✓ · default-off, zero producers/consumers (T1, whole plan) ✓ · authority-never-on-bus (documented; the enforcing guard is W3, out of this plan's scope by design) ✓.
- **Placeholder scan:** every code step shows complete code; every run step shows the exact command + expected result. No TBDs.
- **Type consistency:** `BusEvent(id, event_type, signature, payload)` used identically in T2/T3/T4/T5/T6; `append`/`dispatch_pending`/`sweep`/`poll_once`/`hint_pending`/`peek_pending`/`pending_count` signatures stable across tasks.
- **Deferred by design (not gaps):** the always-on background dispatcher thread/loop and its wiring to a real producer are W2 concerns (W1 is substrate only); concurrent per-signature dispatch is a documented future optimization, not required until a slow handler exists.
