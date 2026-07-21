"""Immutable promotion contracts.

Promotion is deliberately a separate domain boundary from execution and
verification.  A worker can produce a staged diff and evidence, but it cannot
turn either into an authoritative project mutation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from aios.domain.evidence import EvidenceBundle, VerificationResult
from aios.domain.missions.mission_state import MissionState
from aios.domain.workspaces import StagedWorkspace


class PromotionStatus(StrEnum):
    PROMOTED = "promoted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


from aios.domain.capabilities.proof import ConsumedCapabilityProof


class PromotionAuthorization(BaseModel):
    """Server-issued authorization contract for promotion capability verification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proof: ConsumedCapabilityProof
    promotion_attempt_id: str
    mission_id: str
    action_id: str
    worker_id: str
    executor_job_id: str
    contract_digest: str
    workspace_digest: str
    diff_digest: str
    project_root_identity: str
    required_targets: tuple[str, ...]


class PromotionRequest(BaseModel):
    """All values required to prove that a staged diff is still promotable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str
    action_id: str
    worker_id: str
    executor_job_id: str
    environment_digest: str
    project_root: str
    lease: StagedWorkspace
    current_state: MissionState
    contract_digest: str
    authoritative_contract_digest: str
    policy_version: str
    authoritative_policy_version: str
    workspace_digest: str
    diff_digest: str
    verification_results: tuple[VerificationResult, ...]
    evidence_bundle: EvidenceBundle | None = None
    required_targets: tuple[str, ...] = ()
    required_strength: Annotated[int, Field(ge=0)] = 0
    freshness_seconds: Annotated[int, Field(ge=0)] = 300
    requires_capability: bool = False
    authorization: PromotionAuthorization | None = None


class PromotionResult(BaseModel):
    """Auditable result of one promotion attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str
    action_id: str
    status: PromotionStatus
    reason_codes: tuple[str, ...] = ()
    checkpoint_id: str | None = None
    diff_digest: str | None = None
    restored: bool = False
    evidence_ids: tuple[str, ...] = ()


__all__ = [
    "PromotionAuthorization",
    "PromotionRequest",
    "PromotionResult",
    "PromotionStatus",
]
