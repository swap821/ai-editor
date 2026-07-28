"""Organ 38's named owner, and clerk-job provenance reconstruction (Slice 33).

Assembles the durable trace for one clerk job -- human request -> compiled
context -> clerk model -> clerk result -> validation -> escalation decision
-- from whatever `LocalWorkforceProvenanceStore` actually has persisted.
Missing pieces (a request with no model call yet, a model call with no
result yet) are represented honestly as absent, never fabricated, so this
reconstructs correctly even mid-crash.

The ledger has always named `ClerkProvenanceAuthority` as organ 38's
authority owner, but no such class existed anywhere -- the ledger's
`authority_owner` field was validated by string comparison against a
registry of strings, so a name that matched nothing was structurally
invisible (Decision A, docs/architecture/GAGOS_54_ORGANS.md). The
mechanism was real (`LocalWorkforceProvenanceStore`, genuinely wired into
`LocalWorkforceService.run_advisory_job()`'s real production path); only
the owner was missing. `ClerkProvenanceAuthority` is that owner: it moves
the write-side record-construction logic here from
`LocalWorkforceService._record_advisory_job_provenance` (previously
private, inline, and un-owned) and wraps the pre-existing read side
(`get_clerk_job_provenance`) -- one class answering both "what happened to
this job" and "durably record what just happened", not a rename.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from aios.domain.local_workforce.contracts import (
    LocalClerkProvenanceRecord,
    LocalJobRequest,
    LocalJobRequestRecord,
    LocalJobResult,
    LocalJobResultRecord,
    LocalModelCallRecord,
    LocalWorkerModel,
)
from aios.infrastructure.local_workforce import LocalWorkforceProvenanceStore


@dataclass(frozen=True, slots=True)
class ClerkJobProvenance:
    job_id: str
    request: LocalJobRequestRecord | None
    model_calls: tuple[LocalModelCallRecord, ...]
    result: LocalJobResultRecord | None

    @property
    def status(self) -> str:
        if self.request is None:
            return "unknown"
        if self.result is not None:
            return self.result.status
        if self.model_calls:
            return "model_call_recorded_awaiting_result"
        return "request_recorded_awaiting_model_call"

    def render(self) -> str:
        lines = [f"Human request -> job {self.job_id}"]
        if self.request is None:
            lines.append("  no request record found")
            return "\n".join(lines)
        lines.append(
            f"  profile={self.request.job_profile} "
            f"requested_model={self.request.requested_model}"
        )
        if not self.model_calls:
            lines.append("  -> no model call recorded yet")
        for call in self.model_calls:
            lines.append(
                f"  -> clerk model {call.exact_model_id} "
                f"({call.status}, {call.measured_latency}s)"
            )
        if self.result is None:
            lines.append("  -> no result recorded yet")
        else:
            lines.append(
                f"  -> result: {self.result.status} "
                f"(schema_valid={self.result.schema_valid})"
            )
        lines.append(f"  status: {self.status}")
        return "\n".join(lines)


def get_clerk_job_provenance(
    store: LocalWorkforceProvenanceStore, job_id: str
) -> ClerkJobProvenance:
    return ClerkJobProvenance(
        job_id=job_id,
        request=store.get_job_request(job_id),
        model_calls=store.get_model_calls_for_job(job_id),
        result=store.get_job_result(job_id),
    )


class ClerkProvenanceAuthority:
    """The one authority over what actually happened to a governed local
    clerical job: every real request, model call, and result, plus the
    hash-chained provenance record linking them."""

    def __init__(self, store: LocalWorkforceProvenanceStore) -> None:
        self.store = store

    def record_advisory_job(
        self,
        request: LocalJobRequest,
        result: LocalJobResult,
        decision: str,
        *,
        model: LocalWorkerModel | None,
    ) -> None:
        """Durably record one completed (or refused) job -- the real
        request, model call, and result, then the hash-chained provenance
        record connecting them. Recording happens after execution, from
        the same request/result objects a caller already sees, so it can
        never fabricate what actually happened; a rejection (no admitted
        model) is recorded as honestly as a success."""
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        request_digest = hashlib.sha256(
            request.redacted_payload.encode("utf-8")
        ).hexdigest()
        response_digest = hashlib.sha256(
            json.dumps(
                result.structured_output, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if result.structured_output is not None
            else b""
        ).hexdigest()
        call_id = f"local-call-{uuid.uuid4().hex}"

        self.store.save_job_request(
            LocalJobRequestRecord(
                job_id=request.job_id,
                job_profile=request.job_profile.value,
                input_schema_version=request.input_schema_version,
                requested_model=result.model_id,
                evidence_references=tuple(sorted(request.evidence_references)),
                redacted_input_digest=request_digest,
                token_budget=request.token_budget,
                deadline=request.deadline.isoformat(),
                created_at=now,
            )
        )
        self.store.save_model_call(
            LocalModelCallRecord(
                local_model_call_id=call_id,
                local_job_id=request.job_id,
                exact_model_id=result.model_id,
                request_digest=request_digest,
                response_digest=response_digest,
                token_limits=request.token_budget,
                measured_latency=result.latency,
                start_time=now,
                end_time=now,
                status=result.status,
                failure_reason=result.failure_reason,
            )
        )
        self.store.save_job_result(
            LocalJobResultRecord(
                local_job_id=request.job_id,
                local_model_call_id=call_id,
                structured_result_digest=response_digest,
                schema_valid=result.schema_valid,
                evidence_references_preserved=result.evidence_references_preserved,
                unsupported_claims=tuple(result.unsupported_claims),
                status=result.status,
                failure_reason=result.failure_reason,
            )
        )

        job_contract_digest = hashlib.sha256(
            request.model_dump_json().encode("utf-8")
        ).hexdigest()
        passport_digest = model.artifact_digest if model else None
        qual_evidence_digest = model.qualification_evidence_digest if model else None

        # previous_record_digest is deliberately NOT computed here: the
        # store owns the link, so the digest it writes and the link it
        # stores are produced by the same function and cannot disagree.
        self.store.save_provenance_record(
            LocalClerkProvenanceRecord(
                job_id=request.job_id,
                job_contract_digest=job_contract_digest,
                dispatcher_decision=decision,
                passport_digest=passport_digest,
                qualification_evidence_digest=qual_evidence_digest,
                representative_context_digest=None,
                model_request_digest=request_digest,
                model_result_digest=response_digest,
                validation_outcome="valid" if result.schema_valid else "invalid",
                escalation_outcome=None if decision == "local_clerk" else decision,
            )
        )

    def job_provenance(self, job_id: str) -> ClerkJobProvenance:
        return get_clerk_job_provenance(self.store, job_id)


__all__ = ["ClerkJobProvenance", "ClerkProvenanceAuthority", "get_clerk_job_provenance"]
