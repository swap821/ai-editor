"""Autonomous Maintenance Force service."""

import inspect
import os
import time
from pathlib import Path
from typing import Sequence, Callable, Any

from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine


class ScanExecutionError(RuntimeError):
    """Raised when a scan violates bounds or fails unexpectedly."""


class BoundedScanContext:
    """Read-only scanner input that enforces the scan contract during reads."""

    def __init__(self, contract: BoundedScanContract) -> None:
        self.contract = contract
        self.root = Path(contract.allowed_root).resolve()
        if not self.root.exists():
            raise ScanExecutionError("allowed_root does not exist")
        self._started = time.monotonic()
        self._seen_files: set[Path] = set()
        self._total_bytes = 0

    def iter_files(self) -> tuple[Path, ...]:
        """Enumerate files without yielding an item beyond max_files."""
        self._check_deadline()
        if self.root.is_file():
            candidates = (self.root,)
        else:
            candidates = tuple(
                Path(current) / name
                for current, directories, files in os.walk(self.root, followlinks=False)
                for name in sorted(files)
                if not any(
                    (Path(current) / directory).is_symlink()
                    for directory in directories
                )
            )
        contract_limit = self.contract.max_files
        if len(candidates) > contract_limit:
            raise ScanExecutionError(
                f"max_files exceeded: {len(candidates)} > {contract_limit}"
            )
        for path in candidates:
            self._assert_safe(path)
        return tuple(candidates)

    def read_bytes(self, relative_path: str | Path) -> bytes:
        self._check_deadline()
        path = self._resolve(relative_path)
        self._assert_safe(path)
        if path not in self._seen_files:
            if len(self._seen_files) >= self.contract.max_files:
                raise ScanExecutionError("max_files exceeded")
            self._seen_files.add(path)
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise ScanExecutionError("bounded scanner could not stat file") from exc
        if size > self.contract.max_file_bytes:
            raise ScanExecutionError("max_file_bytes exceeded")
        if self._total_bytes + size > self.contract.max_total_bytes:
            raise ScanExecutionError("max_total_bytes exceeded")
        chunks: list[bytes] = []
        remaining = size
        try:
            with path.open("rb") as handle:
                while remaining:
                    self._check_deadline()
                    chunk = handle.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
        except OSError as exc:
            raise ScanExecutionError("bounded scanner could not read file") from exc
        data = b"".join(chunks)
        self._total_bytes += len(data)
        if len(data) != size:
            raise ScanExecutionError("bounded scanner observed an incomplete read")
        return data

    def read_text(self, relative_path: str | Path) -> str:
        return self.read_bytes(relative_path).decode("utf-8", errors="replace")

    def _resolve(self, relative_path: str | Path) -> Path:
        candidate = (self.root / Path(relative_path)).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ScanExecutionError("scanner target escapes allowed_root") from exc
        return candidate

    def _assert_safe(self, path: Path) -> None:
        if path.is_symlink():
            raise ScanExecutionError("symlinks are not allowed in bounded scans")
        try:
            path.resolve().relative_to(self.root)
        except ValueError as exc:
            raise ScanExecutionError("scanner target escapes allowed_root") from exc

    def _check_deadline(self) -> None:
        if time.monotonic() - self._started > max(float(self.contract.deadline), 0.001):
            raise ScanExecutionError("scan deadline exceeded")


class AutonomousMaintenanceForce:
    """A bounded service that identifies maintenance issues but cannot mutate source code directly.

    It runs read-only scanners, reconciles findings through the durable lifecycle engine,
    and proposes repairs that must pass normal Sovereign governance gates.
    """

    def __init__(self, lifecycle_engine: MaintenanceLifecycleEngine) -> None:
        self.lifecycle_engine = lifecycle_engine

    def run_bounded_scan(
        self,
        contract: BoundedScanContract,
        scanner_func: Callable[..., Sequence[MaintenanceFinding]],
    ) -> Sequence[MaintenanceFinding]:
        """Safely execute a scanner within the boundaries of the contract.

        Production scanners receive a :class:`BoundedScanContext`; a legacy
        zero-argument scanner is rejected so its work cannot escape the limits.
        """
        if contract.network_allowed:
            raise ScanExecutionError(
                "Network access is strictly forbidden in bounded maintenance scans."
            )

        try:
            if not inspect.signature(scanner_func).parameters:
                raise ScanExecutionError("scanner must accept BoundedScanContext")
            raw_findings = scanner_func(BoundedScanContext(contract))
        except Exception as e:
            if isinstance(e, ScanExecutionError):
                raise
            raise ScanExecutionError(f"Scanner failed during execution: {e}")

        if len(raw_findings) > contract.max_findings:
            raise ScanExecutionError(
                f"max_findings exceeded: {len(raw_findings)} > {contract.max_findings}"
            )

        return raw_findings

    def reconcile_findings(
        self,
        existing_findings: dict[str, MaintenanceFinding],
        new_raw_findings: Sequence[MaintenanceFinding],
    ) -> dict[str, MaintenanceFinding]:
        """Pass new findings through the durable lifecycle engine."""
        updated_findings = existing_findings.copy()

        for raw_finding in new_raw_findings:
            fingerprint = raw_finding.fingerprint
            existing = updated_findings.get(fingerprint)

            # The engine applies the safety rules (reopening if suppressed, etc.)
            updated = self.lifecycle_engine.report_finding(existing, raw_finding)
            updated_findings[fingerprint] = updated

        # We also need to mark findings that went missing in this scan.
        # But we DO NOT resolve them automatically (missing != resolved).
        seen_fingerprints = {f.fingerprint for f in new_raw_findings}
        for fingerprint, existing in updated_findings.items():
            if fingerprint not in seen_fingerprints and existing.status not in [
                "VERIFIED_RESOLVED",
                "FALSE_POSITIVE",
                "HUMAN_SUPPRESSED",
            ]:
                updated_findings[fingerprint] = (
                    self.lifecycle_engine.mark_missing_in_scan(existing)
                )

        return updated_findings

    def prepare_repair_proposal(self, finding: MaintenanceFinding) -> dict[str, Any]:
        """Generate a proposal for fixing an issue, preventing direct mutation."""
        if finding.status not in ["OPEN", "REOPENED"]:
            raise ValueError(
                f"Cannot propose repair for finding in state: {finding.status}"
            )

        return {
            "proposal_type": "maintenance_repair",
            "finding_id": finding.finding_id,
            "target_id": finding.target_id,
            "justification": f"Durable finding {finding.finding_id} needs repair: {finding.deterministic_evidence}",
            "proposed_by": "AutonomousMaintenanceForce",
        }
