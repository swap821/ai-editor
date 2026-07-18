"""API routes for managing Intelligence Hiring."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import (
    get_anthropic_client,
    get_bedrock_client,
    get_gemini_client,
    get_hiring_repository,
    get_ollama_client,
    get_openai_client,
)
from aios.domain.intelligence.repository import HiringRecordRepository

router = APIRouter(
    tags=["intelligence-hiring"], dependencies=[Depends(enforce_action_boundary)]
)


class HiringStatusResponse(BaseModel):
    status: str
    source: str
    providers: list[dict[str, Any]]


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
