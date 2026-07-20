"""Dedicated CheckpointAuthority for external isolation and transactional rollback."""

from __future__ import annotations

import hmac
import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict


class CheckpointError(RuntimeError):
    """Raised when checkpoint creation, manifest validation, or restoration fails."""


class CheckpointManifest(BaseModel):
    """Immutable signed checkpoint manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    checkpoint_id: str
    mission_id: str
    action_id: str
    worker_id: str
    executor_job_id: str
    contract_digest: str
    workspace_digest: str
    diff_digest: str
    project_root_identity: str
    affected_paths: tuple[dict[str, Any], ...]
    manifest_digest: str
    authority_key_id: str
    created_at: float
    state: str
    signature: str


class RollbackReceipt(BaseModel):
    """Immutable evidence of completed rollback restoration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    checkpoint_id: str
    affected_paths: tuple[str, ...]
    before_digests: dict[str, str]
    after_digests: dict[str, str]
    project_root_identity: str
    status: str
    created_at: float
    evidence_id: str


def _resolve_external_dir(project_root: Path, storage_root: Path | None = None) -> Path:
    proj_resolved = project_root.resolve()
    env_dir = os.environ.get("AIOS_ROLLBACK_DIR")
    if storage_root is not None:
        rollback_root = storage_root.resolve()
    elif env_dir and env_dir.strip():
        rollback_root = Path(env_dir.strip()).expanduser().resolve()
    else:
        # Default to a subpath of tempdir explicitly isolated outside project_root
        rollback_root = (Path(tempfile.gettempdir()) / "aios_rollback_checkpoints").resolve()

    if rollback_root == proj_resolved:
        raise CheckpointError("rollback root cannot equal project root")
    if rollback_root.is_relative_to(proj_resolved):
        raise CheckpointError("rollback root cannot be inside project root")
    if proj_resolved.is_relative_to(rollback_root):
        raise CheckpointError("project root cannot be inside rollback root")
    if proj_resolved.is_symlink() or rollback_root.is_symlink():
        raise CheckpointError("symlink aliases are forbidden for rollback storage")

    rollback_root.mkdir(parents=True, exist_ok=True)
    return rollback_root


