from __future__ import annotations

import sqlite3


class LocalWorkforceProvenanceMigration:
    """Slice 33 — durable local-clerk job/model-call/result provenance."""

    version = 5
    name = "local_workforce_provenance_v1"
    scope = "local_workforce"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS local_job_requests (
                job_id TEXT PRIMARY KEY,
                mission_id TEXT,
                skill_id TEXT,
                skill_version INTEGER,
                job_profile TEXT NOT NULL,
                input_schema_version TEXT NOT NULL,
                qualification_suite_version TEXT NOT NULL,
                model_allowlist_json TEXT NOT NULL,
                requested_model TEXT NOT NULL,
                evidence_references_json TEXT NOT NULL,
                redacted_input_digest TEXT NOT NULL,
                token_budget INTEGER NOT NULL,
                deadline TEXT NOT NULL,
                created_at TEXT NOT NULL,
                record_digest TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS local_model_calls (
                local_model_call_id TEXT PRIMARY KEY,
                local_job_id TEXT NOT NULL REFERENCES local_job_requests(job_id),
                provider TEXT NOT NULL,
                exact_model_id TEXT NOT NULL,
                model_digest_version TEXT,
                qualification_version TEXT NOT NULL,
                admission_record_id TEXT,
                request_digest TEXT NOT NULL,
                response_digest TEXT NOT NULL,
                token_limits INTEGER NOT NULL,
                measured_latency REAL NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                status TEXT NOT NULL,
                failure_reason TEXT,
                record_digest TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_local_model_calls_job
                ON local_model_calls(local_job_id);
            CREATE TABLE IF NOT EXISTS local_job_results (
                local_job_id TEXT PRIMARY KEY REFERENCES local_job_requests(job_id),
                local_model_call_id TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                structured_result_digest TEXT NOT NULL,
                schema_valid INTEGER NOT NULL,
                evidence_references_preserved INTEGER NOT NULL,
                unsupported_claims_json TEXT NOT NULL,
                status TEXT NOT NULL,
                failure_reason TEXT,
                record_digest TEXT NOT NULL
            );
            """
        )
