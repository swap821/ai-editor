from __future__ import annotations

import sqlite3


class RepresentativeContextsMigration:
    """Organ 31: durable, append-only record of every `RepresentativeContextV1`
    `compile_representative_context()` produces for a real gateway-routed
    model call.

    Before this, a compiled context existed only as an in-memory return value
    -- the sole production caller (`aios.council.gateway_reasoning.
    GatewayRoutedCouncilLLMClient`) exposed its digest as a side-channel
    attribute and a log line, both of which are lost on process restart or
    log rotation. This table is the missing durable half, the same
    append-only-per-request shape `DeliberationStore`/`GovernanceAmendmentStore`
    already established -- one row per `request_id`, never overwritten.
    """

    version = 11
    name = "representative_contexts_v1"
    scope = "intelligence"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS representative_contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                operator_identity_digest TEXT NOT NULL,
                constitution_digest TEXT NOT NULL,
                privacy_classification TEXT NOT NULL,
                context_json TEXT NOT NULL,
                context_digest TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_representative_contexts_operator
                ON representative_contexts(operator_identity_digest);
            """
        )
