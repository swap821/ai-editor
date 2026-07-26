from __future__ import annotations

import sqlite3


class AuthenticatedPreferenceBindingsMigration:
    """Bind newly stated preferences to an authenticated operator.

    Ownership stays outside ``OperatorPreferenceV1`` because its historical
    record digest intentionally covers only the original preference contract.
    Rows written before this migration remain unbound and are therefore never
    eligible for authenticated representative context.
    """

    version = 19
    name = "authenticated_preference_bindings_v1"
    scope = "human_representation"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(operator_preference_sidecar)")
        }
        if "operator_identity_digest" not in columns:
            conn.execute(
                "ALTER TABLE operator_preference_sidecar "
                "ADD COLUMN operator_identity_digest TEXT"
            )
        if "owner_binding_digest" not in columns:
            conn.execute(
                "ALTER TABLE operator_preference_sidecar "
                "ADD COLUMN owner_binding_digest TEXT"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_operator_preference_sidecar_owner_scope "
            "ON operator_preference_sidecar(operator_identity_digest, scope)"
        )