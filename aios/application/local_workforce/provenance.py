"""Clerk-job provenance reconstruction (Slice 33).

Assembles the durable trace for one clerk job -- human request -> compiled
context -> clerk model -> clerk result -> validation -> escalation decision
-- from whatever `LocalWorkforceProvenanceStore` actually has persisted.
Missing pieces (a request with no model call yet, a model call with no
result yet) are represented honestly as absent, never fabricated, so this
reconstructs correctly even mid-crash.
"""

from __future__ import annotations

from dataclasses import dataclass

from aios.domain.local_workforce.contracts import (
    LocalJobRequestRecord,
    LocalJobResultRecord,
    LocalModelCallRecord,
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


__all__ = ["ClerkJobProvenance", "get_clerk_job_provenance"]
