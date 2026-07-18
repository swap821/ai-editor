"""API routes for managing Intelligence Hiring."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import (
    get_anthropic_client,
    get_bedrock_client,
    get_gemini_client,
    get_hiring_repository,
    get_hiring_service,
    get_ollama_client,
    get_openai_client,
)
from aios.application.models.hiring_service import IntelligenceHiringService
from aios.domain.privacy import (
    DataClassification,
    FallbackPolicy,
    ModelCallRequest,
    PrivacyPolicy,
)
from aios.domain.intelligence.repository import HiringRecordRepository

router = APIRouter(
    tags=["intelligence-hiring"], dependencies=[Depends(enforce_action_boundary)]
)


class HiringStatusResponse(BaseModel):
    status: str
    source: str
    providers: list[dict[str, Any]]


class HiringCallRequest(BaseModel):
    request_id: str
    mission_id: str
    turn_id: str | None = None
    purpose: str
    prompt: str
    data_classification: DataClassification
    task: str = "general"
    allowed_providers: tuple[str, ...]
    local_only: bool = True
    fallback_policy: FallbackPolicy = FallbackPolicy.DENY
    max_tokens: int = Field(default=1500, gt=0)


def _adapter_status(name: str, adapter: Any) -> dict[str, Any]:
    """Describe only what the injected runtime adapter can establish."""
    if adapter is None:
        return {
            "provider": name,
            "configured": False,
            "availability": "unavailable",
        }
    probe = getattr(adapter, "is_available", None)
    if not callable(probe):
        return {
            "provider": name,
            "configured": True,
            "availability": "unknown",
        }
    try:
        available = bool(probe())
    except Exception:  # noqa: BLE001 - status must surface unknown, not invent health
        return {
            "provider": name,
            "configured": True,
            "availability": "unknown",
        }
    return {
        "provider": name,
        "configured": True,
        "availability": "available" if available else "unavailable",
    }


@router.get("/api/v1/hiring/status", response_model=HiringStatusResponse)
def get_hiring_status(
    ollama: Any = Depends(get_ollama_client),
    bedrock: Any = Depends(get_bedrock_client),
    gemini: Any = Depends(get_gemini_client),
    openai: Any = Depends(get_openai_client),
    anthropic: Any = Depends(get_anthropic_client),
) -> dict[str, Any]:
    """Report provider adapter configuration without fabricating capabilities."""
    providers = [
        _adapter_status("ollama", ollama),
        _adapter_status("bedrock", bedrock),
        _adapter_status("gemini", gemini),
        _adapter_status("openai", openai),
        _adapter_status("anthropic", anthropic),
    ]
    availability = {row["availability"] for row in providers}
    if "available" in availability:
        status = "available"
    elif availability == {"unavailable"}:
        status = "unavailable"
    else:
        status = "unknown"
    return {"status": status, "source": "runtime_adapters", "providers": providers}


@router.get("/api/v1/hiring/proposals")
def list_hiring_proposals(
    repository: HiringRecordRepository = Depends(get_hiring_repository),
) -> dict[str, Any]:
    """List only persisted hiring decisions; an empty store stays empty."""
    items = [record.model_dump(mode="json") for record in repository.list_records()]
    return {
        "items": items,
        "status": "available" if items else "empty",
        "source": "durable_repository",
    }


@router.post("/api/v1/hiring/call")
def execute_hiring_call(
    body: HiringCallRequest,
    request: Request,
    service: IntelligenceHiringService = Depends(get_hiring_service),
) -> dict[str, Any]:
    """Execute one bounded advisory call after the ordinary action boundary."""
    guard = getattr(request.state, "action_guard", None)
    operator_id = getattr(getattr(guard, "envelope", None), "operator_id", None)
    if not operator_id:
        raise HTTPException(status_code=401, detail="authenticated operator required")
    model_request = ModelCallRequest(
        request_id=body.request_id,
        principal_id=operator_id,
        mission_id=body.mission_id,
        turn_id=body.turn_id,
        purpose=body.purpose,
        prompt=body.prompt,
        data_classification=body.data_classification,
        task=body.task,
        max_tokens=body.max_tokens,
        policy=PrivacyPolicy(
            data_classification=body.data_classification,
            local_only=body.local_only,
            allowed_providers=body.allowed_providers,
            fallback_policy=body.fallback_policy,
        ),
    )
    try:
        result, record = service.complete(model_request)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "content": result,
        "call": record.model_dump(mode="json"),
        "advisory": True,
        "source": "provider_adapter",
    }
