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
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from aios import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BusEvent:
    """One observation on the bus."""

    id: int
    event_type: str
    signature: str
    payload: dict[str, Any] = field(default_factory=dict)


# THE LAW, enforced structurally (not just documented): the bus carries what
# HAPPENED, never what is PERMITTED. Event types in these authority families
# are refused at append — fail-closed at the substrate boundary, so no future
# producer can quietly route a decision through the observation tier. (The
# adversarial W2 review correctly flagged a test-only guard as tautological;
# this gate is the structural fix.)
_AUTHORITY_EVENT_PREFIXES: tuple[str, ...] = (
    "skill.",
    "autonomy.",
    "approval.",
    "verdict.",
    "zone.",
    "grant.",
)

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


def _row_to_event(row: sqlite3.Row) -> BusEvent:
    return BusEvent(
        id=int(row["id"]),
        event_type=str(row["event_type"]),
        signature=str(row["signature"]),
        payload=json.loads(row["payload"]),
    )


class CortexBus:
    """A durable SQLite outbox with idempotent, per-entity-ordered dispatch."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        *,
        retention_max: Optional[int] = None,
        retention_days: Optional[int] = None,
        hint_path: Optional[Path] = None,
    ) -> None:
        # Resolve config at CALL time, not import time: a def-time default
        # freezes the value before test isolation / env overrides can apply
        # (the repo's known monkeypatch-staleness trap).
        self.db_path = db_path if db_path is not None else config.CORTEX_BUS_DB
        self.retention_max = max(
            1, int(retention_max if retention_max is not None else config.CORTEX_BUS_RETENTION_MAX)
        )
        self.retention_days = max(
            1, int(retention_days if retention_days is not None else config.CORTEX_BUS_RETENTION_DAYS)
        )
        self.hint_path = hint_path or self.db_path.with_suffix(".hint")
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

    # ── Producer side ────────────────────────────────────────────────────────

    def append(self, event_type: str, signature: str, payload: dict[str, Any]) -> int:
        """Durably append one observation; returns its id. Touches the wake-hint.

        Enforces the retention cap fail-soft: never lets the outbox grow
        unbounded, preferring to drop dispatched rows and, only if the whole
        table is still over cap, the OLDEST pending row (logged) — never raises
        and never blocks a turn.
        """
        event_type = (event_type or "").strip()
        signature = (signature or "").strip()
        if not event_type or not signature:
            raise ValueError("cortex event requires a non-empty event_type and signature")
        if event_type.startswith(_AUTHORITY_EVENT_PREFIXES):
            raise ValueError(
                f"authority-bearing event type {event_type!r} may never ride the "
                "cortex bus — decisions stay synchronous on the verifier's return "
                "value (ADR §4.1)"
            )
        body = json.dumps(dict(payload or {}), ensure_ascii=False)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO cortex_events (event_type, signature, payload) "
                "VALUES (?, ?, ?)",
                (event_type, signature, body),
            )
            event_id = int(cur.lastrowid)
            total = int(
                conn.execute("SELECT COUNT(*) AS n FROM cortex_events").fetchone()["n"]
            )
            overflow = total - self.retention_max
            if overflow > 0:
                # dispatched_at IS NULL sorts 0 before 1, so dispatched rows are
                # dropped FIRST; the oldest pending is dropped only if the table
                # is still over cap after that.
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
                        total,
                        self.retention_max,
                        dropped,
                    )
            conn.commit()
        self._touch_hint()
        return event_id

    def _touch_hint(self) -> None:
        try:
            self.hint_path.parent.mkdir(parents=True, exist_ok=True)
            self.hint_path.write_text("1", encoding="utf-8")
        except OSError:
            pass  # the hint is an optimization; polling still drains the outbox

    # ── Consumer side ────────────────────────────────────────────────────────

    def subscribe(self, handler: Callable[[BusEvent], None]) -> None:
        """Register an in-process handler. Handlers MUST be idempotent (an event
        may be delivered more than once on replay) and MUST NOT carry authority."""
        self._handlers.append(handler)

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

    # ── Maintenance ──────────────────────────────────────────────────────────

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
