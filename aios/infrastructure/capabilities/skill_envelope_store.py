"""SQLite persistence for GAGOS's standing skill envelopes and their activations.

Beside the mission envelopes, in the same capabilities database. An activation
is reserved inside one ``BEGIN IMMEDIATE`` transaction that re-reads the
envelope, so two activations can never take its last place together, and a
revoked or expired envelope gives none. A skill version is activated inside an
envelope at most once.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class SkillEnvelopeStore:
    """Skill envelopes, at most one unrevoked at a time, and their activations."""

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
                CREATE TABLE IF NOT EXISTS gagos_skill_envelopes (
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
                CREATE TABLE IF NOT EXISTS gagos_skill_envelope_activations (
                    envelope_id TEXT NOT NULL,
                    activation INTEGER NOT NULL,
                    skill_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    originator TEXT NOT NULL,
                    activation_digest TEXT NOT NULL,
                    reserved_at REAL NOT NULL,
                    PRIMARY KEY (envelope_id, activation),
                    UNIQUE (envelope_id, skill_id, version)
                )
                """
            )

    def insert(self, row: dict[str, Any], *, now: float) -> None:
        """Record a newly signed skill envelope; any unrevoked one is
        superseded in the same transaction."""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE gagos_skill_envelopes SET revoked_at = ?, revoked_reason = ? "
                    "WHERE revoked_at IS NULL",
                    (now, "superseded by a newer skill envelope"),
                )
                conn.execute(
                    "INSERT INTO gagos_skill_envelopes (envelope_id, operator_id, "
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
        """The most recently signed skill envelope, whatever its state."""
        with closing(self._connect()) as conn:
            return self._envelope(
                conn.execute(
                    "SELECT * FROM gagos_skill_envelopes "
                    "ORDER BY issued_at DESC, rowid DESC LIMIT 1"
                ).fetchone()
            )

    def envelope(self, envelope_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            return self._envelope(
                conn.execute(
                    "SELECT * FROM gagos_skill_envelopes WHERE envelope_id = ?",
                    (envelope_id,),
                ).fetchone()
            )

    def revoke(self, envelope_id: str, *, now: float, reason: str) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE gagos_skill_envelopes SET revoked_at = ?, revoked_reason = ? "
                "WHERE envelope_id = ? AND revoked_at IS NULL",
                (now, reason, envelope_id),
            )
            return cur.rowcount == 1

    def reserve(
        self,
        *,
        envelope_id: str,
        max_activations: int,
        clock: Any,
        skill_id: str,
        version: int,
        originator: str,
        digest_for: Any,
    ) -> int | str:
        """Take the envelope's next activation for *skill_id* at *version*:
        its number, or ``"ended"`` (revoked or expired), ``"full"``, or
        ``"taken"`` (already activated inside it). *digest_for(n)* gives the
        activation's digest. The clock is read only once the writer lock is
        held, as the mission envelope's is."""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                now = float(clock())
                live = conn.execute(
                    "SELECT 1 FROM gagos_skill_envelopes WHERE envelope_id = ? "
                    "AND revoked_at IS NULL AND expires_at > ?",
                    (envelope_id, now),
                ).fetchone()
                if live is None:
                    conn.execute("ROLLBACK")
                    return "ended"
                taken = conn.execute(
                    "SELECT 1 FROM gagos_skill_envelope_activations "
                    "WHERE envelope_id = ? AND skill_id = ? AND version = ?",
                    (envelope_id, skill_id, int(version)),
                ).fetchone()
                if taken is not None:
                    conn.execute("ROLLBACK")
                    return "taken"
                used = conn.execute(
                    "SELECT COUNT(*) FROM gagos_skill_envelope_activations "
                    "WHERE envelope_id = ?",
                    (envelope_id,),
                ).fetchone()[0]
                if used >= max_activations:
                    conn.execute("ROLLBACK")
                    return "full"
                activation = int(used) + 1
                conn.execute(
                    "INSERT INTO gagos_skill_envelope_activations (envelope_id, "
                    "activation, skill_id, version, originator, activation_digest, "
                    "reserved_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        envelope_id,
                        activation,
                        skill_id,
                        int(version),
                        originator,
                        digest_for(activation),
                        now,
                    ),
                )
                conn.execute("COMMIT")
                return activation
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def activation(
        self, envelope_id: str, skill_id: str, version: int
    ) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM gagos_skill_envelope_activations "
                "WHERE envelope_id = ? AND skill_id = ? AND version = ?",
                (envelope_id, skill_id, int(version)),
            ).fetchone()
        return dict(row) if row is not None else None

    def used(self, envelope_id: str) -> int:
        with closing(self._connect()) as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM gagos_skill_envelope_activations "
                    "WHERE envelope_id = ?",
                    (envelope_id,),
                ).fetchone()[0]
            )


__all__ = ["SkillEnvelopeStore"]
