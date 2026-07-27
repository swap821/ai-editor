from __future__ import annotations

import sqlite3


class MissionTransitionHashChainMigration:
    """Organ 42 — tamper-evidence for the mission transition journal.

    The journal recorded (mission_id, transition, sequence, recorded_at) and
    nothing else, so a row could be edited, deleted or reordered on disk with
    no way to tell. Resumption reads this journal to decide how far a mission
    actually got, which makes silent alteration a correctness problem and not
    only an audit one.

    Columns are added nullable on purpose. This table already exists in
    deployed data directories, and rows written before the chain existed
    cannot be retro-signed without inventing evidence. `verify_chain()`
    reports those legacy rows as unverifiable rather than passing them off as
    verified.
    """

    version = 23
    name = "mission_transition_hash_chain_v1"
    scope = "missions"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        # Index access, not row["name"]: this runs against whatever connection
        # apply_migrations was handed, which may not have a Row factory set.
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(mission_execution_transitions)")
        }
        if "previous_entry_digest" not in existing:
            conn.execute(
                "ALTER TABLE mission_execution_transitions "
                "ADD COLUMN previous_entry_digest TEXT"
            )
        if "entry_digest" not in existing:
            conn.execute(
                "ALTER TABLE mission_execution_transitions ADD COLUMN entry_digest TEXT"
            )
