"""Immutable, provenance-bound evidence contracts."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceType(StrEnum):
    COMMAND = "command"
    TEST = "test"
    STATIC_CHECK = "static_check"
    DIFF = "diff"
    ENVIRONMENT = "environment"
    OBSERVATION = "observation"


class VerificationPlanV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intended_behavior: str
    targets: tuple[str, ...] = ()
    required_tests: tuple[str, ...] = ()
    static_checks: tuple[str, ...] = ()
    security_checks: tuple[str, ...] = ()
    expected_side_effects: tuple[str, ...] = ()
    forbidden_side_effects: tuple[str, ...] = ()
    minimum_strength: int = 3
    freshness_seconds: int = 300


class VerificationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    passed_count: int = 0
    failed_count: int = 0
    tool_version: str = "unknown"
    observed_at: str = Field(default_factory=lambda: _utc_now())


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    mission_id: str
    action_id: str
    worker_id: str
    evidence_type: EvidenceType
    source: str
    content_reference: str
    content_digest: str
    redaction_status: str
    produced_at: str = Field(default_factory=lambda: _utc_now())
    environment_digest: str
    tool_version: str
    trust_level: str
    verification_strength: int = 0
    supersedes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verification_id: str
    mission_id: str
    action_id: str
    target: str
    passed: bool
    strength: int
    required_strength: int
    evidence_ids: tuple[str, ...]
    workspace_digest: str
    diff_digest: str
    environment_digest: str
    command: str
    output_digest: str
    tool_version: str
    observed_at: str = Field(default_factory=lambda: _utc_now())

    @property
    def meets_requirement(self) -> bool:
        return self.passed and self.strength >= self.required_strength


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "EvidenceRecord",
    "EvidenceType",
    "VerificationObservation",
    "VerificationPlanV1",
    "VerificationResult",
]
