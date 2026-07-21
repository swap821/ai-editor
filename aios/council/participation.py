"""Adaptive Queen Council participation policy.

Determines which Queens must participate in a deliberation based on mission
attributes. The policy is fail-closed: any ambiguity increases scrutiny rather
than reducing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aios.runtime.contracts import MissionContract, QueenVerdict


@dataclass(frozen=True)
class CouncilParticipation:
    """Participation decision for one deliberation."""

    required: tuple[str, ...]
    optional: tuple[str, ...]
    reason: str


class CouncilParticipationPolicy:
    """Deterministic policy for Queen Council composition."""

    DEFAULT_REQUIRED = ("planner", "security", "memory", "testing")
    OPTIONAL_QUEENS = ("routing", "reflection", "project_understanding", "critique")

    def decide(
        self,
        contract: MissionContract,
        prior_verdicts: list[QueenVerdict] | None = None,
    ) -> CouncilParticipation:
        prior_verdicts = prior_verdicts or []
        optional: list[str] = []
        reasons: list[str] = [
            "default required Queens: planner, security, memory, testing"
        ]

        if self._needs_routing(contract):
            optional.append("routing")
            reasons.append(
                "mission requires routing (multi-strategy or model selection)"
            )

        if self._needs_reflection(contract, prior_verdicts):
            optional.append("reflection")
            reasons.append("high-risk or prior failures trigger reflection")

        if self._needs_project_understanding(contract):
            optional.append("project_understanding")
            reasons.append("complex scope or project context requested")

        if self._needs_critique(contract):
            optional.append("critique")
            reasons.append("high-risk or strong verification requires critique")

        # Full Council (all optional) only when justified.
        if len(optional) == len(self.OPTIONAL_QUEENS):
            reasons.append("full optional Council invoked because all conditions met")
        elif not optional:
            reasons.append("minimal Council justified by mission attributes")
        else:
            reasons.append(f"partial optional Council: {', '.join(optional)}")

        return CouncilParticipation(
            required=self.DEFAULT_REQUIRED,
            optional=tuple(optional),
            reason="; ".join(reasons),
        )

    def _needs_routing(self, contract: MissionContract) -> bool:
        return (
            len(contract.allowed_files) > 3
            or "swarm" in contract.worker_type.lower()
            or "role_pass" in contract.worker_type.lower()
            or "model_policy" in contract.metadata
            or contract.metadata.get("requires_model_routing") is True
        )

    def _needs_reflection(
        self,
        contract: MissionContract,
        prior_verdicts: list[QueenVerdict],
    ) -> bool:
        if contract.risk_level == "RED":
            return True
        if contract.metadata.get("prior_failure_count", 0) > 0:
            return True
        if any(v.verdict == "deny" for v in prior_verdicts):
            return True
        return False

    def _needs_project_understanding(self, contract: MissionContract) -> bool:
        return (
            contract.metadata.get("project_id") is not None
            or contract.metadata.get("complex_task") is True
            or len(contract.goal) > 200
        )

    def _needs_critique(self, contract: MissionContract) -> bool:
        return (
            contract.risk_level in {"YELLOW", "RED"}
            or contract.metadata.get("verification_strength") in {"moderate", "strong"}
            or any(
                "strong" in str(cmd).lower() for cmd in contract.verification_commands
            )
        )

    def explain(
        self,
        contract: MissionContract,
        prior_verdicts: list[QueenVerdict] | None = None,
    ) -> dict[str, Any]:
        participation = self.decide(contract, prior_verdicts)
        return {
            "required": list(participation.required),
            "optional": list(participation.optional),
            "reason": participation.reason,
            "full_council": len(participation.optional) == len(self.OPTIONAL_QUEENS),
        }


__all__ = ["CouncilParticipation", "CouncilParticipationPolicy"]
