"""Collision-safe staged workspaces for bounded mission execution."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aios.domain.workspaces import StagedWorkspace


class WorkspacePathViolation(ValueError):
    """Raised for an unenrolled, escaping, or symlinked project path."""


class WorkspaceCollision(RuntimeError):
    """Raised when a mission already owns a staged workspace."""


class BaselineChanged(RuntimeError):
    """Raised when the real project no longer matches the mission baseline."""


class StagedWorkspaceManager:
    """Own staged copies and promotion preconditions for enrolled projects."""

    def __init__(
        self,
        root: str | Path,
        *,
        enrolled_roots: tuple[str | Path, ...] = (),
        retention_seconds: int = 86_400,
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._mission_markers = self.root / ".mission-leases"
        self._mission_markers.mkdir(parents=True, exist_ok=True)
        self.enrolled_roots = tuple(Path(path).resolve() for path in enrolled_roots)
        self.retention_seconds = max(1, retention_seconds)
        self._mission_leases: dict[str, StagedWorkspace] = {}

    def stage(self, mission_id: str, project_root: str | Path) -> StagedWorkspace:
        if not mission_id or any(
            char
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for char in mission_id
        ):
            raise WorkspacePathViolation("mission id contains unsafe path characters")
        source = self._enrolled_root(project_root)
        if mission_id in self._mission_leases:
            raise WorkspaceCollision(f"mission already owns a workspace: {mission_id}")
        existing = self._find_metadata(mission_id)
        if existing is not None:
            raise WorkspaceCollision(f"mission already owns a workspace: {mission_id}")
        marker = self._mission_markers / mission_id
        try:
            marker.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise WorkspaceCollision(
                f"mission already owns a workspace: {mission_id}"
            ) from exc
        lease_id = uuid.uuid4().hex
        destination = self.root / lease_id
        try:
            self._reject_symlinks(source)
            baseline = tree_digest(source)
            destination.mkdir(parents=True, exist_ok=False)
            self._copy_tree(source, destination)
            lease = StagedWorkspace(
                lease_id=lease_id,
                mission_id=mission_id,
                project_root=str(source),
                workspace_path=str(destination),
                baseline_digest=baseline,
            )
            self._write_metadata(lease)
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            try:
                marker.rmdir()
            except OSError:
                pass
            raise
        self._mission_leases[mission_id] = lease
        return lease

    def load(self, lease_id: str) -> StagedWorkspace:
        metadata = self.root / lease_id / ".gagos-workspace.json"
        if not metadata.is_file():
            raise FileNotFoundError(f"staged workspace not found: {lease_id}")
        lease = StagedWorkspace.model_validate_json(
            metadata.read_text(encoding="utf-8")
        )
        if (
            self._enrolled_root(lease.project_root)
            != Path(lease.project_root).resolve()
        ):
            raise WorkspacePathViolation("workspace project root is not enrolled")
        workspace_path = Path(lease.workspace_path).resolve()
        if (
            workspace_path != (self.root / lease_id).resolve()
            or not workspace_path.is_dir()
        ):
            raise WorkspacePathViolation("workspace metadata path escapes manager root")
        return lease

    def for_mission(self, mission_id: str) -> StagedWorkspace | None:
        """Return the durable lease for a mission, including after restart."""
        lease = self._mission_leases.get(mission_id) or self._find_metadata(mission_id)
        if lease is None:
            return None
        return self.load(lease.lease_id)

    def cleanup_for_mission(self, mission_id: str, *, retain: bool = False) -> None:
        """Release a mission lease after its terminal lifecycle transition."""
        lease = self.for_mission(mission_id)
        if lease is not None:
            self.cleanup(lease, retain=retain)

    def verify_baseline(self, lease: StagedWorkspace) -> None:
        current = tree_digest(Path(lease.project_root).resolve())
        if current != lease.baseline_digest:
            raise BaselineChanged(
                f"project baseline changed for mission {lease.mission_id}; promotion refused"
            )

    def diff(self, lease: StagedWorkspace) -> dict[str, object]:
        """Return a deterministic, content-digested staged diff."""
        baseline = _file_map(Path(lease.project_root).resolve())
        staged = _file_map(Path(lease.workspace_path).resolve())
        added = sorted(set(staged) - set(baseline))
        deleted = sorted(set(baseline) - set(staged))
        modified = sorted(
            path
            for path in set(staged) & set(baseline)
            if staged[path] != baseline[path]
        )
        payload = {
            "lease_id": lease.lease_id,
            "mission_id": lease.mission_id,
            "baseline_digest": lease.baseline_digest,
            "workspace_digest": tree_digest(Path(lease.workspace_path).resolve()),
            "added": added,
            "modified": modified,
            "deleted": deleted,
        }
        payload["diff_digest"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return payload

    def apply(self, lease: StagedWorkspace) -> None:
        """Apply a lease to its enrolled project after rechecking its baseline.

        This is intentionally a low-level adapter.  Callers must invoke it
        through :class:`PromotionAuthority`, which creates the recovery
        checkpoint and verifies evidence before reaching this method.
        """
        self.verify_baseline(lease)
        source_root = Path(lease.workspace_path).resolve()
        target_root = self._enrolled_root(lease.project_root)
        self._reject_symlinks(source_root)
        source_files = _file_map(source_root)
        target_files = _file_map(target_root)

        for relative in sorted(set(target_files) - set(source_files)):
            target = self._safe_child(target_root, relative)
            if target.is_file() or target.is_symlink():
                target.unlink()
        for relative in sorted(source_files):
            source = self._safe_child(source_root, relative)
            target = self._safe_child(target_root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    @staticmethod
    def _safe_child(root: Path, relative: str) -> Path:
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError as exc:
            raise WorkspacePathViolation("workspace file escapes its root") from exc
        if candidate.is_symlink():
            raise WorkspacePathViolation("workspace mutation target is a symlink")
        return candidate

    def cleanup(self, lease: StagedWorkspace, *, retain: bool = False) -> None:
        path = (self.root / lease.lease_id).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise WorkspacePathViolation(
                "workspace cleanup path escapes manager root"
            ) from exc
        if retain:
            return
        shutil.rmtree(path, ignore_errors=False)
        self._mission_leases.pop(lease.mission_id, None)
        marker = self._mission_markers / lease.mission_id
        try:
            marker.rmdir()
        except FileNotFoundError:
            pass

    def _enrolled_root(self, project_root: str | Path) -> Path:
        resolved = Path(project_root).resolve()
        if not self.enrolled_roots:
            raise WorkspacePathViolation("no enrolled project roots configured")
        if not any(_is_within(resolved, enrolled) for enrolled in self.enrolled_roots):
            raise WorkspacePathViolation("project root is not enrolled")
        if not resolved.is_dir():
            raise WorkspacePathViolation("project root is not a directory")
        return resolved

    def _find_metadata(self, mission_id: str) -> StagedWorkspace | None:
        for metadata in self.root.glob("*/.gagos-workspace.json"):
            try:
                lease = StagedWorkspace.model_validate_json(
                    metadata.read_text(encoding="utf-8")
                )
            except Exception:  # noqa: BLE001 - corrupted derived state is ignored
                continue
            if lease.mission_id == mission_id:
                return lease
        return None

    def _write_metadata(self, lease: StagedWorkspace) -> None:
        path = Path(lease.workspace_path) / ".gagos-workspace.json"
        path.write_text(lease.model_dump_json(indent=2), encoding="utf-8")

    def _copy_tree(self, source: Path, destination: Path) -> None:
        for current, directories, files in os.walk(source, followlinks=False):
            current_path = Path(current)
            relative = current_path.relative_to(source)
            target = destination / relative
            target.mkdir(parents=True, exist_ok=True)
            directories[:] = sorted(name for name in directories if name != ".git")
            for name in sorted(files):
                source_file = current_path / name
                if source_file.is_symlink():
                    raise WorkspacePathViolation("symlink found during staged copy")
                target_file = target / name
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_file)

    def _reject_symlinks(self, root: Path) -> None:
        for current, directories, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            if current_path.is_symlink():
                raise WorkspacePathViolation(
                    "symlinked project directory is not allowed"
                )
            if any((current_path / name).is_symlink() for name in directories + files):
                raise WorkspacePathViolation(
                    "symlinks are not allowed in enrolled projects"
                )


def tree_digest(root: Path) -> str:
    """Hash relative file names and bytes in stable order, excluding VCS state."""
    files = _file_map(root)
    hasher = hashlib.sha256()
    for name in sorted(files):
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(files[name].encode("ascii"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def _file_map(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not root.is_dir():
        raise WorkspacePathViolation(f"workspace is not a directory: {root}")
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if name != ".git")
        current_path = Path(current)
        for name in sorted(files):
            if name in {".gagos-workspace.json", ".git"}:
                continue
            source = current_path / name
            if source.is_symlink():
                raise WorkspacePathViolation(
                    "symlink encountered while hashing workspace"
                )
            relative = source.relative_to(root).as_posix()
            result[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


__all__ = [
    "BaselineChanged",
    "StagedWorkspace",
    "StagedWorkspaceManager",
    "WorkspaceCollision",
    "WorkspacePathViolation",
    "tree_digest",
]
