"""SQLite persistence for GAGOS's daily envelopes and their slots.

Beside the exact capabilities, in the same database. A slot is reserved inside
one ``BEGIN IMMEDIATE`` transaction that re-reads the envelope, so two missions
can never take its last slot together, and a revoked or expired envelope gives
none.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class EnvelopeStore:
    """Envelopes, at most one unrevoked at a time, and their consumed slots."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gagos_envelopes (
                    envelope_id TEXT PRIMARY KEY,
                    operator_id TEXT NOT NULL,
                    authentication_event_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    terms_json TEXT NOT NULL,
                    terms_digest TEXT NOT NULL,
                    stop_generation INTEGER NOT NULL,
                    issued_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked_at REAL,
                    revoked_reason TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gagos_envelope_slots (
                    envelope_id TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    mission_id TEXT NOT NULL UNIQUE,
                    originator TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    files_json TEXT NOT NULL,
                    slot_digest TEXT NOT NULL,
                    reserved_at REAL NOT NULL,
                    PRIMARY KEY (envelope_id, slot)
                )
                """
            )

    def insert(self, row: dict[str, Any], *, now: float) -> None:
        """Record a newly signed envelope; any unrevoked one is superseded in
        the same transaction."""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE gagos_envelopes SET revoked_at = ?, revoked_reason = ? "
                    "WHERE revoked_at IS NULL",
                    (now, "superseded by a newer envelope"),
                )
                conn.execute(
                    "INSERT INTO gagos_envelopes (envelope_id, operator_id, "
                    "authentication_event_id, session_id, terms_json, terms_digest, "
                    "stop_generation, issued_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row["envelope_id"],
                        row["operator_id"],
                        row["authentication_event_id"],
                        row["session_id"],
                        json.dumps(row["terms"], sort_keys=True),
                        row["terms_digest"],
                        int(row["stop_generation"]),
                        float(row["issued_at"]),
                        float(row["expires_at"]),
                    ),
                )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    @staticmethod
    def _envelope(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        out = dict(row)
        out["terms"] = json.loads(out.pop("terms_json"))
        return out

    def latest(self) -> dict[str, Any] | None:
        """The most recently signed envelope, whatever its state."""
        with closing(self._connect()) as conn:
            return self._envelope(
                conn.execute(
                    "SELECT * FROM gagos_envelopes ORDER BY issued_at DESC, rowid DESC LIMIT 1"
                ).fetchone()
            )

    def envelope(self, envelope_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            return self._envelope(
                conn.execute(
                    "SELECT * FROM gagos_envelopes WHERE envelope_id = ?",
                    (envelope_id,),
                ).fetchone()
            )

    def revoke(self, envelope_id: str, *, now: float, reason: str) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE gagos_envelopes SET revoked_at = ?, revoked_reason = ? "
                "WHERE envelope_id = ? AND revoked_at IS NULL",
                (now, reason, envelope_id),
            )
            return cur.rowcount == 1

    def reserve(
        self,
        *,
        envelope_id: str,
        max_slots: int,
        clock: Any,
        mission_id: str,
        originator: str,
        kind: str,
        files: list[str],
        digest_for: Any,
    ) -> int | str:
        """Take the envelope's next slot for *mission_id*: its number, or
        ``"ended"`` (revoked or expired) or ``"full"``. *digest_for(slot)*
        gives the slot's digest. The clock is read only once the writer lock
        is held (Codex's review: read before, a wait for the lock admitted
        an envelope that expired meanwhile)."""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                now = float(clock())
                live = conn.execute(
                    "SELECT 1 FROM gagos_envelopes WHERE envelope_id = ? "
                    "AND revoked_at IS NULL AND expires_at > ?",
                    (envelope_id, now),
                ).fetchone()
                used = conn.execute(
                    "SELECT COUNT(*) FROM gagos_envelope_slots WHERE envelope_id = ?",
                    (envelope_id,),
                ).fetchone()[0]
                if live is None or used >= max_slots:
                    conn.execute("ROLLBACK")
                    return "ended" if live is None else "full"
                slot = int(used) + 1
                conn.execute(
                    "INSERT INTO gagos_envelope_slots (envelope_id, slot, mission_id, "
                    "originator, kind, files_json, slot_digest, reserved_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        envelope_id,
                        slot,
                        mission_id,
                        originator,
                        kind,
                        json.dumps(sorted(files)),
                        digest_for(slot),
                        now,
                    ),
                )
                conn.execute("COMMIT")
                return slot
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def slot(self, mission_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM gagos_envelope_slots WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["files"] = json.loads(out.pop("files_json"))
        return out

    def used(self, envelope_id: str) -> int:
        with closing(self._connect()) as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM gagos_envelope_slots WHERE envelope_id = ?",
                    (envelope_id,),
                ).fetchone()[0]
            )


__all__ = ["EnvelopeStore"]
