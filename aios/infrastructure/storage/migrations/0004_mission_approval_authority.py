from __future__ import annotations

import sqlite3


class MissionApprovalAuthorityMigration:
    """R6 — bind mission approval to the exact human-authenticated action."""

    version = 4
    name = "mission_approval_authority_v1"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        mission_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(missions)").fetchall()
        }
        if "runtime_contract_digest" not in mission_columns:
            conn.execute("ALTER TABLE missions ADD COLUMN runtime_contract_digest TEXT")
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(mission_transitions)").fetchall()
        }
        for name in ("contract_digest", "authentication_event_id", "session_id"):
            if name not in columns:
                conn.execute(f"ALTER TABLE mission_transitions ADD COLUMN {name} TEXT")
