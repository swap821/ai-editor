from __future__ import annotations

import sqlite3


class ClerkProvenanceHashChainMigration:
    """Slice 38 — Organ 38 hash chain table."""

    version = 22
    name = "clerk_provenance_hash_chain_v1"
    scope = "local_workforce"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS local_clerk_provenance_chain (
                job_id TEXT PRIMARY KEY,
                job_contract_digest TEXT NOT NULL,
                dispatcher_decision TEXT NOT NULL,
                passport_digest TEXT,
                qualification_evidence_digest TEXT,
                representative_context_digest TEXT,
                model_request_digest TEXT,
                model_result_digest TEXT,
                validation_outcome TEXT,
                escalation_outcome TEXT,
                previous_record_digest TEXT,
                record_digest TEXT NOT NULL
            )
            """
        )
