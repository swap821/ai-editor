"""Phase 3A — durable, replayable Council deliberation state.

Persists every Queen verdict and Council lifecycle event to SQLite so a mission's
deliberation can be replayed and audited, instead of living only in per-mission
JSON artifacts. Schema follows the sovereign roadmap (Phase 3A).

This store is additive: callers treat persistence as best-effort. It never holds
authority and never blocks a mission.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from aios import config
from aios.runtime.contracts import QueenVerdict

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queen_verdicts (
    id INTEGER PRIMARY KEY,
    mission_id TEXT NOT NULL,
    queen_name TEXT NOT NULL,
    verdict TEXT NOT NULL,
    risk TEXT NOT NULL,
    reason TEXT,
    constraints_json TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS council_events (
    id INTEGER PRIMARY KEY,
    mission_id TEXT,
    queen_name TEXT,
    event_type TEXT,
    payload_json TEXT,
    risk TEXT,
    snapshot_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verdicts_mission ON queen_verdicts(mission_id);
CREATE INDEX IF NOT EXISTS idx_events_mission ON council_events(mission_id);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class CouncilState:
    """SQLite-backed log of Queen verdicts and Council events."""

    def __init__(self, db_path: str | Path = config.COUNCIL_STATE_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection scoped to one ``with`` block.

        Mirrors ``sqlite3.Connection``'s own context-manager semantics
        (commit on success, rollback on exception) but ALSO closes the
        connection on exit — plain ``sqlite3.Connection.__exit__`` only
        commits/rolls back the transaction, it never closes the connection,
        which otherwise leaks one open connection/file handle per call.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_verdict(self, mission_id: str, verdict: QueenVerdict) -> int:
        """Persist one Queen verdict; returns its row id."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO queen_verdicts "
                "(mission_id, queen_name, verdict, risk, reason, constraints_json, "
                " confidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    mission_id,
                    verdict.queen,
                    verdict.verdict,
                    verdict.risk,
                    verdict.reason,
                    json.dumps(list(verdict.constraints)),
                    float(verdict.confidence),
                    _utc_now(),
                ),
            )
            return int(cur.lastrowid)

    def record_event(
        self,
        mission_id: str | None,
        *,
        event_type: str,
        queen_name: str | None = None,
        payload: dict[str, Any] | None = None,
        risk: str | None = None,
        snapshot_id: str | None = None,
    ) -> int:
        """Persist one Council lifecycle event; returns its row id."""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO council_events "
                "(mission_id, queen_name, event_type, payload_json, risk, "
                " snapshot_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    mission_id,
                    queen_name,
                    event_type,
                    json.dumps(payload or {}),
                    risk,
                    snapshot_id,
                    _utc_now(),
                ),
            )
            return int(cur.lastrowid)

    def verdicts_for(self, mission_id: str) -> list[dict[str, Any]]:
        """Return every recorded verdict for *mission_id*, oldest first (replay)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM queen_verdicts WHERE mission_id = ? ORDER BY id ASC",
                (mission_id,),
            ).fetchall()
        return [self._verdict_row(row) for row in rows]

    def events_for(self, mission_id: str) -> list[dict[str, Any]]:
        """Return every recorded event for *mission_id*, oldest first (replay)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM council_events WHERE mission_id = ? ORDER BY id ASC",
                (mission_id,),
            ).fetchall()
        return [self._event_row(row) for row in rows]

    @staticmethod
    def _verdict_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "mission_id": row["mission_id"],
            "queen_name": row["queen_name"],
            "verdict": row["verdict"],
            "risk": row["risk"],
            "reason": row["reason"],
            "constraints": json.loads(row["constraints_json"] or "[]"),
            "confidence": row["confidence"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _event_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "mission_id": row["mission_id"],
            "queen_name": row["queen_name"],
            "event_type": row["event_type"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "risk": row["risk"],
            "snapshot_id": row["snapshot_id"],
            "created_at": row["created_at"],
        }


__all__ = ["CouncilState"]
