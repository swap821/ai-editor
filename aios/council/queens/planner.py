"""Planner Queen for the Council Runtime.

Phase 2 drafts a bounded MissionContract from a request. Phase 3 ("thinking
Queens") optionally consults an injected LLM to propose a real plan — but that
plan is reconciled narrow-only (see aios.council.reasoning), so reasoning can
make a mission more cautious/detailed and never escalate privilege.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aios import config
from aios.core.llm import LLMClient
from aios.council.reasoning import plan_with_llm, reconcile_plan
from aios.runtime.contracts import MissionContract, QueenVerdict
from aios.runtime.castes import apply_caste_profile, caste_from_contract

_LOGGER = logging.getLogger(__name__)


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
        default_factory=lambda: [
            "request_plan",
            "read_file",
            "write_file",
            "run_command",
        ]
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

    def __init__(self, llm: LLMClient | None = None) -> None:
        # Optional reasoning client. None (or config.COUNCIL_REASONING off) keeps
        # the Planner fully deterministic.
        self._llm = llm

    def draft(self, request: CouncilMissionRequest | MissionContract) -> PlannerDraft:
        confidence = 0.82
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

            if self._llm is not None and config.COUNCIL_REASONING:
                contract, confidence, reason, constraints = self._reason(
                    contract, reason, constraints
                )

        caste_profile = caste_from_contract(contract)
        if caste_profile is not None:
            contract = apply_caste_profile(contract, caste_profile)
            constraints = [
                *constraints,
                f"{caste_profile.name} caste profile applied; constraints can only narrow authority.",
            ]
        verdict = "allow_with_approval" if contract.requires_approval else "allow"
        risk = contract.risk_level
        if not contract.allowed_files:
            verdict = "defer"
            risk = "YELLOW"
            reason = "Planner cannot spawn a worker without allowed_files."
            constraints = ["Add at least one allowed file before worker birth."]
        elif not contract.verification_commands:
            verdict = "defer"
            risk = "YELLOW"
            reason = (
                "Planner cannot spawn a worker without explicit verification commands."
            )
            constraints = [
                *constraints,
                "Add at least one verification command before worker birth.",
            ]

        return PlannerDraft(
            contract=contract,
            verdict=QueenVerdict(
                queen=self.name,
                verdict=verdict,  # type: ignore[arg-type]
                risk=risk,
                reason=reason,
                constraints=constraints,
                confidence=confidence,
                metadata={
                    "worker_type": contract.worker_type,
                    "allowed_files": list(contract.allowed_files),
                    "verification_commands": list(contract.verification_commands),
                    "reasoned": bool(contract.metadata.get("council_plan")),
                },
            ),
        )

    def _reason(
        self,
        contract: MissionContract,
        reason: str,
        constraints: list[str],
    ) -> tuple[MissionContract, float, str, list[str]]:
        """Consult the LLM, reconcile narrow-only, return an updated contract.

        Any failure (transport, bad JSON, parse) falls back to the deterministic
        contract unchanged — reasoning can never make the mission less safe.
        """
        assert self._llm is not None
        try:
            plan = plan_with_llm(
                self._llm,
                goal=contract.goal,
                allowed_files=list(contract.allowed_files),
                risk=contract.risk_level,
            )
            reconciled = reconcile_plan(
                request_allowed=list(contract.allowed_files),
                request_forbidden=list(contract.forbidden_files),
                request_risk=contract.risk_level,
                request_requires_approval=contract.requires_approval,
                request_verification=list(contract.verification_commands),
                plan=plan,
            )
        except (ValueError, KeyError, TypeError) as exc:
            _LOGGER.warning("planner_reasoning_fallback", exc_info=exc)
            return contract, 0.82, reason, constraints

        metadata = dict(contract.metadata)
        metadata["council_plan"] = reconciled.steps
        reasoned = contract.model_copy(
            update={
                "allowed_files": reconciled.allowed_files,
                "forbidden_files": reconciled.forbidden_files,
                "risk_level": reconciled.risk_level,
                "requires_approval": reconciled.requires_approval,
                "verification_commands": reconciled.verification_commands,
                "metadata": metadata,
            }
        )
        new_constraints = [*constraints, "Planner reasoning applied (narrow-only)."]
        return (
            reasoned,
            reconciled.confidence,
            "MissionContract drafted with Planner reasoning (clamped to request bounds).",
            new_constraints,
        )


__all__ = ["CouncilMissionRequest", "PlannerDraft", "PlannerQueen"]
