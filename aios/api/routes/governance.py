"""Human Sovereign emergency-control routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aios.api.action_guard import CAPABILITY_HEADER, enforce_action_boundary
from aios.api.deps import get_emergency_stop, require_privileged_operator
from aios.application.governance import EmergencyStopController, EmergencyStopError
from aios.domain.governance import EmergencyStopRequest
from aios.domain.identity.models import Principal


router = APIRouter(dependencies=[Depends(enforce_action_boundary)])


class EmergencyStopEngageRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


def _state_payload(controller: EmergencyStopController) -> dict[str, Any]:
    state = controller.state()
    return {
        "engaged": state.engaged,
        "generation": state.generation,
        "operatorId": state.operator_id,
        "authenticationEventId": state.authentication_event_id,
        "reason": state.reason,
        "actions": state.actions,
        "failure": state.failure,
        "engagedAt": state.engaged_at,
        "clearedAt": state.cleared_at,
    }


@router.get("/api/v1/governance/emergency-stop")
def emergency_stop_state(
    controller: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    return _state_payload(controller)


@router.post("/api/v1/governance/emergency-stop/engage")
def engage_emergency_stop(
    req: EmergencyStopEngageRequest,
    principal: Principal = Depends(require_privileged_operator),
    controller: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    try:
        state = controller.engage(
            EmergencyStopRequest(
                operator_id=principal.principal_id,
                authentication_event_id=principal.authentication_event_id,
                reason=req.reason,
            )
        )
    except EmergencyStopError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _state_payload(controller) | {"engaged": state.engaged}


@router.post("/api/v1/governance/emergency-stop/clear")
def clear_emergency_stop(
    request: Request,
    principal: Principal = Depends(require_privileged_operator),
    controller: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    token = request.headers.get(CAPABILITY_HEADER, "")
    try:
        state = controller.clear(
            operator_id=principal.principal_id,
            authentication_event_id=principal.authentication_event_id,
            session_id=principal.session_id,
            clear_capability=token,
        )
    except EmergencyStopError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _state_payload(controller) | {"engaged": state.engaged}


__all__ = ["router"]
