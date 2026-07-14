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
            """
        )
