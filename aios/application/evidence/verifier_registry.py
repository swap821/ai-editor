"""Fixed, bounded handlers for structured deterministic verification."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.service import (
    AutonomousMaintenanceForce,
    ScanExecutionError,
)
from aios.domain.verification import VerifierSpec


class VerifierRegistryError(RuntimeError):
    """Raised when a verifier invocation is unknown or outside its bounds."""


class VerifierRun(BaseModel):
    """Structured result from one fixed verifier handler."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verifier_id: str
    version: str
    run_id: str
    started_at: str
    ended_at: str
    status: Literal["completed", "incomplete", "failed"]
    passed: bool
    argv: tuple[str, ...]
    arguments: dict[str, str]
    finding_fingerprints: tuple[str, ...] = ()
    stdout: str = ""
    stderr: str = ""
    reason: str = ""


ScannerAdapter = Callable[..., Sequence[MaintenanceFinding]]


class VerifierRegistry:
    """Dispatch only versioned handlers with injected scanner adapters.

    The registry is deliberately not an execution authority. It validates the
    immutable invocation and runs the existing bounded scanner adapter; mission
    execution, verification authority, promotion, and reconciliation remain
    owned by their existing canonical services.
    """

    _HANDLERS = frozenset({"maintenance.rescan"})

    def __init__(self, *, scanner_adapters: Mapping[str, ScannerAdapter]) -> None:
        self._scanner_adapters = dict(scanner_adapters)
        self._bounded = AutonomousMaintenanceForce(MaintenanceLifecycleEngine())

    @property
    def scanner_adapters(self) -> dict[str, ScannerAdapter]:
        return dict(self._scanner_adapters)

    def run(
        self,
        spec: VerifierSpec,
        *,
        contract: BoundedScanContract,
        scanner: ScannerAdapter,
    ) -> VerifierRun:
        started_at = _utc_now()
        if spec.verifier_id not in self._HANDLERS:
            raise VerifierRegistryError("unknown verifier")
        if spec.version != "1":
            raise VerifierRegistryError("unsupported verifier version")
        admitted = self._scanner_adapters.get(spec.scanner_id)
        if admitted is None:
            raise VerifierRegistryError("scanner is not admitted")
        if admitted is not scanner:
            raise VerifierRegistryError("scanner adapter mismatch")
        self._validate_bounds(spec, contract)

        argv = (
            spec.verifier_id,
            spec.scanner_id,
            spec.scanner_version,
            spec.target_id,
            spec.rescan_of,
        )
        arguments = {
            "scanner_id": spec.scanner_id,
            "scanner_version": spec.scanner_version,
            "target_id": spec.target_id,
            "rescan_of": spec.rescan_of,
            "allowed_root": spec.allowed_root,
        }
        try:
            findings = tuple(self._bounded.run_bounded_scan(contract, scanner))
        except ScanExecutionError as exc:
            message = str(exc)
            status: Literal["incomplete", "failed"] = (
                "incomplete"
                if any(
                    marker in message.lower()
                    for marker in ("max_", "deadline", "symlink", "escape")
                )
                else "failed"
            )
            return VerifierRun(
                verifier_id=spec.verifier_id,
                version=spec.version,
                run_id=f"verifier-run-{uuid.uuid4().hex}",
                started_at=started_at,
                ended_at=_utc_now(),
                status=status,
                passed=False,
                argv=argv,
                arguments=arguments,
                stderr=message,
                reason=message,
            )

        fingerprints = tuple(finding.fingerprint for finding in findings)
        return VerifierRun(
            verifier_id=spec.verifier_id,
            version=spec.version,
            run_id=f"verifier-run-{uuid.uuid4().hex}",
            started_at=started_at,
            ended_at=_utc_now(),
            status="completed",
            passed=not findings,
            argv=argv,
            arguments=arguments,
            finding_fingerprints=fingerprints,
            stdout=json.dumps(
                {"finding_fingerprints": list(fingerprints)},
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    @staticmethod
    def _validate_bounds(spec: VerifierSpec, contract: BoundedScanContract) -> None:
        if contract.network_allowed:
            raise VerifierRegistryError("network access is forbidden")
        if contract.git_history_allowed:
            raise VerifierRegistryError("git history access is forbidden")
        if Path(spec.allowed_root).is_symlink():
            raise VerifierRegistryError("symlink root is forbidden")
        if Path(contract.allowed_root).is_symlink():
            raise VerifierRegistryError("symlink root is forbidden")
        try:
            root = Path(spec.allowed_root).resolve(strict=True)
            contract_root = Path(contract.allowed_root).resolve(strict=True)
        except OSError as exc:
            raise VerifierRegistryError("verifier root is unavailable") from exc
        if root != contract_root:
            raise VerifierRegistryError("verifier root does not match contract")
        if root.is_symlink():
            raise VerifierRegistryError("symlink root is forbidden")
        # Treat Windows separators as path separators on every host. A verifier
        # contract may be authored on one OS and admitted on another; accepting
        # ``..\\outside`` as a literal POSIX filename would bypass containment.
        target = (root / spec.target_id.replace("\\", "/")).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise VerifierRegistryError("verifier target escapes root") from exc
        if target.is_symlink():
            raise VerifierRegistryError("symlink target is forbidden")
        if (
            min(
                contract.max_files,
                contract.max_total_bytes,
                contract.max_file_bytes,
                contract.max_findings,
                contract.deadline,
            )
            <= 0
        ):
            raise VerifierRegistryError("verifier bounds must be positive")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "VerifierRegistry",
    "VerifierRegistryError",
    "VerifierRun",
    "VerifierSpec",
]
