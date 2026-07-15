"""SQLite persistence for the single Human Sovereign operator."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any


def credential_digest(value: str) -> str:
    """Hash bootstrap/recovery material before it reaches durable storage."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class IdentityStore:
    """Small durable store with a database-enforced single-operator record."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sovereign_operator (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    operator_id TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    credential_digest TEXT NOT NULL,
                    recovery_digest TEXT NOT NULL,
                    enrolled_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sovereign_devices (
                    device_id TEXT PRIMARY KEY,
                    operator_id TEXT NOT NULL,
                    enrolled_at REAL NOT NULL,
                    last_authenticated_at REAL,
                    revoked_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS authentication_events (
                    event_id TEXT PRIMARY KEY,
                    operator_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    session_hash TEXT,
                    occurred_at REAL NOT NULL,
                    device_id TEXT NOT NULL DEFAULT 'device:legacy',
                    strength TEXT NOT NULL DEFAULT 'operator',
                    purpose TEXT NOT NULL DEFAULT 'login',
                    created_at REAL NOT NULL DEFAULT 0,
                    expires_at REAL NOT NULL DEFAULT 0,
                    consumed_at REAL
                )
                """
            )
            # Existing pre-R2 databases are upgraded in place.  Every added
            # column has a conservative default so a stale local database
            # cannot make identity resolution fail open.
            existing = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(authentication_events)")
            }
            additions = {
                "device_id": "TEXT NOT NULL DEFAULT 'device:legacy'",
                "strength": "TEXT NOT NULL DEFAULT 'operator'",
                "purpose": "TEXT NOT NULL DEFAULT 'login'",
                "created_at": "REAL NOT NULL DEFAULT 0",
                "expires_at": "REAL NOT NULL DEFAULT 0",
                "consumed_at": "REAL",
            }
            for column, definition in additions.items():
                if column not in existing:
                    conn.execute(
                        f"ALTER TABLE authentication_events ADD COLUMN {column} {definition}"
                    )
            conn.execute(
                "UPDATE authentication_events SET created_at = occurred_at "
                "WHERE created_at = 0"
            )
            conn.execute(
                "UPDATE authentication_events SET expires_at = occurred_at + 3600 "
                "WHERE expires_at = 0"
            )
            conn.commit()

    def operator(self) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT operator_id, display_name, credential_digest, recovery_digest, enrolled_at "
                "FROM sovereign_operator WHERE singleton_id = 1"
            ).fetchone()
        return dict(row) if row is not None else None

    def create_operator(
        self,
        *,
        operator_id: str,
        display_name: str,
        credential_digest_value: str,
        recovery_digest_value: str,
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO sovereign_operator(
                    singleton_id, operator_id, display_name, credential_digest,
                    recovery_digest, enrolled_at
                ) VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    operator_id,
                    display_name,
                    credential_digest_value,
                    recovery_digest_value,
                    time.time(),
                ),
            )
            conn.commit()

    def create_device(self, *, device_id: str, operator_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO sovereign_devices(device_id, operator_id, enrolled_at) VALUES (?, ?, ?)",
                (device_id, operator_id, time.time()),
            )
            conn.commit()

    def device_for_operator(self, operator_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT device_id, operator_id, enrolled_at, last_authenticated_at, revoked_at "
                "FROM sovereign_devices WHERE operator_id = ? AND revoked_at IS NULL "
                "ORDER BY enrolled_at LIMIT 1",
                (operator_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def touch_device(self, device_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE sovereign_devices SET last_authenticated_at = ? WHERE device_id = ?",
                (time.time(), device_id),
            )
            conn.commit()

    def record_authentication_event(
        self,
        *,
        event_id: str,
        operator_id: str,
        event_type: str,
        session_hash: str | None,
        device_id: str = "device:local",
        strength: str = "operator",
        purpose: str | None = None,
        expires_at: float | None = None,
    ) -> None:
        created_at = time.time()
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO authentication_events(" 
                "event_id, operator_id, event_type, session_hash, occurred_at, device_id, "
                "strength, purpose, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    operator_id,
                    event_type,
                    session_hash,
                    created_at,
                    device_id,
                    strength,
                    purpose or event_type,
                    created_at,
                    expires_at if expires_at is not None else created_at + 3600,
                ),
            )
            conn.commit()

    def authentication_event(self, event_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT event_id, operator_id, device_id, strength, purpose, created_at, "
                "expires_at, consumed_at, session_hash FROM authentication_events "
                "WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def authentication_event_count(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) FROM authentication_events").fetchone()
        return int(row[0]) if row else 0
