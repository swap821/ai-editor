from __future__ import annotations

import sqlite3


class MissionTransitionJournalMigration:
    """Slice 35 — durable, idempotent mission execution transition journal."""

    version = 6
    name = "mission_transition_journal_v1"
    scope = "missions"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mission_execution_transitions (
                mission_id TEXT NOT NULL,
                transition TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (mission_id, transition)
            );
            CREATE INDEX IF NOT EXISTS idx_mission_execution_transitions_mission
                ON mission_execution_transitions(mission_id, sequence);
            """
        )
