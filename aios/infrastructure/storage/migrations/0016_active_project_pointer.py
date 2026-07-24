from __future__ import annotations

import sqlite3


class ActiveProjectPointerMigration:
    """Organ 28: a durable pointer to the most recently scanned project.

    Previously `aios/api/routes/projects.py` tracked "which project was
    last scanned" (and its summary) with two process-local module
    globals -- real durable history already existed in
    `project_passports` via `ProjectPassportStore`, but nothing recorded
    *which* project_id to look it up under, so `GET .../passport/status`
    silently forgot everything on every process restart even though the
    underlying scan history was still sitting on disk.

    A true singleton row (`id = 1`, enforced by the CHECK constraint):
    this system tracks one active project at a time, matching the
    existing routes' own single-workspace design -- this migration makes
    that state durable, it does not add multi-project tracking that
    didn't exist before.
    """

    version = 16
    name = "active_project_pointer_v1"
    scope = "human_representation"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_project_pointer (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                project_id TEXT NOT NULL,
                last_scan_summary_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
