"""Domain models for the Frontier Intelligence Hiring Broker."""
from typing import Sequence, Literal

from pydantic import BaseModel, ConfigDict


class HiringRequest(BaseModel):
    """A formal request to hire an intelligence provider for a mission."""
    model_config = ConfigDict(frozen=True)

    problem_id: str
    mission_id: str
    purpose: str
    task_class: str
    required_capabilities: Sequence[str]
    data_classification: Literal["public", "internal", "confidential", "secret", "local_only"]
    context_manifest: Sequence[str]
    privacy_budget: str
    cost_budget: str
    latency_budget: int
    candidate_providers: Sequence[str]
    verification_requirements: Sequence[str]


class HiringDecision(BaseModel):
    """The deterministic outcome of a provider hiring request."""
    model_config = ConfigDict(frozen=True)

    eligible_providers: Sequence[str]
    selected_provider: str | None
    selected_model: str | None
    reason: str
    redactions: Sequence[str]
    external_data_scope: str
    cost_limit: str
    fallback_order: Sequence[str]
    human_approval_required: bool
