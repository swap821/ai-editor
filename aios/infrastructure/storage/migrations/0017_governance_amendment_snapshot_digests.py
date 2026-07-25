from __future__ import annotations

import sqlite3


class GovernanceAmendmentSnapshotDigestsMigration:
    """Organ 45 -- add activated_snapshot_digest and predecessor_snapshot_digest columns."""

    version = 17
    name = "governance_amendment_snapshot_digests"
    scope = "governance"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(governance_amendment_proposals)")}
        if "activated_snapshot_digest" not in columns:
            conn.execute(
                "ALTER TABLE governance_amendment_proposals ADD COLUMN activated_snapshot_digest TEXT"
            )
        if "predecessor_snapshot_digest" not in columns:
            conn.execute(
                "ALTER TABLE governance_amendment_proposals ADD COLUMN predecessor_snapshot_digest TEXT"
            )