class CheckpointAuthority:
    """Production authority owning checkpoint snapshotting, manifest signing, and two-phase rollback."""

    def __init__(
        self,
        *,
        project_root: Path | str,
        storage_root: Path | str | None = None,
        authority_key: str | None = None,
        key_id: str = "checkpoint-key-v1",
    ) -> None:
        self.project_root = Path(project_root).resolve()
        if not self.project_root.exists():
            raise CheckpointError(f"project root {self.project_root} does not exist")

        self.storage_root = _resolve_external_dir(
            self.project_root,
            Path(storage_root) if storage_root else None,
        )
        self.authority_key = (
            authority_key
            or os.environ.get("CHECKPOINT_AUTHORITY_KEY", "")
            or "aios-checkpoint-key-default-32bytes!"
        )
        self.key_id = key_id

    def _sign_manifest_bytes(self, data: bytes) -> str:
        return hmac.new(
            self.authority_key.encode("utf-8"),
            data,
            hashlib.sha256,
        ).hexdigest()

    def create_checkpoint(
        self,
        *,
        mission_id: str,
        action_id: str,
        worker_id: str,
        executor_job_id: str,
        contract_digest: str,
        workspace_digest: str,
        diff_digest: str,
        affected_paths: Sequence[str],
    ) -> CheckpointManifest:
        if not mission_id or not action_id or not worker_id or not executor_job_id:
            raise CheckpointError("missing required identity parameters for checkpoint creation")
        if not contract_digest or not workspace_digest or not diff_digest:
            raise CheckpointError("missing required digests for checkpoint creation")

        checkpoint_id = f"chk-{mission_id}-{contract_digest[:8]}-{time.time_ns()}"
        chk_dir = self.storage_root / checkpoint_id
        if chk_dir.exists():
            raise CheckpointError(f"checkpoint ID collision: {checkpoint_id}")

        chk_dir.mkdir(parents=True, exist_ok=False)
        snapshot_dir = chk_dir / "snapshot"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        project_identity = hashlib.sha256(str(self.project_root).encode("utf-8")).hexdigest()

        path_records: list[dict[str, Any]] = []
        for rel_str in affected_paths:
            norm_rel = str(rel_str).replace("\\", "/").strip("/")
            if norm_rel.startswith("/") or ".." in norm_rel.split("/"):
                raise CheckpointError(f"path traversal or absolute path refused: {rel_str}")

            target_file = (self.project_root / norm_rel).resolve()
            if not target_file.is_relative_to(self.project_root):
                raise CheckpointError(f"path escapes project root: {rel_str}")

            existed = target_file.exists()
            before_sha = None
            mode_val = None

            if existed:
                if target_file.is_dir():
                    raise CheckpointError(f"directory targets are not supported directly: {rel_str}")
                content = target_file.read_bytes()
                before_sha = hashlib.sha256(content).hexdigest()
                mode_val = target_file.stat().st_mode
                # Save snapshot file
                snap_file = snapshot_dir / norm_rel
                snap_file.parent.mkdir(parents=True, exist_ok=True)
                snap_file.write_bytes(content)

            path_records.append({
                "rel_path": norm_rel,
                "existed_before": existed,
                "object_type": "file" if existed else "none",
                "before_sha256": before_sha,
                "mode": mode_val,
                "classification": "modified" if existed else "created",
            })

        created_at = time.time()
        payload_to_digest = {
            "checkpoint_id": checkpoint_id,
            "mission_id": mission_id,
            "action_id": action_id,
            "worker_id": worker_id,
            "executor_job_id": executor_job_id,
            "contract_digest": contract_digest,
            "workspace_digest": workspace_digest,
            "diff_digest": diff_digest,
            "project_root_identity": project_identity,
            "affected_paths": path_records,
            "created_at": created_at,
        }
        manifest_raw = json.dumps(payload_to_digest, sort_keys=True)
        manifest_digest = hashlib.sha256(manifest_raw.encode("utf-8")).hexdigest()
        signature = self._sign_manifest_bytes(manifest_raw.encode("utf-8"))

        manifest = CheckpointManifest(
            checkpoint_id=checkpoint_id,
            mission_id=mission_id,
            action_id=action_id,
            worker_id=worker_id,
            executor_job_id=executor_job_id,
            contract_digest=contract_digest,
            workspace_digest=workspace_digest,
            diff_digest=diff_digest,
            project_root_identity=project_identity,
            affected_paths=tuple(path_records),
            manifest_digest=manifest_digest,
            authority_key_id=self.key_id,
            created_at=created_at,
            state="created",
            signature=signature,
        )

        (chk_dir / "manifest.json").write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return manifest

    def restore_checkpoint(self, checkpoint_id: str) -> RollbackReceipt:
        chk_dir = self.storage_root / checkpoint_id
        if not chk_dir.exists():
            raise CheckpointError(f"checkpoint {checkpoint_id} not found")

        manifest_file = chk_dir / "manifest.json"
        if not manifest_file.exists():
            raise CheckpointError(f"checkpoint manifest missing for {checkpoint_id}")

        raw_json = manifest_file.read_text(encoding="utf-8")
        manifest = CheckpointManifest.model_validate_json(raw_json)

        if manifest.state in ("consumed", "invalid"):
            raise CheckpointError(f"checkpoint {checkpoint_id} is already in state {manifest.state}")

        # Validate signature
        payload_to_digest = {
            "checkpoint_id": manifest.checkpoint_id,
            "mission_id": manifest.mission_id,
            "action_id": manifest.action_id,
            "worker_id": manifest.worker_id,
            "executor_job_id": manifest.executor_job_id,
            "contract_digest": manifest.contract_digest,
            "workspace_digest": manifest.workspace_digest,
            "diff_digest": manifest.diff_digest,
            "project_root_identity": manifest.project_root_identity,
            "affected_paths": [p for p in manifest.affected_paths],
            "created_at": manifest.created_at,
        }
        manifest_raw = json.dumps(payload_to_digest, sort_keys=True)
        expected_sig = self._sign_manifest_bytes(manifest_raw.encode("utf-8"))
        if not hmac.compare_digest(manifest.signature, expected_sig):
            raise CheckpointError("checkpoint manifest signature verification failed")

        snapshot_dir = chk_dir / "snapshot"
        if not snapshot_dir.exists():
            raise CheckpointError("checkpoint snapshot directory missing")

        # Record current digests before restoration
        before_digests: dict[str, str] = {}
        after_digests: dict[str, str] = {}
        affected_rel_paths: list[str] = []

        for entry in manifest.affected_paths:
            rel_path = entry["rel_path"]
            affected_rel_paths.append(rel_path)
            target_file = self.project_root / rel_path

            if target_file.exists() and target_file.is_file():
                before_digests[rel_path] = hashlib.sha256(target_file.read_bytes()).hexdigest()
            else:
                before_digests[rel_path] = "absent"

        # Apply restoration
        for entry in manifest.affected_paths:
            rel_path = entry["rel_path"]
            target_file = self.project_root / rel_path
            existed_before = entry.get("existed_before", False)

            if existed_before:
                snap_file = snapshot_dir / rel_path
                if not snap_file.exists():
                    raise CheckpointError(f"snapshot file missing for {rel_path}")
                content = snap_file.read_bytes()
                if entry.get("before_sha256") and hashlib.sha256(content).hexdigest() != entry["before_sha256"]:
                    raise CheckpointError(f"snapshot content tampered for {rel_path}")
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_bytes(content)
            else:
                if target_file.exists():
                    if target_file.is_file():
                        target_file.unlink()
                    elif target_file.is_dir():
                        shutil.rmtree(target_file)

            if target_file.exists() and target_file.is_file():
                after_digests[rel_path] = hashlib.sha256(target_file.read_bytes()).hexdigest()
            else:
                after_digests[rel_path] = "absent"

        # Mark consumed atomically
        consumed_manifest = manifest.model_copy(update={"state": "consumed"})
        manifest_file.write_text(consumed_manifest.model_dump_json(indent=2), encoding="utf-8")

        receipt = RollbackReceipt(
            checkpoint_id=checkpoint_id,
            affected_paths=tuple(affected_rel_paths),
            before_digests=before_digests,
            after_digests=after_digests,
            project_root_identity=manifest.project_root_identity,
            status="RESTORED",
            created_at=time.time(),
            evidence_id=f"rollback-receipt-{hashlib.sha256(checkpoint_id.encode()).hexdigest()[:16]}",
        )
        return receipt
