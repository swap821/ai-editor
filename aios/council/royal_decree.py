"""Royal Decree planning for complex Council missions.

This module produces advisory evidence and narrowed worker contracts. It does
not execute scouts, approve work, or change the verifier path; the existing
Council deliberation -> King approval -> worker -> Testing Queen flow remains
the only action path.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aios.council.queens.planner import CouncilMissionRequest
from aios.runtime.castes import apply_caste_profile
from aios.runtime.contracts import MissionContract


@dataclass(frozen=True)
class RoyalDecreeDraft:
    decree_id: str
    advisory: bool
    scout_first: bool
    complexity_reasons: tuple[str, ...]
    scout_contract: MissionContract
    worker_contracts: tuple[MissionContract, ...]
    sequence: tuple[dict[str, Any], ...]

    def as_metadata(self) -> dict[str, Any]:
        return {
            "decree_id": self.decree_id,
            "advisory": self.advisory,
            "scout_first": self.scout_first,
            "complexity_reasons": list(self.complexity_reasons),
            "sequence": list(self.sequence),
            "scout_contract": self.scout_contract.model_dump(mode="json"),
            "worker_contracts": [
                contract.model_dump(mode="json") for contract in self.worker_contracts
            ],
            "authority": (
                "advisory only; Security Queen, verifier, and King approval remain authoritative"
            ),
        }


def complexity_reasons(
    *,
    goal: str,
    allowed_files: list[str],
    verification_commands: list[str],
) -> list[str]:
    reasons: list[str] = []
    lowered = goal.lower()
    keywords = (
        "integrate",
        "migration",
        "refactor",
        "phase",
        "complex",
        "multi",
        "security",
        "frontend",
        "backend",
        "tests",
    )
    if len(allowed_files) > 1:
        reasons.append("multiple allowed files")
    if verification_commands:
        reasons.append("explicit verification commands")
    if len(goal) >= 160:
        reasons.append("long mission goal")
    if any(keyword in lowered for keyword in keywords):
        reasons.append("complexity keyword in goal")
    return reasons


def should_use_royal_decree(request: CouncilMissionRequest) -> bool:
    return bool(
        complexity_reasons(
            goal=request.goal,
            allowed_files=list(request.allowed_files),
            verification_commands=list(request.verification_commands),
        )
    )


def draft_royal_decree(request: CouncilMissionRequest) -> RoyalDecreeDraft:
    reasons = tuple(
        complexity_reasons(
            goal=request.goal,
            allowed_files=list(request.allowed_files),
            verification_commands=list(request.verification_commands),
        )
        or ["operator requested royal decree"]
    )
    decree_id = f"decree-{request.mission_id}"
    scout_contract = apply_caste_profile(
        _contract_from_request(
            request,
            mission_id=f"{request.mission_id}-scout",
            worker_type="forager_worker",
            allowed_tools=["request_plan", "read_file"],
            verification_commands=[],
            caste="forager",
            metadata={
                "royal_decree_id": decree_id,
                "royal_decree_role": "scout",
                "royal_decree_advisory": True,
            },
        )
    )
    builder_contract = apply_caste_profile(
        _contract_from_request(
            request,
            mission_id=request.mission_id,
            worker_type=request.worker_type,
            allowed_tools=list(request.allowed_tools),
            verification_commands=list(request.verification_commands),
            caste="builder",
            metadata={
                "royal_decree_id": decree_id,
                "royal_decree_role": "builder",
                "royal_decree_advisory": True,
            },
        )
    )
    verifier_contract = apply_caste_profile(
        _contract_from_request(
            request,
            mission_id=f"{request.mission_id}-verify",
            worker_type="scout_worker",
            allowed_tools=["request_plan", "read_file", "run_command"],
            verification_commands=list(request.verification_commands),
            caste="scout",
            metadata={
                "royal_decree_id": decree_id,
                "royal_decree_role": "verifier",
                "royal_decree_advisory": True,
            },
        )
    )
    sequence = (
        {
            "stage": "scout",
            "contract_id": scout_contract.mission_id,
            "caste": scout_contract.metadata.get("caste"),
            "authority": "read-only evidence proposal",
        },
        {
            "stage": "council_review",
            "contract_id": builder_contract.mission_id,
            "authority": "Security Queen and Memory Queen review before approval",
        },
        {
            "stage": "execution",
            "contract_id": builder_contract.mission_id,
            "authority": "King approval required before worker spawn",
        },
        {
            "stage": "verification",
            "contract_id": verifier_contract.mission_id,
            "authority": "Testing Queen and verifier remain authoritative",
        },
        {
            "stage": "king_report",
            "contract_id": builder_contract.mission_id,
            "authority": "existing KingReport path",
        },
    )
    return RoyalDecreeDraft(
        decree_id=decree_id,
        advisory=True,
        scout_first=True,
        complexity_reasons=reasons,
        scout_contract=scout_contract,
        worker_contracts=(builder_contract, verifier_contract),
        sequence=sequence,
    )


def apply_royal_decree(
    request: CouncilMissionRequest,
    *,
    force: bool = False,
) -> CouncilMissionRequest:
    if not force and not should_use_royal_decree(request):
        return request
    decree = draft_royal_decree(request)
    builder = decree.worker_contracts[0]
    metadata = dict(request.metadata)
    metadata["caste"] = "builder"
    metadata["royal_decree"] = decree.as_metadata()
    metadata["royal_decree_advisory"] = True
    metadata["royal_decree_execution_gate"] = "king_approval"
    metadata["royal_decree_verifier_gate"] = "TestingQueen"
    return CouncilMissionRequest(
        mission_id=request.mission_id,
        goal=request.goal,
        workspace_root=request.workspace_root,
        allowed_files=list(request.allowed_files),
        forbidden_files=list(builder.forbidden_files),
        allowed_tools=list(builder.allowed_tools),
        forbidden_tools=list(builder.forbidden_tools),
        verification_commands=list(request.verification_commands),
        worker_type=request.worker_type,
        created_by=request.created_by,
        risk_level=request.risk_level,
        requires_approval=request.requires_approval,
        priority=request.priority,
        timeout_seconds=builder.timeout_seconds,
        max_steps=builder.max_steps,
        pheromone_context=list(request.pheromone_context),
        metadata=metadata,
    )


def _contract_from_request(
    request: CouncilMissionRequest,
    *,
    mission_id: str,
    worker_type: str,
    allowed_tools: list[str],
    verification_commands: list[str],
    caste: str,
    metadata: dict[str, Any],
) -> MissionContract:
    merged_metadata = dict(request.metadata)
    merged_metadata.update(metadata)
    merged_metadata["caste"] = caste
    return MissionContract(
        mission_id=mission_id,
        goal=request.goal,
        worker_type=worker_type,
        created_by="royal_decree",
        priority=request.priority,
        risk_level=request.risk_level,  # type: ignore[arg-type]
        requires_approval=True,
        workspace_root=str(Path(request.workspace_root)),
        allowed_files=list(request.allowed_files),
        forbidden_files=list(request.forbidden_files),
        allowed_tools=allowed_tools,
        forbidden_tools=list(request.forbidden_tools),
        timeout_seconds=request.timeout_seconds,
        max_steps=request.max_steps,
        verification_commands=verification_commands,
        pheromone_context=list(request.pheromone_context),
        metadata=merged_metadata,
    )


__all__ = [
    "RoyalDecreeDraft",
    "apply_royal_decree",
    "complexity_reasons",
    "draft_royal_decree",
    "should_use_royal_decree",
]
