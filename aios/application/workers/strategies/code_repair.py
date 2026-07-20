"""Production code worker repair strategy operating exclusively in staged workspaces."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from aios import config
from aios.domain.workers.worker_contract import WorkerStrategyName


class WorkerExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    worker_id: str
    workspace_root: str
    output_digest: str
    summary: str
    proposal: dict[str, Any] | None = None


class ProductionCodeWorkerStrategy:
    """Production repair strategy creating bounded repair proposals for private Executor execution."""

    name = WorkerStrategyName.CODE

    def __init__(self, workspace_manager: Any | None = None) -> None:
        self.workspace_manager = workspace_manager

    async def run(self, request: Any) -> WorkerExecutionResult:
        contract = request.contract
        spec = request.spec
        principal = request.principal

        # Extract workspace root
        if self.workspace_manager is not None and hasattr(contract, "mission_id"):
            lease = self.workspace_manager.for_mission(contract.mission_id)
            if lease is not None:
                workspace_root = Path(lease.workspace_path).resolve()
            else:
                scope = getattr(contract, "scope", {}) or {}
                raw_root = scope.get("workspace_root") or getattr(
                    contract, "workspace_root", None
                )
                if not raw_root:
                    metadata = getattr(contract, "metadata", {}) or {}
                    raw_root = metadata.get("workspace_root")
                if not raw_root:
                    raise ValueError(
                        "code worker strategy requires a staged workspace root"
                    )
                workspace_root = Path(raw_root).resolve()
        else:
            scope = getattr(contract, "scope", {}) or {}
            raw_root = scope.get("workspace_root") or getattr(
                contract, "workspace_root", None
            )
            if not raw_root:
                metadata = getattr(contract, "metadata", {}) or {}
                raw_root = metadata.get("workspace_root")
            if not raw_root:
                raise ValueError(
                    "code worker strategy requires a staged workspace root"
                )
            workspace_root = Path(raw_root).resolve()

        project_root = config.PROJECT_ROOT.resolve()

        # Enforce boundary: worker MUST operate in staged workspace, never directly in project root
        if workspace_root == project_root:
            raise ValueError(
                "Worker strategy cannot operate directly on enrolled project root"
            )

        metadata = getattr(contract, "metadata", {}) or {}
        target_rel = metadata.get("target_id") or metadata.get("target_file")

        expected_digest = ""
        if target_rel:
            target_path = (workspace_root / target_rel.replace("\\", "/")).resolve()
            if target_path.exists() and target_path.is_file():
                content = target_path.read_bytes()
                expected_digest = hashlib.sha256(content).hexdigest()

        proposal = {
            "operation_id": "REMOVE_MAINTENANCE_MARKER_V1",
            "target_rel": target_rel,
            "expected_digest": expected_digest,
            "allowed_markers": [
                "# DEFECT_MARKER: fix_required\n",
                "# DEFECT_MARKER: fix_required",
                "TODO_MAINTENANCE_DEFECT\n",
                "TODO_MAINTENANCE_DEFECT",
            ],
            "workspace_root": str(workspace_root),
        }

        summary = (
            f"Proposed repair operation REMOVE_MAINTENANCE_MARKER_V1 for {target_rel}"
        )
        output_digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()

        worker_id_val = (
            spec.worker_id if hasattr(spec, "worker_id") else principal.worker_id
        )

        return WorkerExecutionResult(
            status="completed",
            worker_id=str(worker_id_val),
            workspace_root=str(workspace_root),
            output_digest=output_digest,
            summary=summary,
            proposal=proposal,
        )


__all__ = ["ProductionCodeWorkerStrategy", "WorkerExecutionResult"]
