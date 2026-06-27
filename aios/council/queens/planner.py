"""Planner Queen for simulated Council Runtime Phase 2."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aios.runtime.contracts import MissionContract, QueenVerdict


@dataclass(frozen=True)
class CouncilMissionRequest:
    """Human/Council input used to draft a v0.1 MissionContract."""

    mission_id: str
    goal: str
    workspace_root: str | Path
    allowed_files: list[str]
    forbidden_files: list[str] = field(
        default_factory=lambda: ["backend/", ".env", "aios/security/"]
    )
    allowed_tools: list[str] = field(
        default_factory=lambda: ["request_plan", "read_file", "write_file", "run_command"]
    )
    forbidden_tools: list[str] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    worker_type: str = "hybrid_plan_worker"
    created_by: str = "planner_queen"
    risk_level: str = "YELLOW"
    requires_approval: bool = True
    priority: int = 0
    timeout_seconds: int = 600
    max_steps: int = 12
    pheromone_context: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannerDraft:
    """Planner output: the contract draft plus the queen verdict for the ledger."""

    contract: MissionContract
    verdict: QueenVerdict


class PlannerQueen:
    """Draft MissionContracts without becoming execution authority."""

    name = "planner"

    def draft(self, request: CouncilMissionRequest | MissionContract) -> PlannerDraft:
        if isinstance(request, MissionContract):
            contract = request
            reason = "Existing MissionContract accepted for Council review."
            constraints = ["Existing contract must still pass Security Queen review."]
        else:
            metadata = dict(request.metadata)
            if "request_plan" in request.allowed_tools:
                metadata.setdefault(
                    "hybrid_plan_prompt",
                    f"Create a bounded plan for this mission: {request.goal}",
                )
            contract = MissionContract(
                mission_id=request.mission_id,
                goal=request.goal,
                worker_type=request.worker_type,
                created_by=request.created_by,
                priority=request.priority,
                risk_level=request.risk_level,  # type: ignore[arg-type]
                requires_approval=request.requires_approval,
                workspace_root=str(Path(request.workspace_root)),
                allowed_files=list(request.allowed_files),
                forbidden_files=list(request.forbidden_files),
                allowed_tools=list(request.allowed_tools),
                forbidden_tools=list(request.forbidden_tools),
                timeout_seconds=request.timeout_seconds,
                max_steps=request.max_steps,
                verification_commands=list(request.verification_commands),
                pheromone_context=list(request.pheromone_context),
                metadata=metadata,
            )
            reason = "MissionContract drafted from CouncilMissionRequest."
            constraints = ["Worker execution remains bounded by MissionContract."]

        verdict = "allow_with_approval" if contract.requires_approval else "allow"
        risk = contract.risk_level
        if not contract.allowed_files:
            verdict = "defer"
            risk = "YELLOW"
            reason = "Planner cannot spawn a worker without allowed_files."
            constraints = ["Add at least one allowed file before worker birth."]

        return PlannerDraft(
            contract=contract,
            verdict=QueenVerdict(
                queen=self.name,
                verdict=verdict,  # type: ignore[arg-type]
                risk=risk,
                reason=reason,
                constraints=constraints,
                confidence=0.82,
                metadata={
                    "worker_type": contract.worker_type,
                    "allowed_files": list(contract.allowed_files),
                    "verification_commands": list(contract.verification_commands),
                },
            ),
        )


__all__ = ["CouncilMissionRequest", "PlannerDraft", "PlannerQueen"]
