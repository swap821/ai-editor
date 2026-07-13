from __future__ import annotations

import sqlite3


class MissionStateMigration:
    """Slice 7 — authoritative mission state, contract digest, and transition audit."""

    version = 1
    name = "mission_state_v1"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS missions (
                mission_id TEXT PRIMARY KEY,
                parent_mission_id TEXT,
                turn_id TEXT,
                project_id TEXT,
                operator_id TEXT NOT NULL,
                contract_json TEXT NOT NULL,
                contract_digest TEXT NOT NULL,
                capability_digest TEXT,
                policy_version TEXT NOT NULL,
                state TEXT NOT NULL,
                exported_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_missions_project ON missions(project_id);
            CREATE INDEX IF NOT EXISTS idx_missions_turn ON missions(turn_id);
            CREATE INDEX IF NOT EXISTS idx_missions_state ON missions(state);
            CREATE INDEX IF NOT EXISTS idx_missions_contract_digest ON missions(contract_digest);

            CREATE TABLE IF NOT EXISTS mission_transitions (
                id INTEGER PRIMARY KEY,
                mission_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT,
                capability_digest TEXT,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY (mission_id) REFERENCES missions(mission_id)
            );

            CREATE INDEX IF NOT EXISTS idx_transitions_mission ON mission_transitions(mission_id);
            """
        )
