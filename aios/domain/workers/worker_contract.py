"""Typed, non-authoritative worker identity and lifecycle contracts.

Workers are derived from a mission.  They never inherit the operator's
identity or credentials and these contracts deliberately contain no authority
or approval fields.  Authority remains on the mission/action/capability path.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkerStrategyName(StrEnum):
    DETERMINISTIC = "deterministic"
    TOOL_LOOP = "tool_loop"
    ROLE_PASS = "role_pass"
    SWARM = "swarm"
    RESEARCH = "research"
    CODE = "code"
    TEST = "test"
    INSPECTION = "inspection"


class WorkerState(StrEnum):
    REQUESTED = "requested"
    ADMITTED = "admitted"
    BORN = "born"
    RUNNING = "running"
    AWAITING_CAPABILITY = "awaiting_capability"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    DISSOLVED = "dissolved"


class WorkerLifecycle(BaseModel):
    """An immutable observation of a worker's current lifecycle state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    worker_id: str
    mission_id: str
    state: WorkerState
    strategy: WorkerStrategyName
    changed_at: str = Field(default_factory=lambda: _utc_now())
    reason: str = ""


class WorkerPrincipal(BaseModel):
    """A worker principal derived from one exact mission contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_id: str
    worker_id: str
    mission_id: str
    contract_digest: str
    parent_principal_id: str | None = None
    authentication_level: str = "derived"
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerSpec(BaseModel):
    """Bounded admission request consumed by the Worker Foundry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    worker_id: str
    mission_id: str
    contract_digest: str
    strategy: WorkerStrategyName
    caste: str | None = None
    priority: int = 0
    max_steps: int = 1
    timeout_seconds: int = 1
    allowed_tools: tuple[str, ...] = ()
    scope: dict[str, Any] = Field(default_factory=dict)
    budgets: dict[str, Any] = Field(default_factory=dict)
    data_classification: str = "internal"
    executor_policy: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)


def contract_digest(contract: Any) -> str:
    """Return the contract's canonical digest without trusting model text."""

    digest_method = getattr(contract, "digest", None)
    if callable(digest_method):
        value = digest_method()
        if isinstance(value, str) and value:
            return value
    if hasattr(contract, "model_dump"):
        payload = contract.model_dump(mode="json")
    elif hasattr(contract, "__dict__"):
        payload = contract.__dict__
    else:
        payload = repr(contract)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "WorkerLifecycle",
    "WorkerPrincipal",
    "WorkerSpec",
    "WorkerState",
    "WorkerStrategyName",
    "contract_digest",
]
