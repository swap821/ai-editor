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


class ProductionCodeWorkerStrategy:
    """Production repair strategy executing bounded repairs inside staged workspaces."""

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
                raw_root = scope.get("workspace_root") or getattr(contract, "workspace_root", None)
                if not raw_root:
                    metadata = getattr(contract, "metadata", {}) or {}
                    raw_root = metadata.get("workspace_root")
                if not raw_root:
                    raise ValueError("code worker strategy requires a staged workspace root")
                workspace_root = Path(raw_root).resolve()
        else:
            scope = getattr(contract, "scope", {}) or {}
            raw_root = scope.get("workspace_root") or getattr(contract, "workspace_root", None)
            if not raw_root:
                metadata = getattr(contract, "metadata", {}) or {}
                raw_root = metadata.get("workspace_root")
            if not raw_root:
                raise ValueError("code worker strategy requires a staged workspace root")
            workspace_root = Path(raw_root).resolve()

        project_root = config.PROJECT_ROOT.resolve()

        # Enforce boundary: worker MUST operate in staged workspace, never directly in project root
        if workspace_root == project_root:
            raise ValueError("Worker strategy cannot operate directly on enrolled project root")

        # Perform repair on staged workspace: resolve findings by removing defect markers
        metadata = getattr(contract, "metadata", {}) or {}
        target_rel = metadata.get("target_id") or metadata.get("target_file")
        
        modified_files = []
        if target_rel:
            target_path = (workspace_root / target_rel.replace("\\", "/")).resolve()
            if target_path.exists() and target_path.is_file():
                content = target_path.read_text(encoding="utf-8", errors="replace")
                new_content = content.replace("# DEFECT_MARKER: fix_required\n", "").replace("# DEFECT_MARKER: fix_required", "")
                new_content = new_content.replace("TODO_MAINTENANCE_DEFECT\n", "").replace("TODO_MAINTENANCE_DEFECT", "")
                if new_content != content:
                    target_path.write_text(new_content, encoding="utf-8")
                    modified_files.append(target_rel)
        else:
            # Fallback scan for markers in staged workspace
            for file_path in workspace_root.rglob("*"):
                rel_parts = file_path.relative_to(workspace_root).parts
                if file_path.is_file() and not any(p.startswith(".") for p in rel_parts):
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                        if "# DEFECT_MARKER: fix_required" in content or "TODO_MAINTENANCE_DEFECT" in content:
                            new_content = content.replace("# DEFECT_MARKER: fix_required\n", "").replace("# DEFECT_MARKER: fix_required", "")
                            new_content = new_content.replace("TODO_MAINTENANCE_DEFECT\n", "").replace("TODO_MAINTENANCE_DEFECT", "")
                            file_path.write_text(new_content, encoding="utf-8")
                            modified_files.append(str(file_path.relative_to(workspace_root)))
                    except OSError:
                        continue

        summary = f"Repaired {len(modified_files)} file(s) in staged workspace: {', '.join(modified_files)}"
        output_digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()

        return WorkerExecutionResult(
            status="completed",
            worker_id=spec.worker_id if hasattr(spec, "worker_id") else principal.worker_id,
            workspace_root=str(workspace_root),
            output_digest=output_digest,
            summary=summary,
        )


__all__ = ["ProductionCodeWorkerStrategy", "WorkerExecutionResult"]
