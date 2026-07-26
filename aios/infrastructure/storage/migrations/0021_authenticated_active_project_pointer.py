from __future__ import annotations

import sqlite3


class AuthenticatedActiveProjectPointerMigration:
    """Bind the durable active-project pointer to an authenticated operator.

    Pointers written before this migration remain intentionally unbound and
    therefore cannot supply project material to authenticated chat.
    """

    version = 21
    name = "authenticated_active_project_pointer_v1"
    scope = "human_representation"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(active_project_pointer)")
        }
        if "operator_identity_digest" not in columns:
            conn.execute(
                "ALTER TABLE active_project_pointer "
                "ADD COLUMN operator_identity_digest TEXT"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_active_project_pointer_owner "
            "ON active_project_pointer(operator_identity_digest)"
        )