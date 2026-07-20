"""Domain models for the Durable Maintenance Finding Lifecycle."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from aios.domain.evidence import VerificationResult
from aios.domain.promotion import PromotionResult


FindingState = Literal[
    "OPEN",
    "ACKNOWLEDGED",
    "TRIAGED",
    "PROPOSAL_READY",
    "MISSION_CREATED",
    "REPAIRING",
    "VERIFYING",
    "VERIFICATION_FAILED",
    "VERIFIED_RESOLVED",
    "FALSE_POSITIVE",
    "HUMAN_SUPPRESSED",
    "REOPENED",
]


class MaintenanceFinding(BaseModel):
    """A durable record of a maintenance issue discovered by a scanner."""

    model_config = ConfigDict(frozen=True)

    finding_id: str
    fingerprint: str
    scanner_id: str
    scanner_version: str
    kind: str
    severity: str
    confidence: float
    evidence_quality: str

    target_id: str
    target_digest: str
    source_digest: str

    first_seen: str
    last_seen: str
    occurrence_count: int
    status: FindingState

    deterministic_evidence: str
    local_clerk_enrichment: Optional[str] = None
    frontier_analysis: Optional[str] = None

    mission_id: Optional[str] = None
    verification_ids: list[str] = []
    resolution_evidence: Optional[str] = None
    human_disposition: Optional[str] = None


class MaintenanceResolutionEvidence(BaseModel):
    """Complete authority-bound evidence required to resolve a finding.

    The contract is deliberately richer than a list of verification IDs. The
    application service resolves every referenced mission, verification, scan,
    and promotion through authoritative stores before accepting it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str
    mission_contract_digest: str
    action_id: str
    promotion: PromotionResult
    verification_results: tuple[VerificationResult, ...]
    workspace_digest: str
    diff_digest: str
    rescan_id: str
    scanner_id: str
    scanner_version: str
    target_id: str
    source_digest: str


__all__ = [
    "FindingState",
    "MaintenanceFinding",
    "MaintenanceResolutionEvidence",
]
