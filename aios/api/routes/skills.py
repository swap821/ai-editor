"""API routes for managing the Skill Library."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import get_learning_service, get_skill_repository
from aios.application.learning.service import (
    LearningService,
    SkillActivationAuthorization,
    SkillActivationDenied,
)
from aios.domain.capabilities.proof import ConsumedCapabilityProof

router = APIRouter(
    tags=["skill-library"], dependencies=[Depends(enforce_action_boundary)]
)


class ActivateSkillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str = ""
    capability_digest: str = ""


class SkillReuseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    version: int
    mission_id: str
    goal: str
    project_id: str
    current_inputs: dict[str, str]
    current_state: dict[str, str]
    current_scope: str
    mission_allowed_tools: tuple[str, ...] = Field(default_factory=tuple)
    validated_version: str


@router.get("/api/v1/skills")
def list_skills(
    repository: SkillRepository = Depends(get_skill_repository),
) -> dict[str, Any]:
    """List only persisted institutional skills."""
    items = [skill.model_dump(mode="json") for skill in repository.list_skills()]
    return {
        "items": items,
        "status": "available" if items else "empty",
        "source": "durable_repository",
    }


@router.post("/api/v1/skills/{skill_id}/versions/{version}/activate")
def activate_skill_route(
    skill_id: str,
    version: int,
    request: Request,
    body: ActivateSkillRequest | None = None,
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    """Operator capability-backed skill activation route."""
    proof = getattr(request.state, "consumed_capability_proof", None)
    if proof is None or not isinstance(proof, ConsumedCapabilityProof):
        raise HTTPException(
            status_code=403,
            detail="skill activation requires exact server-consumed capability proof",
        )
    auth = SkillActivationAuthorization(
        proof=proof,
        skill_id=skill_id,
        version=version,
    )
    try:
        skill = service.activate_skill(auth)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SkillActivationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "skill_id": skill.skill_id,
        "version": skill.version,
        "state": skill.state,
        "status": "activated",
        "source": "capability_backed_human_activation",
    }


@router.post("/api/v1/skills/reuse")
def attempt_skill_reuse(
    body: SkillReuseRequest,
    request: Request,
    service: LearningService = Depends(get_learning_service),
) -> dict[str, Any]:
    """Create a governed draft mission or return a frontier escalation."""
    guard = getattr(request.state, "action_guard", None)
    operator_id = getattr(getattr(guard, "envelope", None), "operator_id", None)
    if not operator_id:
        raise HTTPException(status_code=401, detail="authenticated operator required")
    try:
        directive = service.attempt_local_reuse(
            skill_id=body.skill_id,
            version=body.version,
            mission_id=body.mission_id,
            operator_id=operator_id,
            goal=body.goal,
            project_id=body.project_id,
            current_inputs=body.current_inputs,
            current_state=body.current_state,
            current_scope=body.current_scope,
            mission_allowed_tools=body.mission_allowed_tools,
            validated_version=body.validated_version,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        **directive.model_dump(mode="json"),
        "status": "mission_created"
        if directive.directive_type == "local_execute"
        else "escalate",
        "source": "durable_skill_repository",
        "execution": "mission_service_draft_only",
    }
