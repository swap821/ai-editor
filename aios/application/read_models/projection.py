"""Incremental, durable system read model.

The projection stores only current active entities and counters.  Normal reads
never replay the event history; replay is an explicit recovery operation driven
by the Cortex consumer cursor.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios.domain.read_models import MetricEnvelope, MetricStatus, SystemPortraitSnapshot
from aios.runtime.cortex_bus import BusEvent, CortexBus, ConsumerReplayGap


_SCHEMA = """
CREATE TABLE IF NOT EXISTS system_portrait_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS active_turns (
    entity_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS active_missions (
    entity_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS active_workers (
    entity_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS active_models (
    entity_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projection_applied_events (
    event_id INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


class IncrementalSystemProjection:
    """Apply one observation in O(1) against current active entities."""

    consumer_name = "system-portrait"

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._ensure_state(conn, "last_event_id", "0")
            self._ensure_state(conn, "phase", "idle")
            for key in (
                "active_turns",
                "active_missions",
                "active_workers",
                "active_models",
            ):
                self._ensure_state(conn, key, "0")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def _ensure_state(conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO system_portrait_state(key, value) VALUES (?, ?)",
            (key, value),
        )

    @staticmethod
    def _state(conn: sqlite3.Connection, key: str) -> str:
        row = conn.execute(
            "SELECT value FROM system_portrait_state WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row is not None else "0"

    @staticmethod
    def _set_state(conn: sqlite3.Connection, key: str, value: object) -> None:
        conn.execute(
            "INSERT INTO system_portrait_state(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def apply(self, event: BusEvent) -> bool:
        """Apply one event idempotently; duplicate event IDs are ignored."""
        now = _utc_now()
        with self._lock, self._connect() as conn:
            inserted = conn.execute(
                "INSERT OR IGNORE INTO projection_applied_events(event_id, applied_at) "
                "VALUES (?, ?)",
                (event.id, now),
            ).rowcount
            if inserted == 0:
                return False
            payload = _flatten_payload(event.payload)
            event_type = event.event_type
            if event_type in {"turn.started", "directive.started"}:
                self._activate(
                    conn,
                    "active_turns",
                    _entity_id(payload, "turn_id", event.signature),
                    payload,
                    now,
                )
            elif event_type in {"turn.completed", "turn.failed"}:
                self._deactivate(
                    conn,
                    "active_turns",
                    _entity_id(payload, "turn_id", event.signature),
                )
            elif event_type in {"mission.running", "mission.started"}:
                self._activate(
                    conn,
                    "active_missions",
                    _entity_id(payload, "mission_id", event.signature),
                    payload,
                    now,
                )
            elif event_type in {
                "mission.completed",
                "mission.failed",
                "mission.cancelled",
                "mission.rolled_back",
            }:
                self._deactivate(
                    conn,
                    "active_missions",
                    _entity_id(payload, "mission_id", event.signature),
                )
            elif event_type == "worker.started":
                self._activate(
                    conn,
                    "active_workers",
                    _entity_id(payload, "worker_id", event.signature),
                    payload,
                    now,
                )
            elif event_type in {
                "worker.completed",
                "worker.dissolved",
                "worker.failed",
                "worker.killed",
            }:
                self._deactivate(
                    conn,
                    "active_workers",
                    _entity_id(payload, "worker_id", event.signature),
                )
            elif event_type in {"model.selected", "model.started"}:
                self._activate(
                    conn,
                    "active_models",
                    _model_id(payload, event.signature),
                    payload,
                    now,
                )
            elif event_type in {"model.completed", "model.failed", "model.dissolved"}:
                self._deactivate(
                    conn, "active_models", _model_id(payload, event.signature)
                )

            self._set_state(conn, "last_event_id", event.id)
            counts = {
                "active_turns": self._count(conn, "active_turns"),
                "active_missions": self._count(conn, "active_missions"),
                "active_workers": self._count(conn, "active_workers"),
                "active_models": self._count(conn, "active_models"),
            }
            for key, count in counts.items():
                self._set_state(conn, key, count)
            self._set_state(
                conn,
                "phase",
                "active" if any(counts.values()) else "idle",
            )
        return True

    def _activate(
        self,
        conn: sqlite3.Connection,
        table: str,
        entity_id: str,
        payload: dict[str, Any],
        now: str,
    ) -> None:
        if not entity_id:
            return
        conn.execute(
            f"INSERT INTO {table}(entity_id, payload_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(entity_id) DO UPDATE SET payload_json = excluded.payload_json, "
            "updated_at = excluded.updated_at",
            (entity_id, json.dumps(payload, sort_keys=True), now),
        )

    def _deactivate(self, conn: sqlite3.Connection, table: str, entity_id: str) -> None:
        if entity_id:
            conn.execute(f"DELETE FROM {table} WHERE entity_id = ?", (entity_id,))

    @staticmethod
    def _count(conn: sqlite3.Connection, table: str) -> int:
        return int(
            conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
        )

    def snapshot(self) -> SystemPortraitSnapshot:
        """Read current projections only; event history is never scanned."""
        with self._connect() as conn:
            active = {
                table: tuple(
                    str(row["entity_id"])
                    for row in conn.execute(
                        f"SELECT entity_id FROM {table} ORDER BY entity_id"
                    ).fetchall()
                )
                for table in (
                    "active_turns",
                    "active_missions",
                    "active_workers",
                    "active_models",
                )
            }
            phase = self._state(conn, "phase")
            last_event_id = int(self._state(conn, "last_event_id"))
            counts = {
                "active_turns": int(self._state(conn, "active_turns")),
                "active_missions": int(self._state(conn, "active_missions")),
                "active_workers": int(self._state(conn, "active_workers")),
                "active_models": int(self._state(conn, "active_models")),
            }
        measured_at = _utc_now()
        metrics = {
            key: MetricEnvelope(
                value=value,
                status=MetricStatus.MEASURED,
                measured_at=measured_at,
                source="system_portrait_projection",
                freshness=0,
            )
            for key, value in counts.items()
        }
        return SystemPortraitSnapshot(
            status="online",
            phase=phase,
            active_turns=active["active_turns"],
            active_missions=active["active_missions"],
            active_workers=active["active_workers"],
            active_models=active["active_models"],
            last_event_id=last_event_id,
            metrics=metrics,
        )

    def process_available(self, bus: CortexBus, *, limit: int = 100) -> int:
        """Replay a bounded page and advance only this consumer's cursor."""
        processed = 0
        while True:
            batch = bus.consumer_batch(self.consumer_name, limit=limit)
            if not batch:
                return processed
            for event in batch:
                try:
                    self.apply(event)
                    bus.ack_consumer(self.consumer_name, event.id)
                    processed += 1
                except Exception as exc:  # noqa: BLE001 - cursor records retry state
                    cursor = bus.fail_consumer(self.consumer_name, event.id, str(exc))
                    if cursor.status != "quarantined":
                        return processed
            if len(batch) < max(1, int(limit)):
                return processed


class SystemProjectionConsumer:
    """Bounded dispatcher adapter for the projection's independent cursor."""

    def __init__(self, projection: IncrementalSystemProjection, bus: CortexBus) -> None:
        self.projection = projection
        self.bus = bus

    def __call__(self, event: BusEvent) -> None:
        try:
            self.projection.apply(event)
            self.bus.ack_consumer(self.projection.consumer_name, event.id)
        except Exception as exc:  # noqa: BLE001 - observer failure is quarantined/retried
            cursor = self.bus.fail_consumer(
                self.projection.consumer_name,
                event.id,
                str(exc),
            )
            if cursor.status != "quarantined":
                return


_PROJECTIONS: dict[str, IncrementalSystemProjection] = {}
_PROJECTIONS_LOCK = threading.Lock()


def get_system_projection(db_path: str | Path) -> IncrementalSystemProjection:
    key = str(Path(db_path).resolve())
    with _PROJECTIONS_LOCK:
        projection = _PROJECTIONS.get(key)
        if projection is None:
            projection = IncrementalSystemProjection(
                Path(db_path).with_name("system_portrait.db")
            )
            _PROJECTIONS[key] = projection
        return projection


def _flatten_payload(payload: dict[str, Any]) -> dict[str, Any]:
    flat = dict(payload or {})
    nested = flat.get("payload")
    if isinstance(nested, dict):
        flat = {**flat, **nested}
    return flat


def _entity_id(payload: dict[str, Any], key: str, fallback: str) -> str:
    value = payload.get(key) or payload.get(_camel(key)) or fallback
    return str(value or "")


def _model_id(payload: dict[str, Any], fallback: str) -> str:
    value = (
        payload.get("model")
        or payload.get("model_id")
        or payload.get("modelId")
        or fallback
    )
    return str(value or "")


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "IncrementalSystemProjection",
    "SystemProjectionConsumer",
    "get_system_projection",
]
