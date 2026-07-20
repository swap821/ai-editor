"""Canonical Pydantic model for isolated private Executor repair receipts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExecutorRepairReceipt(BaseModel):
    """Strictly validated private Executor repair receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    mission_contract_digest: str
    operation_id: str
    target: str
    changed: bool
    before_target_digest: str
    after_target_digest: str
    workspace_digest_before: str
    workspace_digest_after: str
    isolation_backend: str
    environment_digest: str
    started_timestamp: str
    ended_timestamp: str
    executor_service_identity_version: str
    exit_code: int
    receipt_version: str = "1.0"


__all__ = ["ExecutorRepairReceipt"]
