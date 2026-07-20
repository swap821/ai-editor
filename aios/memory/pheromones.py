"""Structured pheromone store — typed signals with time-decay."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class PheromoneType(str, Enum):
    FILE_LOCK = "file-lock"
    SUCCESS_TRAIL = "success-trail"
    FAILURE_WARNING = "failure-warning"
    ATTENTION_SIGNAL = "attention-signal"


@dataclass(frozen=True)
class Pheromone:
    pheromone_id: int
    ptype: PheromoneType
    resource: str
    depositor: str
    strength: float
    payload: dict[str, Any]
    created_at: str
    updated_at: str


def _utcnow() -> str:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat()


def _parse_time(value: str) -> float:
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


class PheromoneStore:
    """SQLite-backed pheromone CRUD with computed-at-read-time decay."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS pheromones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ptype TEXT NOT NULL,
        resource TEXT NOT NULL,
        depositor TEXT NOT NULL,
        raw_strength REAL NOT NULL DEFAULT 1.0,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_pheromones_resource ON pheromones(resource);
    CREATE INDEX IF NOT EXISTS idx_pheromones_ptype ON pheromones(ptype);
    """

    def __init__(
        self,
        db_path: Path | None = None,
        lambda_decay: float = 0.02,
        floor: float = 0.01,
    ) -> None:
        self._db_path = db_path or Path(":memory:")
        self._lambda = lambda_decay
        self._floor = floor
        self._shared_conn: sqlite3.Connection | None = None
        if str(self._db_path) == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:")
            self._shared_conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(self._SCHEMA)
            conn.commit()
        finally:
            if conn is not self._shared_conn:
                conn.close()

    def _conn(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _close(self, conn: sqlite3.Connection) -> None:
        if conn is not self._shared_conn:
            conn.close()

    def _compute_strength(self, raw_strength: float, updated_at: str) -> float:
        hours_since_update = max((time.time() - _parse_time(updated_at)) / 3600.0, 0.0)
        return raw_strength * math.exp(-self._lambda * hours_since_update)

    def deposit(
        self,
        ptype: PheromoneType,
        resource: str,
        depositor: str,
        strength: float = 1.0,
        payload: dict[str, Any] | None = None,
    ) -> int:
        now = _utcnow()
        conn = self._conn()
        try:
            cur = conn.execute(
                "INSERT INTO pheromones "
                "(ptype, resource, depositor, raw_strength, payload_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    PheromoneType(ptype).value,
                    resource,
                    depositor,
                    float(strength),
                    json.dumps(payload or {}),
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            self._close(conn)

    def reinforce(self, pheromone_id: int, boost: float = 0.2) -> None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT raw_strength FROM pheromones WHERE id = ?", (pheromone_id,)
            ).fetchone()
            if row is None:
                return
            new_strength = min(1.0, float(row["raw_strength"]) + boost)
            conn.execute(
                "UPDATE pheromones SET raw_strength = ?, updated_at = ? WHERE id = ?",
                (new_strength, _utcnow(), pheromone_id),
            )
            conn.commit()
        finally:
            self._close(conn)

    def _row_to_pheromone(self, row: sqlite3.Row) -> Pheromone:
        return Pheromone(
            pheromone_id=int(row["id"]),
            ptype=PheromoneType(row["ptype"]),
            resource=str(row["resource"]),
            depositor=str(row["depositor"]),
            strength=self._compute_strength(
                float(row["raw_strength"]), str(row["updated_at"])
            ),
            payload=json.loads(str(row["payload_json"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def query(
        self,
        resource: str | None = None,
        ptype: PheromoneType | None = None,
        min_strength: float = 0.1,
        limit: int = 50,
    ) -> list[Pheromone]:
        sql = "SELECT * FROM pheromones WHERE 1=1"
        params: list[object] = []
        if resource is not None:
            sql += " AND resource = ?"
            params.append(resource)
        if ptype is not None:
            sql += " AND ptype = ?"
            params.append(PheromoneType(ptype).value)
        conn = self._conn()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            self._close(conn)
        pheromones = [self._row_to_pheromone(row) for row in rows]
        pheromones = [p for p in pheromones if p.strength >= min_strength]
        pheromones.sort(key=lambda p: p.strength, reverse=True)
        return pheromones[:limit]

    def decay_all(self) -> int:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, raw_strength, updated_at FROM pheromones"
            ).fetchall()
            expired_ids = [
                int(row["id"])
                for row in rows
                if self._compute_strength(
                    float(row["raw_strength"]), str(row["updated_at"])
                )
                < self._floor
            ]
            if expired_ids:
                placeholders = ",".join("?" for _ in expired_ids)
                conn.execute(
                    f"DELETE FROM pheromones WHERE id IN ({placeholders})",  # noqa: S608
                    expired_ids,
                )
                conn.commit()
            return len(expired_ids)
        finally:
            self._close(conn)

    def for_contract(self, allowed_files: list[str]) -> list[str]:
        if not allowed_files:
            return []
        contexts: list[str] = []
        for resource in allowed_files:
            for pheromone in self.query(resource=resource):
                summary = (
                    pheromone.payload.get("summary") if pheromone.payload else None
                )
                if not summary:
                    count = (
                        pheromone.payload.get("count") if pheromone.payload else None
                    )
                    outcome = (
                        pheromone.payload.get("outcome") if pheromone.payload else None
                    )
                    if outcome is not None and count is not None:
                        summary = f"{outcome} {count} times"
                    elif count is not None:
                        summary = f"seen {count} times"
                    else:
                        summary = pheromone.depositor
                contexts.append(
                    f"[{pheromone.ptype.value}] {pheromone.resource} "
                    f"(strength={pheromone.strength:.2f}): {summary}"
                )
        return contexts
