from __future__ import annotations

import sqlite3


class HumanStateCorrectionsMigration:
    """Organ 30: adds a real ground-truth correction slot to each stored
    `classify_human_state()` hypothesis.

    `human_state_hypotheses` (migration 0010) recorded every hypothesis but
    had no way to record whether it was actually right -- the classifier's
    own accuracy against real production traffic (not synthetic test
    examples) could never be measured. `corrected_state`/`corrected_at` are
    nullable, added via `ALTER TABLE` rather than a new table, since a
    correction is naturally a property of the one hypothesis row it
    corrects, not a separate event stream (`HumanStateHypothesis`'s own
    digest formula hashes only its own fields -- state/confidence/
    visible_reason/user_correctable/grants_authority -- so adding these
    columns does not invalidate any existing row's tamper-detection digest).
    """

    version = 13
    name = "human_state_corrections_v1"
    scope = "human_representation"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(human_state_hypotheses)")
        }
        if "corrected_state" not in columns:
            conn.execute(
                "ALTER TABLE human_state_hypotheses ADD COLUMN corrected_state TEXT"
            )
        if "corrected_at" not in columns:
            conn.execute(
                "ALTER TABLE human_state_hypotheses ADD COLUMN corrected_at TEXT"
            )
