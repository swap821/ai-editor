"""Reflection Queen — deterministic second-order review based on prior outcomes.

This Queen does not call external models. It inspects mission metadata for prior
failures and current risk, then adds strengthen-only constraints.
"""
from __future__ import annotations

from aios.runtime.contracts import MissionContract, QueenEvidence, QueenVerdict


class ReflectionQueen:
    """Apply lessons from prior failures to tighten mission constraints."""

    name = "reflection"

    def review(self, contract: MissionContract) -> QueenVerdict:
        prior_failures = contract.metadata.get("prior_failure_count", 0)
        prior_patterns = contract.metadata.get("prior_failure_patterns", [])
        checks: list[dict] = [
            {"kind": "prior_failure_count", "value": prior_failures},
            {"kind": "prior_failure_patterns", "value": list(prior_patterns)},
        ]
        constraints: list[str] = []
        risk = contract.risk_level

        if prior_failures > 0:
            constraints.append(
                f"reflection: mission has {prior_failures} prior failure(s); require stronger verification"
            )
            checks.append({"kind": "escalation", "value": "stronger_verification"})
            if risk == "GREEN":
                risk = "YELLOW"

        if "verification_flake" in prior_patterns:
            constraints.append(
                "reflection: prior verification flake detected; require idempotent commands"
            )

        if "scope_creep" in prior_patterns:
            constraints.append(
                "reflection: prior scope creep detected; allowed_files may not expand during execution"
            )

        return QueenVerdict(
            queen=self.name,
            verdict="allow" if not constraints else "allow_with_approval",
            risk=risk,
            reason="Reflection Queen applied prior-failure lessons (strengthen-only).",
            constraints=constraints,
            confidence=0.85,
            confidence_basis="mission metadata and deterministic prior-failure rules",
            evidence=QueenEvidence(
                basis="contract.metadata.prior_failure_count and prior_failure_patterns",
                checks=checks,
            ),
            recommended_worker_strategy=None,
            unresolved_questions=[
                "Have prior failures for this mission pattern been reviewed by the operator?"
            ] if prior_failures > 0 else [],
            metadata={"prior_failures": prior_failures, "patterns": list(prior_patterns)},
        )


__all__ = ["ReflectionQueen"]
