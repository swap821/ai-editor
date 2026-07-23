from __future__ import annotations

import sqlite3


class DeliberationRecordsMigration:
    """Organ 39: durable, append-only history for `DeliberationRecord`
    (Slice 34's contract, `aios/domain/intelligence/deliberation.py`).

    `synthesize_deliberation()` had zero durable storage before this
    migration -- every record it built existed only for the caller's own
    stack frame. Rows are append-only per `(deliberation_id, revision)`,
    matching the correction-lineage / governance-amendment convention
    already established (Slice 28 / Slice 37) rather than upserted in
    place, so a re-synthesis (e.g. after resolving a security concern)
    keeps the prior version inspectable.
    """

    version = 9
    name = "deliberation_records_v1"
    scope = "council"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS deliberation_records (
                deliberation_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                mission_id TEXT,
                trigger_reasons_json TEXT NOT NULL,
                positions_json TEXT NOT NULL,
                disagreements_json TEXT NOT NULL,
                unresolved_minority_concerns_json TEXT NOT NULL,
                final_disposition TEXT NOT NULL,
                created_at TEXT NOT NULL,
                deliberation_digest TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (deliberation_id, revision)
            );
            CREATE INDEX IF NOT EXISTS idx_deliberation_records_mission
                ON deliberation_records(mission_id);
            """
        )
