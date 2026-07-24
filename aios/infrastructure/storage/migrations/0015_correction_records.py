from __future__ import annotations

import sqlite3


class CorrectionRecordsMigration:
    """Organ 29: durable, append-only, digest-verified storage for
    `CorrectionRecordV1` -- previously `build_correction_record_v1()`/
    `record_correction_and_build_v1()`/`correction_lineage_v1()` had zero
    production callers anywhere in this codebase; the one real production
    correction route (`POST /api/v1/conversation/correction`) called
    `ConversationStateStore.record_correction()` directly and never built a
    typed record at all. `ConversationStateStore.conversation_corrections`
    remains the durable owner of the underlying before/after frames and
    revision/supersession lifecycle -- this table does not replace it, it
    is the typed, digest-verified, operator-attributed view organ 29's own
    contract promises, populated by a real caller for the first time.
    """

    version = 15
    name = "correction_records_v1"
    scope = "human_representation"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS correction_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                correction_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                base_revision INTEGER NOT NULL,
                correction_revision INTEGER NOT NULL,
                corrected_fields_json TEXT NOT NULL,
                prior_interpretation_digest TEXT NOT NULL,
                current_interpretation_digest TEXT NOT NULL,
                source TEXT NOT NULL,
                operator_id TEXT,
                created_at TEXT NOT NULL,
                record_digest TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_correction_records_session "
            "ON correction_records (session_id)"
        )
