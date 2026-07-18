"""Mounted API routes for the governed Local Workforce."""

from __future__ import annotations

from typing import Any, Sequence

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import (
    get_local_workforce_registry,
    get_local_workforce_service,
)
from aios.application.local_workforce.service import (
    InvalidLocalJobProfile,
    LocalModelNotApproved,
    LocalModelNotFound,
    LocalWorkforceService,
)
from aios.domain.local_workforce.contracts import LocalWorkerModel
from aios.domain.local_workforce.registry import LocalWorkforceRegistry


router = APIRouter(
    tags=["local-workforce"],
    dependencies=[Depends(enforce_action_boundary)],
)


class ApprovalRequest(BaseModel):
    approved: bool = Field(
        ..., description="Whether the local worker model is approved by the human."
    )


class ProfilesRequest(BaseModel):
    profiles: list[str] = Field(
        ..., description="List of local job profiles allowed for this model."
    )


@router.get("/api/v1/local-workforce", response_model=list[LocalWorkerModel])
def list_models(
    registry: LocalWorkforceRegistry = Depends(get_local_workforce_registry),
) -> Sequence[LocalWorkerModel]:
    """Retrieve all durable local models, including retained history."""
    return registry.list_models()


@router.get("/api/v1/local-workforce/{model_id}", response_model=LocalWorkerModel)
def get_model(
    model_id: str,
    registry: LocalWorkforceRegistry = Depends(get_local_workforce_registry),
) -> LocalWorkerModel:
    """Retrieve one durable local model by identifier."""
    model = registry.get_model(model_id)
    if model is None:
        raise HTTPException(
            status_code=404, detail=f"Model {model_id} not found in registry."
        )
    return model


@router.post("/api/v1/local-workforce/refresh")
def refresh_models(
    service: LocalWorkforceService = Depends(get_local_workforce_service),
) -> dict[str, Any]:
    """Reconcile the durable registry with the real local provider."""
    models = service.refresh()
    return {"status": "refreshed", "count": len(models)}


@router.post("/api/v1/local-workforce/{model_id}/approve")
def approve_model(
    model_id: str,
    req: ApprovalRequest = Body(...),
    service: LocalWorkforceService = Depends(get_local_workforce_service),
) -> dict[str, Any]:
    """Persist the Human Sovereign's approval decision."""
    try:
        model = service.approve(model_id, req.approved)
    except LocalModelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "status": "success",
        "model_id": model.model_id,
        "approved": model.operator_approved,
    }


@router.post("/api/v1/local-workforce/{model_id}/profiles")
def set_model_profiles(
    model_id: str,
    req: ProfilesRequest = Body(...),
    service: LocalWorkforceService = Depends(get_local_workforce_service),
) -> dict[str, Any]:
    """Persist only known clerical profiles for a registered model."""
    try:
        model = service.update_profiles(model_id, req.profiles)
    except LocalModelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidLocalJobProfile as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "status": "profiles_updated",
        "model_id": model.model_id,
        "profiles": sorted(profile.value for profile in model.allowed_job_profiles),
    }


@router.post("/api/v1/local-workforce/{model_id}/health-check")
def health_check_model(
    model_id: str,
    service: LocalWorkforceService = Depends(get_local_workforce_service),
) -> dict[str, Any]:
    """Record a truthful model/provider health result."""
    try:
        return service.health_check(model_id)
    except LocalModelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/v1/local-workforce/{model_id}/qualify")
def qualify_model(
    model_id: str,
    service: LocalWorkforceService = Depends(get_local_workforce_service),
) -> dict[str, Any]:
    """Run health, hardware, and structured qualification in the application layer."""
    try:
        return service.qualify(model_id)
    except LocalModelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LocalModelNotApproved as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
