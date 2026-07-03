"""Restore-capable Council Runtime snapshots."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios.agents.rollback_engine import RollbackEngine, RollbackError, RollbackResult
from aios.runtime.contracts import MissionContract


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SnapshotManager:
    """Create restore-capable snapshots for Council worker missions.

    The metadata file remains useful as an evidence trail, but the identifier
    returned to the contract is the real rollback SHA created by
    :class:`RollbackEngine`.
    """

    def __init__(self, runtime_root: str | Path) -> None:
        from aios.runtime import _safe_resolve
        self.runtime_root = _safe_resolve(runtime_root)
        self.snapshot_dir = self.runtime_root / "snapshots"

    def create_snapshot(self, contract: MissionContract) -> str:
        workspace_root = Path(contract.workspace_root).resolve()
        engine = self._engine_for(workspace_root)
        snapshot = engine.create_snapshot(
            f"council pre-action snapshot: {contract.mission_id}"
        )
        snapshot_id = snapshot.sha
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "rollback_id": snapshot.sha,
            "mission_id": contract.mission_id,
            "workspace_root": contract.workspace_root,
            "created_at": _utc_now(),
            "mode": "rollback_engine_v1",
            "message": snapshot.message,
        }
        (self.snapshot_dir / f"{snapshot.sha[:12]}.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        return snapshot_id

    def rollback_snapshot(
        self, workspace_root: str | Path, snapshot_id: str
    ) -> RollbackResult:
        """Restore a Council-owned workspace to a recorded rollback snapshot."""
        engine = self._engine_for(Path(workspace_root).resolve())
        return engine.rollback(snapshot_id)

    def _engine_for(self, workspace_root: Path) -> RollbackEngine:
        """Build the rollback engine for a Council workspace.

        Council must not silently adopt an existing git repository. It owns a
        separate git database under the runtime root and leaves only a managed
        ``.git`` pointer in the workspace. If some other repo is already there,
        fail closed before the worker can act.
        """
        key = hashlib.sha256(str(workspace_root).encode("utf-8")).hexdigest()[:16]
        git_dir = (self.runtime_root / "rollback_git" / key).resolve()
        pointer = workspace_root / ".git"
        if pointer.is_dir():
            raise RollbackError(
                "Council rollback refused: workspace already contains a .git "
                "directory not owned by the Council runtime"
            )
        if pointer.is_file():
            text = pointer.read_text(encoding="utf-8", errors="ignore").strip()
            prefix = "gitdir:"
            if not text.lower().startswith(prefix):
                raise RollbackError(
                    "Council rollback refused: workspace .git pointer is malformed"
                )
            target = Path(text[len(prefix):].strip())
            if not target.is_absolute():
                target = (workspace_root / target).resolve()
            if target.resolve() != git_dir:
                raise RollbackError(
                    "Council rollback refused: workspace .git pointer is not "
                    "owned by this Council runtime"
                )
        return RollbackEngine(
            repo_dir=workspace_root,
            git_dir=git_dir,
            lock_path=self.runtime_root / "rollback_git" / f"{key}.lock",
        )


__all__ = ["SnapshotManager"]
