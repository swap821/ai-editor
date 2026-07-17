"""API routes for managing the Local Workforce."""

from __future__ import annotations

from typing import Any, Sequence

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field

from aios.api.deps import (
    get_action_broker,
    get_authenticated_principal,
)
# We will need to register this dependency later
from aios.domain.local_workforce.registry import LocalWorkforceRegistry
from aios.domain.local_workforce.contracts import LocalWorkerModel, LocalJobProfile
from aios.domain.actions.envelope import ActionEnvelope, ActionType, Principal
from aios.application.action_broker import ActionBroker, PolicyBrokerError
from aios.api.action_guard import enforce_action_boundary

router = APIRouter(tags=["local-workforce"], dependencies=[Depends(enforce_action_boundary)])


# Request models
class ApprovalRequest(BaseModel):
    approved: bool = Field(..., description="Whether the local worker model is approved by the human.")


class ProfilesRequest(BaseModel):
    profiles: list[str] = Field(..., description="List of local job profiles allowed for this model.")


def get_local_workforce_registry() -> LocalWorkforceRegistry:
    # Need to move this to `aios.api.deps`
    # Default instantiated for now. Real instantiation will be handled properly when we update deps.py
    return LocalWorkforceRegistry()


@router.get("/api/v1/local-workforce", response_model=list[LocalWorkerModel])
def list_models(
    registry: LocalWorkforceRegistry = Depends(get_local_workforce_registry)
) -> Sequence[LocalWorkerModel]:
    """Retrieve all local models in the registry."""
    return registry.list_models()


@router.get("/api/v1/local-workforce/{model_id}", response_model=LocalWorkerModel)
def get_model(
    model_id: str,
    registry: LocalWorkforceRegistry = Depends(get_local_workforce_registry)
) -> LocalWorkerModel:
    """Retrieve a specific local model by ID."""
    model = registry.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found in registry.")
    return model


@router.post("/api/v1/local-workforce/refresh")
def refresh_models(
    registry: LocalWorkforceRegistry = Depends(get_local_workforce_registry),
    broker: ActionBroker = Depends(get_action_broker),
    principal: Principal = Depends(get_authenticated_principal),
) -> dict[str, Any]:
    """Refresh the list of local models available from the provider (e.g. Ollama)."""
    envelope = ActionEnvelope(
        action_type=ActionType.LOCAL_WORKFORCE_REFRESH,
        payload={},
        principal=principal,
    )
    
    try:
        broker.dispatch(envelope)
    except PolicyBrokerError as e:
        raise HTTPException(status_code=403, detail=str(e))
        
    registry.refresh()
    return {"status": "refreshed", "count": len(registry.list_models())}


@router.post("/api/v1/local-workforce/{model_id}/approve")
def approve_model(
    model_id: str,
    req: ApprovalRequest = Body(...),
    registry: LocalWorkforceRegistry = Depends(get_local_workforce_registry),
    broker: ActionBroker = Depends(get_action_broker),
    principal: Principal = Depends(get_authenticated_principal),
) -> dict[str, Any]:
    """Set the human approval status for a local model."""
    envelope = ActionEnvelope(
        action_type=ActionType.LOCAL_WORKFORCE_APPROVE,
        payload={"model_id": model_id, "approved": req.approved},
        principal=principal,
    )
    
    try:
        broker.dispatch(envelope)
    except PolicyBrokerError as e:
        raise HTTPException(status_code=403, detail=str(e))
        
    registry.set_approval(model_id, req.approved)
    return {"status": "success", "model_id": model_id, "approved": req.approved}


@router.post("/api/v1/local-workforce/{model_id}/profiles")
def set_model_profiles(
    model_id: str,
    req: ProfilesRequest = Body(...),
    registry: LocalWorkforceRegistry = Depends(get_local_workforce_registry),
    broker: ActionBroker = Depends(get_action_broker),
    principal: Principal = Depends(get_authenticated_principal),
) -> dict[str, Any]:
    """Set the allowed local job profiles for a local model."""
    envelope = ActionEnvelope(
        action_type=ActionType.LOCAL_WORKFORCE_PROFILES,
        payload={"model_id": model_id, "profiles": req.profiles},
        principal=principal,
    )
    
    try:
        broker.dispatch(envelope)
    except PolicyBrokerError as e:
        raise HTTPException(status_code=403, detail=str(e))
        
    registry.set_profiles(model_id, req.profiles)
    return {"status": "success", "model_id": model_id, "profiles": req.profiles}
