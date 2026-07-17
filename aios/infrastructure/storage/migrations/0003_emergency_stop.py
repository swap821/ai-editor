from __future__ import annotations

import sqlite3


class EmergencyStopMigration:
    """Slice 24 — durable emergency-stop latch schema."""

    version = 3
    name = "emergency_stop_v1"
    scope = "governance"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS emergency_stop_state (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                engaged INTEGER NOT NULL,
                generation INTEGER NOT NULL,
                operator_id TEXT,
                authentication_event_id TEXT,
                reason TEXT NOT NULL,
                actions_json TEXT NOT NULL,
                failure TEXT,
                engaged_at TEXT,
                cleared_at TEXT
            );
            CREATE TABLE IF NOT EXISTS emergency_clear_capabilities (
                capability_digest TEXT PRIMARY KEY,
                generation INTEGER NOT NULL,
                operator_id TEXT NOT NULL,
                authentication_event_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                issued_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                consumed_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_emergency_clear_generation
                ON emergency_clear_capabilities(generation, consumed_at, expires_at);
            """
        )
