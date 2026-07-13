"""Immutable identity for a staged mission workspace."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class StagedWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lease_id: str
    mission_id: str
    project_root: str
    workspace_path: str
    baseline_digest: str
    created_at: str = Field(default_factory=lambda: _utc_now())
    retention_until: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = ["StagedWorkspace"]
