"""SQLite persistence for local-clerk job/model-call/result provenance
(Slice 33).

Every row carries a `record_digest` (sha256 of the canonical-JSON dump of
the record, matching the convention already used by `MissionContract.
digest()` and `ConstitutionSnapshotV1`) computed at write time and
recomputed at read time -- a row edited outside this store without also
updating its digest is detected as tampered, not silently trusted.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from aios.domain.local_workforce.contracts import (
    LocalJobRequestRecord,
    LocalJobResultRecord,
    LocalModelCallRecord,
)
from aios.infrastructure.storage.migrations import apply_migrations


class RecordTamperedError(RuntimeError):
    """Raised when a stored record's digest no longer matches its content."""


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class LocalWorkforceProvenanceStore:
    """Durable store for `LocalJobRequestRecord`/`LocalModelCallRecord`/
    `LocalJobResultRecord`. Each table's primary key enforces exactly one
    row per job/model-call/result -- a duplicate insert for the same id is
    a database error, not a silent overwrite, so a retried request cannot
    create an ambiguous second lineage for the same job id."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="local_workforce")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save_job_request(self, record: LocalJobRequestRecord) -> None:
        payload = record.model_dump(mode="json")
        digest = _digest(payload)
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO local_job_requests (
                    job_id, mission_id, skill_id, skill_version, job_profile,
                    input_schema_version, qualification_suite_version,
                    model_allowlist_json, requested_model,
                    evidence_references_json, redacted_input_digest,
                    token_budget, deadline, created_at, record_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.job_id,
                    record.mission_id,
                    record.skill_id,
                    record.skill_version,
                    record.job_profile,
                    record.input_schema_version,
                    record.qualification_suite_version,
                    json.dumps(list(record.model_allowlist)),
                    record.requested_model,
                    json.dumps(list(record.evidence_references)),
                    record.redacted_input_digest,
                    record.token_budget,
                    record.deadline,
                    record.created_at,
                    digest,
                ),
            )
            conn.commit()

    def save_model_call(self, record: LocalModelCallRecord) -> None:
        payload = record.model_dump(mode="json")
        digest = _digest(payload)
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO local_model_calls (
                    local_model_call_id, local_job_id, provider, exact_model_id,
                    model_digest_version, qualification_version,
                    admission_record_id, request_digest, response_digest,
                    token_limits, measured_latency, start_time, end_time,
                    status, failure_reason, record_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.local_model_call_id,
                    record.local_job_id,
                    record.provider,
                    record.exact_model_id,
                    record.model_digest_version,
                    record.qualification_version,
                    record.admission_record_id,
                    record.request_digest,
                    record.response_digest,
                    record.token_limits,
                    record.measured_latency,
                    record.start_time,
                    record.end_time,
                    record.status,
                    record.failure_reason,
                    digest,
                ),
            )
            conn.commit()

    def save_job_result(self, record: LocalJobResultRecord) -> None:
        payload = record.model_dump(mode="json")
        digest = _digest(payload)
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO local_job_results (
                    local_job_id, local_model_call_id, schema_version,
                    structured_result_digest, schema_valid,
                    evidence_references_preserved, unsupported_claims_json,
                    status, failure_reason, record_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.local_job_id,
                    record.local_model_call_id,
                    record.schema_version,
                    record.structured_result_digest,
                    int(record.schema_valid),
                    int(record.evidence_references_preserved),
                    json.dumps(list(record.unsupported_claims)),
                    record.status,
                    record.failure_reason,
                    digest,
                ),
            )
            conn.commit()

    def get_job_request(self, job_id: str) -> LocalJobRequestRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM local_job_requests WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        record = LocalJobRequestRecord(
            job_id=row["job_id"],
            mission_id=row["mission_id"],
            skill_id=row["skill_id"],
            skill_version=row["skill_version"],
            job_profile=row["job_profile"],
            input_schema_version=row["input_schema_version"],
            qualification_suite_version=row["qualification_suite_version"],
            model_allowlist=tuple(json.loads(row["model_allowlist_json"])),
            requested_model=row["requested_model"],
            evidence_references=tuple(json.loads(row["evidence_references_json"])),
            redacted_input_digest=row["redacted_input_digest"],
            token_budget=row["token_budget"],
            deadline=row["deadline"],
            created_at=row["created_at"],
        )
        _verify(record, row["record_digest"])
        return record

    def get_model_calls_for_job(
        self, job_id: str
    ) -> tuple[LocalModelCallRecord, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM local_model_calls WHERE local_job_id = ? "
                "ORDER BY start_time",
                (job_id,),
            ).fetchall()
        records = []
        for row in rows:
            record = LocalModelCallRecord(
                local_model_call_id=row["local_model_call_id"],
                local_job_id=row["local_job_id"],
                provider=row["provider"],
                exact_model_id=row["exact_model_id"],
                model_digest_version=row["model_digest_version"],
                qualification_version=row["qualification_version"],
                admission_record_id=row["admission_record_id"],
                request_digest=row["request_digest"],
                response_digest=row["response_digest"],
                token_limits=row["token_limits"],
                measured_latency=row["measured_latency"],
                start_time=row["start_time"],
                end_time=row["end_time"],
                status=row["status"],
                failure_reason=row["failure_reason"],
            )
            _verify(record, row["record_digest"])
            records.append(record)
        return tuple(records)

    def get_job_result(self, job_id: str) -> LocalJobResultRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM local_job_results WHERE local_job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        record = LocalJobResultRecord(
            local_job_id=row["local_job_id"],
            local_model_call_id=row["local_model_call_id"],
            schema_version=row["schema_version"],
            structured_result_digest=row["structured_result_digest"],
            schema_valid=bool(row["schema_valid"]),
            evidence_references_preserved=bool(row["evidence_references_preserved"]),
            unsupported_claims=tuple(json.loads(row["unsupported_claims_json"])),
            status=row["status"],
            failure_reason=row["failure_reason"],
        )
        _verify(record, row["record_digest"])
        return record


def _verify(
    record: LocalJobRequestRecord | LocalModelCallRecord | LocalJobResultRecord,
    stored_digest: str,
) -> None:
    recomputed = _digest(record.model_dump(mode="json"))
    if recomputed != stored_digest:
        raise RecordTamperedError(
            f"stored record digest mismatch for {type(record).__name__}: "
            "the row was altered outside this store"
        )


__all__ = ["LocalWorkforceProvenanceStore", "RecordTamperedError"]
