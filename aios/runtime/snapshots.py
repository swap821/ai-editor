"""Minimal snapshot identifiers for Council Runtime Phase 1A."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios.runtime.contracts import MissionContract


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SnapshotManager:
    """Create lightweight snapshot records.

    Phase 1A only needs immutable snapshot identifiers in the contract and
    evidence trail. Full file restoration belongs to the later healing phase.
    """

    def __init__(self, runtime_root: str | Path) -> None:
        self.runtime_root = Path(runtime_root).resolve()
        self.snapshot_dir = self.runtime_root / "snapshots"

    def create_snapshot(self, contract: MissionContract) -> str:
        snapshot_id = f"snapshot-{uuid.uuid4().hex[:12]}"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "mission_id": contract.mission_id,
            "workspace_root": contract.workspace_root,
            "created_at": _utc_now(),
            "mode": "metadata_only_v0.1",
        }
        (self.snapshot_dir / f"{snapshot_id}.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        return snapshot_id


__all__ = ["SnapshotManager"]
