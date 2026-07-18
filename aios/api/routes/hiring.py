"""API routes for managing Intelligence Hiring."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aios.api.action_guard import enforce_action_boundary
from aios.domain.intelligence.broker import HiringBroker

router = APIRouter(tags=["intelligence-hiring"], dependencies=[Depends(enforce_action_boundary)])

# We simulate a global broker instance for the API.
_broker = HiringBroker()

class HiringStatusResponse(BaseModel):
    status: str
    providers: list[str]
    capabilities: dict[str, list[str]]


@router.get("/api/v1/hiring/status", response_model=HiringStatusResponse)
def get_hiring_status() -> dict[str, Any]:
    """Retrieve the overall intelligence hiring broker status."""
    return {
        "status": "online",
        "providers": list(_broker._provider_capabilities.keys()),
        "capabilities": _broker._provider_capabilities,
    }


@router.get("/api/v1/hiring/proposals")
def list_hiring_proposals() -> dict[str, Any]:
    """Retrieve the list of current intelligence hiring proposals (simulated for UI)."""
    # Simulated proposals for the UI
    return {
        "proposals": [
            {
                "id": "hire-reasoning",
                "status": "active",
                "request": {
                    "data_classification": "public",
                    "required_capabilities": ["reasoning"],
                    "cost_budget": "free"
                },
                "decision": {
                    "selected_provider": "ollama",
                    "selected_model": "auto",
                    "reason": "Selected provider meets all constraints within budget."
                }
            },
            {
                "id": "hire-frontier",
                "status": "pending_approval",
                "request": {
                    "data_classification": "confidential",
                    "required_capabilities": ["frontier", "reasoning"],
                    "cost_budget": "high"
                },
                "decision": {
                    "selected_provider": "bedrock",
                    "selected_model": "auto",
                    "reason": "Selected provider meets all constraints within budget.",
                    "human_approval_required": True
                }
            }
        ]
    }
