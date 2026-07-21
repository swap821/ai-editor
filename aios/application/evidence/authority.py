"""Evidence authority: provenance, redaction and durable record creation."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Callable

from aios.domain.evidence import EvidenceBundle, EvidenceCommand, EvidenceRecord
from aios.runtime.secret_policy import SecretPolicy


class EvidenceAuthority:
    """Create canonical evidence without treating worker prose as proof."""

    def __init__(
        self,
        *,
        secret_policy: SecretPolicy | None = None,
        sink: Callable[[EvidenceRecord], None] | None = None,
    ) -> None:
        self.secret_policy = secret_policy or SecretPolicy()
        self.sink = sink
        self._records: dict[str, EvidenceRecord] = {}

    def record(
        self,
        *,
        mission_id: str,
        action_id: str,
        worker_id: str,
        evidence_type: str,
        source: str,
        content: str,
        environment_digest: str,
        tool_version: str,
        trust_level: str = "observed",
        verification_strength: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceRecord:
        safe_content = self.secret_policy.redact_text(content)
        safe_metadata = _redact_json(self.secret_policy, metadata or {})
        digest = hashlib.sha256(safe_content.encode("utf-8")).hexdigest()
        evidence = EvidenceRecord(
            evidence_id=f"evidence-{uuid.uuid4().hex}",
            mission_id=mission_id,
            action_id=action_id,
            worker_id=worker_id,
            evidence_type=evidence_type,
            source=source,
            content_reference=f"inline:{digest}",
            content_digest=digest,
            redaction_status="redacted_or_clean",
            environment_digest=environment_digest,
            tool_version=tool_version,
            trust_level=trust_level,
            verification_strength=verification_strength,
            metadata=safe_metadata,
        )
        self._records[evidence.evidence_id] = evidence
        if self.sink is not None:
            self.sink(evidence)
        return evidence

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return self._records.get(evidence_id)

    def records_for(self, mission_id: str) -> tuple[EvidenceRecord, ...]:
        return tuple(
            record
            for record in self._records.values()
            if record.mission_id == mission_id
        )

    def bundle(
        self,
        *,
        mission_id: str,
        worker_id: str,
        contract_digest: str,
        workspace_digest: str,
        diff_digest: str,
        executor_job_id: str,
        environment_digest: str,
        commands: list[dict[str, Any]],
        verification_strength: int,
        targets_exercised: tuple[str, ...],
        started_at: str,
        ended_at: str,
    ) -> EvidenceBundle:
        """Build a redacted, digest-bound bundle from executor observations."""
        normalized: list[EvidenceCommand] = []
        for entry in commands:
            raw_command = entry.get("command", "")
            command = (
                raw_command
                if isinstance(raw_command, str)
                else " ".join(str(part) for part in raw_command)
            )
            stdout = self.secret_policy.redact_text(str(entry.get("stdout") or ""))
            stderr = self.secret_policy.redact_text(str(entry.get("stderr") or ""))
            normalized.append(
                EvidenceCommand(
                    command=command,
                    return_code=entry.get("returncode"),
                    stdout_digest=hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
                    stderr_digest=hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
                    tool_version=str(entry.get("tool_version") or "unknown"),
                    observed_at=str(entry.get("observed_at") or ended_at),
                )
            )
        return EvidenceBundle(
            mission_id=mission_id,
            worker_id=worker_id,
            contract_digest=contract_digest,
            workspace_digest=workspace_digest,
            diff_digest=diff_digest,
            executor_job_id=executor_job_id,
            environment_digest=environment_digest,
            commands=tuple(normalized),
            verification_strength=verification_strength,
            targets_exercised=targets_exercised,
            started_at=started_at,
            ended_at=ended_at,
        )


def _redact_json(policy: SecretPolicy, value: Any) -> Any:
    if isinstance(value, str):
        return policy.redact_text(value)
    if isinstance(value, list):
        return [_redact_json(policy, item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_json(policy, item) for key, item in value.items()}
    return value


__all__ = ["EvidenceAuthority"]
