from __future__ import annotations

import sqlite3


class RepresentativeContextReceiptsMigration:
    """Append-only authenticated-chat receipt sidecar.

    Historical representative contexts remain untouched: their context JSON
    was canonically digested before receipts existed. The sidecar is linked by
    request id and context digest so a modern governed chat can persist the
    complete audit receipt atomically without invalidating old records.
    """

    version = 18
    name = "representative_context_receipts_v1"
    scope = "intelligence"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS representative_context_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                context_digest TEXT NOT NULL,
                operator_identity_digest TEXT NOT NULL,
                constitution_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                receipt_json TEXT NOT NULL,
                receipt_digest TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_representative_context_receipts_operator
                ON representative_context_receipts(operator_identity_digest);
            CREATE INDEX IF NOT EXISTS idx_representative_context_receipts_expiry
                ON representative_context_receipts(expires_at);
            """
        )