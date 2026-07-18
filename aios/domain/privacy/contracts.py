"""Immutable contracts for governed local/cloud intelligence."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataClassification(StrEnum):
    PUBLIC = "PUBLIC"
    PROJECT_INTERNAL = "PROJECT_INTERNAL"
    SENSITIVE = "SENSITIVE"
    SECRET = "SECRET"
    NEVER_EXTERNAL = "NEVER_EXTERNAL"


class FallbackPolicy(StrEnum):
    DENY = "deny"
    LOCAL_ONLY = "local_only"


class PrivacyPolicy(BaseModel):
    """Operator-owned egress policy attached to one model request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_classification: DataClassification = DataClassification.PROJECT_INTERNAL
    local_only: bool = True
    allowed_providers: tuple[str, ...] = ("ollama",)
    allowed_models: tuple[str, ...] = ()
    fallback_policy: FallbackPolicy = FallbackPolicy.LOCAL_ONLY


class ModelCallRequest(BaseModel):
    """A model request without provider authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    principal_id: str
    mission_id: str | None = None
    turn_id: str | None = None
    purpose: str
    prompt: str
    data_classification: DataClassification
    policy: PrivacyPolicy = Field(default_factory=PrivacyPolicy)
    task: str = "general"
    max_tokens: int = 1500
    metadata: dict[str, Any] = Field(default_factory=dict)


class PrivacyDecision(BaseModel):
    """Deterministic privacy result; model output cannot create one."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    data_classification: DataClassification
    scrubbed_prompt: str
    redactions: tuple[str, ...] = ()
    allowed_providers: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()
    local_only: bool
    evaluated_at: str = Field(default_factory=lambda: _utc_now())


class ModelCallRecord(BaseModel):
    """Redacted, bounded evidence about one provider call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    principal_id: str
    mission_id: str | None = None
    turn_id: str | None = None
    purpose: str
    data_classification: DataClassification
    redactions: tuple[str, ...] = ()
    allowed_providers: tuple[str, ...]
    selected_provider: str | None = None
    selected_model: str | None = None
    local_cloud_decision: str
    fallback: str | None = None
    estimated_tokens: int = 0
    actual_tokens: int = 0
    cost: float | None = None
    latency_ms: int | None = None
    output_digest: str | None = None
    status: str
    recorded_at: str = Field(default_factory=lambda: _utc_now())


def digest_output(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "DataClassification",
    "FallbackPolicy",
    "ModelCallRecord",
    "ModelCallRequest",
    "PrivacyDecision",
    "PrivacyPolicy",
    "digest_output",
]
