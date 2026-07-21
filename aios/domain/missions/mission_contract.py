from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aios.domain.verification import SkillVerifierSpec, VerifierSpec
from aios.domain.missions.mission_state import MissionState

RiskLevel = str  # "GREEN" | "YELLOW" | "RED"


class MissionBudget(BaseModel):
    """Bounded resource budget for a mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_workers: int = 1
    max_steps: int = 12
    timeout_seconds: int = 600
    max_tokens: int | None = None
    max_cost_usd: float | None = None


class VerificationPlan(BaseModel):
    """What must be verified before promotion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_strength: str = "none"  # none | weak | moderate | strong
    commands: list[str] = Field(default_factory=list)
    verifiers: tuple[VerifierSpec | SkillVerifierSpec, ...] = ()
    expected_output_fragments: list[str] = Field(default_factory=list)
    forbidden_output_fragments: list[str] = Field(default_factory=list)


class MissionContract(BaseModel):
    """Versioned, immutable mission contract (v1) — the authority for one mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = "v1"
    mission_id: str
    parent_mission_id: str | None = None
    turn_id: str | None = None
    project_id: str | None = None
    operator_id: str
    goal: str
    worker_type: str
    created_by: str
    risk_level: RiskLevel = "YELLOW"
    requires_approval: bool = True
    policy_version: str = "v1"
    capability_digest: str | None = None
    budget: MissionBudget = Field(default_factory=MissionBudget)
    scope: dict[str, Any] = Field(default_factory=dict)
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    verification_plan: VerificationPlan = Field(default_factory=VerificationPlan)
    workspace_root: str | None = None
    snapshot_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: _utc_now())

    def digest(self) -> str:
        """Stable digest of the authoritative contract fields."""
        canonical = self.model_dump(
            include={
                "version",
                "mission_id",
                "parent_mission_id",
                "turn_id",
                "project_id",
                "operator_id",
                "goal",
                "worker_type",
                "created_by",
                "risk_level",
                "requires_approval",
                "policy_version",
                "capability_digest",
                "budget",
                "scope",
                "allowed_files",
                "forbidden_files",
                "allowed_tools",
                "forbidden_tools",
                "verification_plan",
                "workspace_root",
                "snapshot_id",
            },
            mode="json",
            by_alias=True,
        )
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def with_state(self, state: MissionState) -> "MissionContract":
        """Return a copy with the target state recorded in metadata (not authority)."""
        metadata = dict(self.metadata)
        metadata["target_state"] = state.value
        return self.model_copy(update={"metadata": metadata})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = ["MissionBudget", "MissionContract", "VerificationPlan"]
