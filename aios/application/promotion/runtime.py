"""Production adapters used by :class:`PromotionAuthority`.

The authority owns the decision; this adapter owns only the mechanical
checkpoint, staged diff application, exact-copy smoke check, and recovery
operations needed after that decision.
"""

from __future__ import annotations

from pathlib import Path

from aios.application.workspaces.staged import StagedWorkspaceManager, tree_digest
from aios.domain.missions.mission_contract import MissionContract
from aios.domain.promotion import PromotionRequest
from aios.runtime.snapshots import SnapshotManager


class WorkspacePromotionRuntime:
    """Bind PromotionAuthority to Council-owned workspace adapters."""

    def __init__(
        self,
        workspace_manager: StagedWorkspaceManager,
        runtime_root: str | Path,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.runtime_root = Path(runtime_root).resolve()
        self.snapshots = SnapshotManager(self.runtime_root)

    def create_checkpoint(self, request: PromotionRequest) -> str:
        contract = MissionContract(
            mission_id=request.mission_id,
            operator_id="promotion_authority",
            goal="Promotion recovery checkpoint",
            worker_type="promotion",
            created_by="promotion_authority",
            workspace_root=request.project_root,
            allowed_files=list(request.required_targets),
            snapshot_id=None,
        )
        return self.snapshots.create_snapshot(contract)

    def apply_staged_diff(self, request: PromotionRequest) -> None:
        self.workspace_manager.apply(request.lease)

    def post_promotion_smoke(self, request: PromotionRequest) -> bool:
        """Prove the enrolled tree now equals the verified staged tree."""
        return tree_digest(Path(request.project_root)) == tree_digest(
            Path(request.lease.workspace_path)
        )

    def restore_checkpoint(self, checkpoint_id: str, request: PromotionRequest) -> bool:
        result = self.snapshots.rollback_snapshot(
            request.project_root,
            checkpoint_id,
        )
        return result.restored


__all__ = ["WorkspacePromotionRuntime"]
