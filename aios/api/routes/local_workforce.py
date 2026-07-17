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
        
    registry.update_profiles(model_id, {LocalJobProfile(p) for p in req.profiles})
    return {"status": "profiles_updated", "model_id": model_id, "profiles": req.profiles}


@router.post("/api/v1/local-workforce/{model_id}/health-check")
def health_check_model(
    model_id: str,
    registry: LocalWorkforceRegistry = Depends(get_local_workforce_registry),
    broker: ActionBroker = Depends(get_action_broker),
    principal: Principal = Depends(get_authenticated_principal),
) -> dict[str, Any]:
    """Check the health of a local model."""
    envelope = ActionEnvelope(
        action_type=ActionType.LOCAL_WORKFORCE_HEALTH_CHECK,
        payload={"model_id": model_id},
        principal=principal,
    )
    
    try:
        broker.dispatch(envelope)
    except PolicyBrokerError as e:
        raise HTTPException(status_code=403, detail=str(e))
        
    model = registry.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    from aios.core.llm import OllamaClient, LLMError
    client = OllamaClient(model=model_id)
    
    try:
        # A basic health check is a quick prompt
        client.complete("Respond with exactly one word: healthy", temperature=0.0)
        registry.record_health(model_id, "healthy", True)
        return {"status": "healthy"}
    except LLMError as e:
        registry.record_health(model_id, "failing", False)
        return {"status": "failing", "detail": str(e)}


@router.post("/api/v1/local-workforce/{model_id}/qualify")
def qualify_model(
    model_id: str,
    registry: LocalWorkforceRegistry = Depends(get_local_workforce_registry),
    broker: ActionBroker = Depends(get_action_broker),
    principal: Principal = Depends(get_authenticated_principal),
) -> dict[str, Any]:
    """Run the qualification suite and resource admission for a local model."""
    envelope = ActionEnvelope(
        action_type=ActionType.LOCAL_WORKFORCE_QUALIFY,
        payload={"model_id": model_id},
        principal=principal,
    )
    
    try:
        broker.dispatch(envelope)
    except PolicyBrokerError as e:
        raise HTTPException(status_code=403, detail=str(e))
        
    model = registry.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    if not model.operator_approved:
        raise HTTPException(status_code=400, detail="Model must be operator_approved before qualification")

    # 1. Health check
    if model.health != "healthy":
        # Force a health check
        from aios.core.llm import OllamaClient, LLMError
        client = OllamaClient(model=model_id)
        try:
            client.complete("ping", temperature=0.0)
            registry.record_health(model_id, "healthy", True)
        except LLMError:
            registry.record_health(model_id, "failing", False)
            registry.update_admission(model_id, "rejected", "Health check failed")
            return {"status": "rejected", "reason": "Health check failed"}

    # 2. Resource Admission
    from aios.domain.local_workforce.admission import HardwareAdmission, AdmissionContext
    hw_admission = HardwareAdmission()
    ctx = AdmissionContext(
        requested_context_size=model.max_context,
        requested_output_size=model.max_output,
    )
    admission_result = hw_admission.evaluate(ctx)
    if not admission_result.admitted:
        registry.update_admission(model_id, "rejected", admission_result.reason)
        return {"status": "rejected", "reason": admission_result.reason}

    # 3. Qualification Suite
    from aios.domain.local_workforce.qualifier import QualificationSuite
    from aios.core.llm import OllamaClient
    client = OllamaClient(model=model_id)
    suite = QualificationSuite(client)
    qual_result = suite.run()
    
    if qual_result.passed:
        registry.update_admission(model_id, "approved", "Passed all qualification checks")
        return {"status": "admitted", "qualification": qual_result.model_dump()}
    else:
        reason = "Failed qualification suite"
        registry.update_admission(model_id, "rejected", reason)
        return {"status": "rejected", "reason": reason, "qualification": qual_result.model_dump()}
