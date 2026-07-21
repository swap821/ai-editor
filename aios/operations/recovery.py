"""Explicit, integrity-checked recovery operations for the local control plane."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from aios import config
from aios.application.read_models.projection import IncrementalSystemProjection
from aios.runtime.cortex_bus import CortexBus
from aios.security.audit_logger import verify_chain


class RecoveryError(RuntimeError):
    """Raised when recovery cannot prove the operation is safe."""


@dataclass(frozen=True, slots=True)
class BackupManifest:
    schema_version: str
    created_at: str
    source: str
    files: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "source": self.source,
            "files": dict(sorted(self.files.items())),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise RecoveryError(f"unsafe backup member path: {name!r}")
    return path


def _data_files(data_dir: Path, destination: Path | None = None) -> list[Path]:
    if not data_dir.exists():
        return []
    files: list[Path] = []
    destination_resolved = destination.resolve() if destination else None
    backup_root = (data_dir / "backups").resolve()
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        # Backups are artifacts, not live state.  Including them would make
        # every backup contain all previous backups and grow without bound.
        if backup_root in path.resolve().parents:
            continue
        if destination_resolved is not None and path.resolve() == destination_resolved:
            continue
        # Environment files are credentials, not application state.
        if path.name in {".env", ".env.local", ".env.production"}:
            continue
        files.append(path)
    return files


def create_backup(
    *,
    data_dir: Path = config.DATA_DIR,
    destination: Path,
) -> BackupManifest:
    """Create a gzipped state archive with a content-hash manifest."""
    data_dir = Path(data_dir).resolve()
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = _data_files(data_dir, destination)
    hashes = {path.relative_to(data_dir).as_posix(): _sha256(path) for path in files}
    manifest = BackupManifest(
        schema_version="1",
        created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        source=str(data_dir),
        files=hashes,
    )
    with tarfile.open(destination, mode="w:gz") as archive:
        for path in files:
            archive.add(
                path, arcname=path.relative_to(data_dir).as_posix(), recursive=False
            )
        payload = json.dumps(
            manifest.as_dict(), sort_keys=True, separators=(",", ":")
        ).encode()
        info = tarfile.TarInfo("manifest.json")
        info.size = len(payload)
        info.mtime = int(datetime.now(timezone.utc).timestamp())
        archive.addfile(info, io.BytesIO(payload))
    return manifest


def _read_manifest(archive: tarfile.TarFile) -> BackupManifest:
    try:
        member = archive.getmember("manifest.json")
    except KeyError as exc:
        raise RecoveryError("backup has no manifest") from exc
    handle = archive.extractfile(member)
    if handle is None:
        raise RecoveryError("backup manifest is unreadable")
    try:
        raw = json.loads(handle.read().decode("utf-8"))
        if raw.get("schema_version") != "1" or not isinstance(raw.get("files"), dict):
            raise ValueError("unsupported manifest")
        return BackupManifest(
            schema_version="1",
            created_at=str(raw["created_at"]),
            source=str(raw["source"]),
            files={str(key): str(value) for key, value in raw["files"].items()},
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RecoveryError("invalid backup manifest") from exc


def verify_backup(bundle: Path) -> BackupManifest:
    """Verify archive paths and every content hash without extracting it."""
    bundle = Path(bundle).resolve()
    try:
        with tarfile.open(bundle, mode="r:gz") as archive:
            manifest = _read_manifest(archive)
            members = {member.name: member for member in archive.getmembers()}
            declared = set(manifest.files)
            actual = set(members) - {"manifest.json"}
            if declared != actual:
                raise RecoveryError("backup manifest does not match archive members")
            for name, expected in manifest.files.items():
                _safe_member(name)
                member = members[name]
                if not member.isfile():
                    raise RecoveryError(
                        f"backup member is not a regular file: {name!r}"
                    )
                handle = archive.extractfile(member)
                if handle is None:
                    raise RecoveryError(f"backup member is unreadable: {name!r}")
                digest = hashlib.sha256(handle.read()).hexdigest()
                if digest != expected:
                    raise RecoveryError(f"backup hash mismatch: {name!r}")
            return manifest
    except (OSError, tarfile.TarError) as exc:
        raise RecoveryError(f"backup cannot be read: {exc}") from exc


def restore_backup(
    *,
    bundle: Path,
    data_dir: Path = config.DATA_DIR,
    safety_backup: Path | None = None,
    emergency_stop: Any | None = None,
) -> Path | None:
    """Stage and install verified state; retain the old directory when present."""
    if emergency_stop is not None:
        emergency_stop.assert_operational()
    manifest = verify_backup(Path(bundle))
    destination = Path(data_dir).resolve()
    if destination.exists() and any(destination.iterdir()) and safety_backup is None:
        raise RecoveryError("non-empty data directory requires a safety backup")
    if (
        safety_backup is not None
        and destination.exists()
        and any(destination.iterdir())
    ):
        create_backup(data_dir=destination, destination=Path(safety_backup))

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.restore-", dir=parent))
    try:
        with tarfile.open(Path(bundle).resolve(), mode="r:gz") as archive:
            for name in manifest.files:
                relative = _safe_member(name)
                member = archive.getmember(name)
                handle = archive.extractfile(member)
                if handle is None:
                    raise RecoveryError(f"backup member is unreadable: {name!r}")
                target = staging.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as output:
                    shutil.copyfileobj(handle, output)
                os.chmod(target, member.mode & 0o777)
        old_dir: Path | None = None
        if destination.exists():
            old_dir = (
                parent
                / f"{destination.name}.pre-restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            )
            destination.rename(old_dir)
        staging.rename(destination)
        return old_dir
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_audit(*, db_path: Path = config.AUDIT_DB_PATH) -> dict[str, Any]:
    status = verify_chain(db_path=db_path)
    return {
        "valid": bool(status.valid),
        "entries": int(status.total_entries),
        "message": status.reason or "audit verified",
    }


def rebuild_projections(*, bus: CortexBus | None = None) -> int:
    """Recreate the derived portrait DB from the durable observation bus."""
    owned_bus = bus is None
    resolved_bus = bus or CortexBus()
    projection_path = Path(resolved_bus.db_path).with_name("system_portrait.db")
    for path in (
        projection_path,
        projection_path.with_suffix(".db-wal"),
        projection_path.with_suffix(".db-shm"),
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    resolved_bus.reset_consumer(
        IncrementalSystemProjection.consumer_name, start_event_id=0
    )
    projection = IncrementalSystemProjection(projection_path)
    processed = projection.process_available(resolved_bus)
    if owned_bus:
        del resolved_bus
    return processed


__all__ = [
    "BackupManifest",
    "RecoveryError",
    "create_backup",
    "rebuild_projections",
    "restore_backup",
    "verify_audit",
    "verify_backup",
]
