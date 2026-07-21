"""Frozen v0.1 schemas for the Council Runtime.

These contracts are the shared language between council orchestration, workers,
verification, ledgers, and the human-facing report. Phase 0 defines schemas only;
runtime behavior belongs in later phases.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RiskLevel = Literal["GREEN", "YELLOW", "RED"]
WorkerStatus = Literal[
    "completed",
    "failed",
    "timeout",
    "blocked",
    "contract_violation",
    "approval_denied",
    "awaiting_approval",
    "killed",
]


class RuntimeContract(BaseModel):
    """Base settings for v0.1 contract models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class MissionContract(RuntimeContract):
    version: str = "v0.1"
    mission_id: str
    parent_mission_id: str | None = None
    goal: str
    worker_type: str
    created_by: str
    priority: int = 0
    risk_level: RiskLevel = "YELLOW"
    requires_approval: bool = True
    workspace_root: str
    snapshot_id: str | None = None
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    timeout_seconds: int = 600
    max_steps: int = 12
    verification_commands: list[str] = Field(default_factory=list)
    pheromone_context: list[str] = Field(default_factory=list)
    required_output: list[str] = Field(
        default_factory=lambda: [
            "summary",
            "files_touched",
            "diff",
            "verification_result",
            "risk_after",
            "rollback_id",
        ]
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerResult(RuntimeContract):
    mission_id: str
    worker_id: str
    status: WorkerStatus
    summary: str = ""
    files_touched: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    risk_after: RiskLevel
    rollback_id: str | None = None
    next_recommendation: str = ""
    council_verdicts_applied: list[dict[str, Any]] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    started_at: str
    ended_at: str


class QueenEvidence(RuntimeContract):
    """Structured evidence produced by a Queen during deliberation."""

    basis: str = ""
    checks: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class QueenVerdict(RuntimeContract):
    queen: str
    verdict: Literal["allow", "allow_with_approval", "deny", "defer"]
    risk: RiskLevel
    reason: str
    constraints: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    confidence_basis: str = ""
    evidence: QueenEvidence | None = None
    recommended_worker_strategy: str | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunLedger(RuntimeContract):
    mission_id: str
    mission: str
    risk_before: RiskLevel
    risk_after: RiskLevel
    contract: MissionContract
    workers_created: list[str] = Field(default_factory=list)
    files_allowed: list[str] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    blocked_attempts: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    council_verdicts: list[QueenVerdict] = Field(default_factory=list)
    snapshot_id: str | None = None
    rollback_id: str | None = None
    status: str
    created_at: str
    completed_at: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class KingReport(RuntimeContract):
    mission_id: str
    mission: str
    status: Literal[
        "awaiting_approval",
        "completed",
        "failed",
        "rolled_back",
        "needs_revision",
    ]
    council_summary: dict[str, Any] = Field(default_factory=dict)
    recommendation: Literal[
        "approve",
        "reject",
        "revise",
        "rollback",
        "observe",
    ]
    risk: RiskLevel
    files: list[str] = Field(default_factory=list)
    verification_result: dict[str, Any] = Field(default_factory=dict)
    approval_needed: bool
    rollback_available: bool
    rollback_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    human_summary: str


__all__ = [
    "KingReport",
    "MissionContract",
    "QueenEvidence",
    "QueenVerdict",
    "RiskLevel",
    "RunLedger",
    "WorkerResult",
    "WorkerStatus",
]
