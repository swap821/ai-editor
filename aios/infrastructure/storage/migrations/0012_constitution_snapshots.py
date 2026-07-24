from __future__ import annotations

import sqlite3


class ConstitutionSnapshotsMigration:
    """Organ 45: durable, content-addressed history of `ConstitutionSnapshotV1`
    plus a per-constitution "current" pointer.

    `build_constitution_snapshot()`'s own docstring already documents that it
    "does not persist a chain across process restarts" -- before this,
    `activate_amendment_route()` rebuilt a fresh, ephemeral "previous"
    snapshot on every single call (never reading anything it had produced
    before), so every activation looked like the very first one and nothing
    was ever available for `rollback_amendment()` to find "the exact
    predecessor" of.

    Snapshots are keyed by their own content digest (`snapshot_digest`), not
    by `(constitution_id, version)` -- a rollback re-points the current
    pointer at an *existing* row rather than inserting a duplicate, since
    `rollback_amendment()`'s own contract is "revert to the exact
    predecessor", not "create a new version equal to an old one".
    """

    version = 12
    name = "constitution_snapshots_v1"
    scope = "constitution"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS constitution_snapshots (
                snapshot_digest TEXT PRIMARY KEY,
                constitution_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_constitution_snapshots_constitution
                ON constitution_snapshots(constitution_id);

            CREATE TABLE IF NOT EXISTS constitution_current_pointer (
                constitution_id TEXT PRIMARY KEY,
                snapshot_digest TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
