"""Project-Understanding Queen — deterministic context adapter.

This Queen does not call external models. It inspects the mission scope and
project metadata, then adds constraints to keep the mission aligned with the
project context.
"""
from __future__ import annotations

from aios.runtime.contracts import MissionContract, QueenEvidence, QueenVerdict


class ProjectUnderstandingQueen:
    """Align a mission with known project context without widening scope."""

    name = "project_understanding"

    def review(self, contract: MissionContract) -> QueenVerdict:
        project_id = contract.metadata.get("project_id")
        checks: list[dict] = [{"kind": "project_id", "value": project_id}]
        constraints: list[str] = []
        questions: list[str] = []

        if project_id:
            constraints.append(
                f"project_understanding: mission scoped to project '{project_id}'"
            )
        else:
            questions.append("Which project context should constrain this mission?")

        if contract.metadata.get("complex_task"):
            constraints.append(
                "project_understanding: complex_task flag set; require explicit milestone breakdown"
            )
            checks.append({"kind": "complex_task", "value": True})

        if len(contract.goal) > 200:
            constraints.append(
                "project_understanding: long goal; require explicit success criteria"
            )
            checks.append({"kind": "goal_length", "value": len(contract.goal)})

        return QueenVerdict(
            queen=self.name,
            verdict="allow",
            risk=contract.risk_level,
            reason="Project-Understanding Queen aligned mission to project context.",
            constraints=constraints,
            confidence=0.86,
            confidence_basis="contract metadata and deterministic scope rules",
            evidence=QueenEvidence(
                basis="contract.metadata.project_id, complex_task, goal length",
                checks=checks,
            ),
            recommended_worker_strategy=None,
            unresolved_questions=questions,
            metadata={"project_id": project_id, "complex_task": contract.metadata.get("complex_task")},
        )


__all__ = ["ProjectUnderstandingQueen"]
