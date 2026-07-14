"""Target-specific verification authority built on the existing strength rules."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from aios.application.evidence.authority import EvidenceAuthority
from aios.core.verification_strength import derive_strength
from aios.domain.evidence import (
    VerificationObservation,
    VerificationPlanV1,
    VerificationResult,
)
from aios.domain.verification import aggregate_strength, evidence_is_fresh


class VerificationAuthority:
    """Challenge results against a plan and canonical workspace identity."""

    def __init__(self, evidence: EvidenceAuthority | None = None) -> None:
        self.evidence = evidence or EvidenceAuthority()
        self._results: dict[str, VerificationResult] = {}

    def verify(
        self,
        *,
        mission_id: str,
        action_id: str,
        worker_id: str,
        target: str,
        plan: VerificationPlanV1,
        workspace_digest: str,
        diff_digest: str,
        environment_digest: str,
        observation: VerificationObservation,
    ) -> VerificationResult:
        if plan.targets and target not in plan.targets:
            raise ValueError(f"verification target is not in plan: {target}")
        passed = observation.exit_code == 0
        strength = int(
            derive_strength(
                passed=passed,
                passed_count=observation.passed_count,
                failed_count=observation.failed_count,
                command=observation.command,
            )
        )
        output = observation.stdout + "\n" + observation.stderr
        output_digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        evidence = self.evidence.record(
            mission_id=mission_id,
            action_id=action_id,
            worker_id=worker_id,
            evidence_type="test",
            source="verification_authority",
            content=output,
            environment_digest=environment_digest,
            tool_version=observation.tool_version,
            trust_level="verified" if passed else "failed",
            verification_strength=strength,
            metadata={"target": target, "command": observation.command},
        )
        result = VerificationResult(
            verification_id=f"verification-{uuid.uuid4().hex}",
            mission_id=mission_id,
            action_id=action_id,
            target=target,
            passed=passed,
            strength=strength,
            required_strength=plan.minimum_strength,
            evidence_ids=(evidence.evidence_id,),
            workspace_digest=workspace_digest,
            diff_digest=diff_digest,
            environment_digest=environment_digest,
            command=observation.command,
            output_digest=output_digest,
            tool_version=observation.tool_version,
            observed_at=observation.observed_at,
        )
        self._results[result.verification_id] = result
        return result

    def is_current(
        self,
        result: VerificationResult,
        *,
        workspace_digest: str,
        diff_digest: str,
        now: str | None = None,
        freshness_seconds: int = 300,
    ) -> bool:
        return (
            result.workspace_digest == workspace_digest
            and result.diff_digest == diff_digest
            and evidence_is_fresh(
                result.observed_at,
                now=now or _utc_now(),
                freshness_seconds=freshness_seconds,
            )
        )

    def promotion_strength(self, results: list[VerificationResult]) -> int:
        return aggregate_strength(
            result.strength if result.meets_requirement else 0 for result in results
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = ["VerificationAuthority"]
