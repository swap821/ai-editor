"""Live Pheromone Surface — ephemeral coordination signals with TTL."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Any


class SignalType(str, Enum):
    FILE_LOCK = "file-lock"
    WORKER_ACTIVE = "worker-active"
    ATTENTION_NEEDED = "attention-needed"
    PROGRESS_UPDATE = "progress-update"


@dataclass(frozen=True)
class LiveSignal:
    signal_id: int
    stype: SignalType
    resource: str
    worker_id: str
    ttl_seconds: int
    payload: dict[str, Any]
    created_at: float  # time.time() monotonic

    def is_expired(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return (now - self.created_at) > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stype"] = self.stype.value
        return d


_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY,
    stype TEXT,
    resource TEXT,
    worker_id TEXT,
    ttl_seconds INTEGER,
    payload_json TEXT,
    created_at REAL
)
"""


class LiveSurface:
    """In-memory + SQLite-backed ephemeral coordination signals."""

    def __init__(self, db_path: Path | None = None):
        self._lock = threading.Lock()
        self._signals: dict[int, LiveSignal] = {}
        self._next_id = 1
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        if db_path is not None:
            self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
            self._conn.execute(_SCHEMA)
            self._conn.commit()
            self._recover()

    def _recover(self) -> None:
        assert self._conn is not None
        now = time.time()
        cur = self._conn.execute(
            "SELECT id, stype, resource, worker_id, ttl_seconds, payload_json, created_at FROM signals"
        )
        rows = cur.fetchall()
        max_id = 0
        stale_ids: list[int] = []
        for row in rows:
            sig_id, stype, resource, worker_id, ttl_seconds, payload_json, created_at = row
            max_id = max(max_id, sig_id)
            if (now - created_at) > ttl_seconds:
                stale_ids.append(sig_id)
                continue
            signal = LiveSignal(
                signal_id=sig_id,
                stype=SignalType(stype),
                resource=resource,
                worker_id=worker_id,
                ttl_seconds=ttl_seconds,
                payload=json.loads(payload_json) if payload_json else {},
                created_at=created_at,
            )
            self._signals[sig_id] = signal
        if stale_ids:
            self._conn.executemany(
                "DELETE FROM signals WHERE id = ?", [(i,) for i in stale_ids]
            )
            self._conn.commit()
        self._next_id = max_id + 1

    def emit(
        self,
        stype: SignalType,
        resource: str,
        worker_id: str,
        ttl_seconds: int = 30,
        payload: dict[str, Any] | None = None,
    ) -> int:
        payload = payload or {}
        with self._lock:
            signal_id = self._next_id
            self._next_id += 1
            signal = LiveSignal(
                signal_id=signal_id,
                stype=stype,
                resource=resource,
                worker_id=worker_id,
                ttl_seconds=ttl_seconds,
                payload=payload,
                created_at=time.time(),
            )
            self._signals[signal_id] = signal
            if self._conn is not None:
                self._conn.execute(
                    "INSERT INTO signals (id, stype, resource, worker_id, ttl_seconds, payload_json, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        signal_id,
                        stype.value,
                        resource,
                        worker_id,
                        ttl_seconds,
                        json.dumps(payload),
                        signal.created_at,
                    ),
                )
                self._conn.commit()
            return signal_id

    def query_resource(self, resource: str) -> list[LiveSignal]:
        now = time.time()
        with self._lock:
            return [
                s
                for s in self._signals.values()
                if s.resource == resource and not s.is_expired(now)
            ]

    def query_worker(self, worker_id: str) -> list[LiveSignal]:
        now = time.time()
        with self._lock:
            return [
                s
                for s in self._signals.values()
                if s.worker_id == worker_id and not s.is_expired(now)
            ]

    def active_locks(self) -> list[LiveSignal]:
        now = time.time()
        with self._lock:
            return [
                s
                for s in self._signals.values()
                if s.stype == SignalType.FILE_LOCK and not s.is_expired(now)
            ]

    def sweep_expired(self) -> int:
        now = time.time()
        with self._lock:
            expired_ids = [
                sig_id
                for sig_id, s in self._signals.items()
                if s.is_expired(now)
            ]
            for sig_id in expired_ids:
                del self._signals[sig_id]
            if expired_ids and self._conn is not None:
                self._conn.executemany(
                    "DELETE FROM signals WHERE id = ?",
                    [(i,) for i in expired_ids],
                )
                self._conn.commit()
            return len(expired_ids)

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            active = [s for s in self._signals.values() if not s.is_expired(now)]
            by_type: dict[str, int] = {}
            for s in active:
                by_type[s.stype.value] = by_type.get(s.stype.value, 0) + 1
            return {
                "signals": [s.to_dict() for s in active],
                "total": len(active),
                "by_type": by_type,
            }

    def revoke(self, signal_id: int) -> bool:
        with self._lock:
            if signal_id not in self._signals:
                return False
            del self._signals[signal_id]
            if self._conn is not None:
                self._conn.execute("DELETE FROM signals WHERE id = ?", (signal_id,))
                self._conn.commit()
            return True
