"""Canonical maintenance scan-to-repair-to-rescan application flow."""

from __future__ import annotations

import hashlib
import inspect
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from aios.application.evidence.verifier_registry import (
    VerifierRegistry,
    VerifierRegistryError,
    VerifierSpec,
)
from aios.application.evidence.verification import VerificationAuthority
from aios.application.executor.service import ExecutorService, environment_digest
from aios.application.missions.mission_service import MissionService
from aios.application.promotion.authority import PromotionAuthority
from aios.application.workspaces import StagedWorkspaceManager
from aios.domain.evidence import (
    EvidenceBundle,
    EvidenceCommand,
    VerificationObservation,
    VerificationPlanV1,
)
from aios.domain.maintenance.contracts import (
    MaintenanceFinding,
    MaintenanceResolutionEvidence,
)
from aios.domain.maintenance.lifecycle import (
    MaintenanceLifecycleEngine,
    SecurityViolationError,
)
from aios.domain.maintenance.mission_bridge import MaintenanceMissionBridge
from aios.domain.maintenance.repository import MaintenanceFindingRepository
from aios.domain.maintenance.service import AutonomousMaintenanceForce
from aios.domain.maintenance.scan_repository import (
    MaintenanceScan,
    MaintenanceScanRepository,
)
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.missions.mission_state import MissionState
from aios.application.workspaces.staged import tree_digest


class MaintenanceConvergenceError(RuntimeError):
    """Raised when a maintenance lifecycle cannot proceed safely."""


@dataclass(frozen=True)
class MaintenanceScanResult:
    scan: MaintenanceScan
    findings: tuple[MaintenanceFinding, ...]


@dataclass(frozen=True)
class MaintenanceRepairResult:
    status: str
    mission_id: str
    finding: MaintenanceFinding
    verification_ids: tuple[str, ...] = ()
    scan_id: str | None = None
    promotion_status: str | None = None
    reason: str | None = None


class MaintenanceConvergenceService:
    """Coordinate existing canonical organs without creating maintenance ones."""

    def __init__(
        self,
        *,
        finding_repository: MaintenanceFindingRepository,
        scan_repository: MaintenanceScanRepository,
        mission_service: MissionService,
        worker_foundry: Any,
        executor_service: ExecutorService,
        verifier_registry: VerifierRegistry | None = None,
        verification_authority: VerificationAuthority,
        promotion_authority: PromotionAuthority,
        workspace_manager: StagedWorkspaceManager,
        lifecycle_engine: MaintenanceLifecycleEngine,
    ) -> None:
        self.finding_repository = finding_repository
        self.scan_repository = scan_repository
        self.mission_service = mission_service
        self.worker_foundry = worker_foundry
        self.executor_service = executor_service
        self.verifier_registry = verifier_registry or VerifierRegistry(
            scanner_adapters={}
        )
        self.verification_authority = verification_authority
        self.promotion_authority = promotion_authority
        self.workspace_manager = workspace_manager
        self.lifecycle_engine = lifecycle_engine
        self._maintenance_force = AutonomousMaintenanceForce(lifecycle_engine)

    def run_scan(
        self,
        contract: BoundedScanContract,
        scanner: Callable[..., Sequence[MaintenanceFinding]],
        *,
        scanner_id: str,
        scanner_version: str,
        target_id: str,
        source_digest: str,
        rescan_of: str | None = None,
    ) -> MaintenanceScanResult:
        """Run one bounded scan and durably reconcile only its observations."""
        scan_id = f"scan-{uuid.uuid4().hex}"
        started_at = _utc_now()
        scan = MaintenanceScan(
            scan_id=scan_id,
            scanner_id=scanner_id,
            scanner_version=scanner_version,
            target_id=target_id,
            source_digest=source_digest,
            contract=contract,
            status="started",
            started_at=started_at,
            rescan_of=rescan_of,
        )
        self.scan_repository.save(scan)
        try:
            raw_findings = tuple(
                self._maintenance_force.run_bounded_scan(contract, scanner)
            )
            for finding in raw_findings:
                if (
                    finding.scanner_id != scanner_id
                    or finding.scanner_version != scanner_version
                ):
                    raise ValueError(
                        "scanner finding provenance does not match the scan contract"
                    )
        except Exception as exc:  # noqa: BLE001 - scan failures become durable truth
            status = "incomplete" if _is_incomplete_scan(exc) else "failed"
            failed = scan.model_copy(
                update={
                    "status": status,
                    "completed_at": _utc_now(),
                    "failure_reason": str(exc),
                }
            )
            self.scan_repository.save(failed)
            return MaintenanceScanResult(scan=failed, findings=())

        completed = scan.model_copy(
            update={
                "status": "completed",
                "completed_at": _utc_now(),
                "finding_count": len(raw_findings),
                "finding_fingerprints": tuple(
                    finding.fingerprint for finding in raw_findings
                ),
            }
        )
        self.scan_repository.save(completed)
        reconciled: list[MaintenanceFinding] = []
        for finding in raw_findings:
            existing = self.finding_repository.get(finding.fingerprint)
            updated = self.lifecycle_engine.report_finding(existing, finding)
            self.finding_repository.save(updated)
            reconciled.append(updated)
        return MaintenanceScanResult(scan=completed, findings=tuple(reconciled))

    def create_repair_mission(
        self,
        fingerprint: str,
        *,
        operator_id: str,
        workspace_root: str,
    ) -> Any:
        finding = self.finding_repository.get(fingerprint)
        if finding is None:
            raise MaintenanceConvergenceError("maintenance finding does not exist")
        contract = MaintenanceMissionBridge.create_repair_mission(
            finding,
            operator_id,
            workspace_root=workspace_root,
        )
        record = self.mission_service.create(contract)
        self.finding_repository.save(
            self.lifecycle_engine.bind_mission(finding, record.mission_id)
        )
        return record

    async def run_approved_repair(
        self,
        mission_id: str,
        *,
        scanner: Callable[..., Sequence[MaintenanceFinding]],
        rescan_contract: BoundedScanContract,
        capability_consumer: Callable[[Any], bool],
        create_checkpoint: Callable[[Any], str],
        restore_checkpoint: Callable[[str, Any], bool],
        smoke_test: Callable[[Any], bool],
    ) -> MaintenanceRepairResult:
        """Execute one already-approved repair through the canonical organs."""
        record = self.mission_service.repository.get(mission_id)
        if record.state is not MissionState.APPROVED:
            raise MaintenanceConvergenceError(
                f"maintenance repair requires approved mission, got {record.state.value}"
            )
        fingerprint = str(record.contract.metadata.get("finding_fingerprint", ""))
        finding = self.finding_repository.get(fingerprint)
        if finding is None or finding.mission_id != mission_id:
            raise MaintenanceConvergenceError(
                "mission is not bound to a durable finding"
            )
        self.finding_repository.save(
            self.lifecycle_engine.mark_repairing(finding, mission_id)
        )

        try:
            self.mission_service.start_execution(mission_id)
            worker_result = self.worker_foundry.run(
                record.contract,
                strategy=record.contract.metadata.get("worker_strategy", "code"),
                context={"executor_policy": "private_service"},
            )
            if inspect.isawaitable(worker_result):
                worker_result = await worker_result
            worker_id = _worker_id(worker_result)
            if str(getattr(worker_result, "status", "completed")) != "completed":
                return self._failed(
                    mission_id,
                    finding,
                    f"worker status: {getattr(worker_result, 'status', 'unknown')}",
                )
            self.mission_service.start_verification(mission_id)
            finding = self.lifecycle_engine.mark_verifying(
                self.finding_repository.get(fingerprint) or finding,
                mission_id,
            )
            self.finding_repository.save(finding)
            lease = self.workspace_manager.for_mission(mission_id)
            if lease is None:
                return self._failed(mission_id, finding, "staged workspace unavailable")
            diff = self.workspace_manager.diff(lease)
            verifier_payload = record.contract.metadata.get("verification_spec", {})
            verifier_spec = VerifierSpec.model_validate(verifier_payload).model_copy(
                update={"allowed_root": str(lease.workspace_path)}
            )
            verification_contract = rescan_contract.model_copy(
                update={"allowed_root": str(lease.workspace_path)}
            )
            verifier_run = self.verifier_registry.run(
                verifier_spec,
                contract=verification_contract,
                scanner=scanner,
            )
            environment = environment_digest(
                {
                    "verifier_id": verifier_run.verifier_id,
                    "verifier_version": verifier_run.version,
                }
            )
            plan = VerificationPlanV1(
                intended_behavior=f"repair finding {finding.finding_id}",
                targets=(finding.target_id,),
                required_tests=(verifier_run.verifier_id,),
                # The deterministic rescan is an authoritative scanner result,
                # not a test-runner claim.  Its explicit weak floor is still
                # bound to the current workspace/diff and a completed scan.
                minimum_strength=1,
            )
            observation = VerificationObservation(
                command=verifier_run.verifier_id,
                exit_code=0 if verifier_run.passed else 1,
                stdout=verifier_run.stdout,
                stderr=verifier_run.stderr,
                passed_count=1 if verifier_run.passed else 0,
                failed_count=0 if verifier_run.passed else 1,
                tool_version=f"{verifier_run.verifier_id}@{verifier_run.version}",
                observed_at=verifier_run.ended_at,
            )
            verification = self.verification_authority.verify(
                mission_id=mission_id,
                action_id=f"maintenance-action:{mission_id}",
                worker_id=worker_id,
                target=finding.target_id,
                plan=plan,
                workspace_digest=str(diff["workspace_digest"]),
                diff_digest=str(diff["diff_digest"]),
                environment_digest=environment,
                observation=observation,
            )
            if not verification.meets_requirement:
                return self._failed(
                    mission_id,
                    finding,
                    "authoritative verification failed",
                )
            bundle = EvidenceBundle(
                mission_id=mission_id,
                worker_id=worker_id,
                contract_digest=record.contract_digest,
                workspace_digest=str(diff["workspace_digest"]),
                diff_digest=str(diff["diff_digest"]),
                # EvidenceBundle predates the structured verifier registry and
                # calls this correlation field executor_job_id. Preserve the
                # existing promotion contract while binding it to the real
                # verifier run, never to a fabricated shell job.
                executor_job_id=verifier_run.run_id,
                environment_digest=environment,
                commands=(
                    EvidenceCommand(
                        command=verifier_run.verifier_id,
                        return_code=0 if verifier_run.passed else 1,
                        stdout_digest=_digest(verifier_run.stdout),
                        stderr_digest=_digest(verifier_run.stderr),
                        tool_version=f"{verifier_run.verifier_id}@{verifier_run.version}",
                        observed_at=verifier_run.ended_at,
                    ),
                ),
                verification_strength=verification.strength,
                targets_exercised=(finding.target_id,),
                started_at=verifier_run.started_at,
                ended_at=verifier_run.ended_at,
            )
            promotion = self.promotion_authority.promote(
                self._promotion_request(
                    record=record,
                    finding=finding,
                    lease=lease,
                    diff=diff,
                    worker_id=worker_id,
                    executor_job_id=verifier_run.run_id,
                    environment_digest_value=environment,
                    verification=verification,
                    bundle=bundle,
                ),
                create_checkpoint=create_checkpoint,
                apply_staged_diff=lambda _request: self.workspace_manager.apply(lease),
                smoke_test=smoke_test,
                restore_checkpoint=restore_checkpoint,
                consume_capability=capability_consumer,
                mark_completed=None,
            )
            if promotion.status.value != "promoted":
                return self._failed(
                    mission_id,
                    finding,
                    ";".join(promotion.reason_codes) or "promotion failed",
                    status="PROMOTION_FAILED",
                )
            rescan = self.run_scan(
                rescan_contract,
                scanner,
                scanner_id=finding.scanner_id,
                scanner_version=finding.scanner_version,
                target_id=finding.target_id,
                source_digest=_source_digest(record.contract.workspace_root)
                if record.contract.workspace_root
                else finding.source_digest,
                rescan_of=finding.fingerprint,
            )
            resolution_evidence = MaintenanceResolutionEvidence(
                mission_id=mission_id,
                mission_contract_digest=record.contract_digest,
                action_id=f"maintenance-action:{mission_id}",
                promotion=promotion,
                verification_results=(verification,),
                workspace_digest=str(diff["workspace_digest"]),
                diff_digest=str(diff["diff_digest"]),
                rescan_id=rescan.scan.scan_id,
                scanner_id=finding.scanner_id,
                scanner_version=finding.scanner_version,
                target_id=finding.target_id,
                source_digest=rescan.scan.source_digest,
            )
            try:
                final_finding = self.reconcile_rescan(resolution_evidence)
            except MaintenanceConvergenceError as exc:
                if rescan.scan.status != "completed":
                    return MaintenanceRepairResult(
                        status="RESCAN_INCOMPLETE",
                        mission_id=mission_id,
                        finding=self.finding_repository.get(fingerprint) or finding,
                        verification_ids=(verification.verification_id,),
                        scan_id=rescan.scan.scan_id,
                        promotion_status=promotion.status.value,
                        reason=str(exc),
                    )
                return self._failed(
                    mission_id,
                    self.finding_repository.get(fingerprint) or finding,
                    f"rescan authority refused: {exc}",
                )
            if final_finding.status != "VERIFIED_RESOLVED":
                return MaintenanceRepairResult(
                    status="RESCAN_INCOMPLETE",
                    mission_id=mission_id,
                    finding=final_finding,
                    verification_ids=(verification.verification_id,),
                    scan_id=rescan.scan.scan_id,
                    promotion_status=promotion.status.value,
                    reason="current deterministic rescan did not prove resolution",
                )

            # Authoritative post-promotion rescan proved resolution: NOW complete mission
            self.mission_service.complete(
                mission_id,
                evidence_digest=promotion.evidence_ids[0] if promotion.evidence_ids else None,
            )

            return MaintenanceRepairResult(
                status="VERIFIED_RESOLVED",
                mission_id=mission_id,
                finding=final_finding,
                verification_ids=(verification.verification_id,),
                scan_id=rescan.scan.scan_id,
                promotion_status=promotion.status.value,
            )
        except (VerifierRegistryError, ValueError) as exc:
            current = self.finding_repository.get(fingerprint) or finding
            return self._failed(mission_id, current, str(exc))
        except Exception as exc:  # noqa: BLE001 - mission failures are durable
            current = self.finding_repository.get(fingerprint) or finding
            return self._failed(mission_id, current, str(exc))

    def reconcile_rescan(
        self, evidence: MaintenanceResolutionEvidence
    ) -> MaintenanceFinding:
        """Reconcile only a complete, authority-bound resolution contract."""
        scan = self.scan_repository.get(evidence.rescan_id)
        if scan is None:
            raise MaintenanceConvergenceError("authoritative rescan does not exist")
        fingerprint = scan.rescan_of
        if not fingerprint:
            raise MaintenanceConvergenceError("rescan is not bound to a finding")
        finding = self.finding_repository.get(fingerprint)
        if finding is None:
            raise MaintenanceConvergenceError("rescan finding does not exist")
        if fingerprint in scan.finding_fingerprints:
            return finding
        try:
            mission = self.mission_service.repository.get(evidence.mission_id)
        except Exception as exc:  # noqa: BLE001 - authority lookup fails closed
            raise MaintenanceConvergenceError(
                "authoritative mission does not exist"
            ) from exc
        for result in evidence.verification_results:
            authoritative = self.verification_authority.get(result.verification_id)
            if authoritative is None or authoritative is not result:
                raise MaintenanceConvergenceError(
                    "verification result is not held by VerificationAuthority"
                )
        try:
            resolved = self.lifecycle_engine.resolve_after_rescan(
                finding,
                mission=mission,
                evidence=evidence,
                scan=scan,
                verification_is_current=lambda result: self.verification_authority.is_current(
                    result,
                    workspace_digest=evidence.workspace_digest,
                    diff_digest=evidence.diff_digest,
                    freshness_seconds=300,
                ),
            )
        except SecurityViolationError as exc:
            raise MaintenanceConvergenceError(str(exc)) from exc
        self.finding_repository.save(resolved)
        return resolved

    def _failed(
        self,
        mission_id: str,
        finding: MaintenanceFinding,
        reason: str,
        *,
        status: str = "VERIFICATION_FAILED",
    ) -> MaintenanceRepairResult:
        try:
            if self.mission_service.repository.get(mission_id).state in {
                MissionState.RUNNING,
                MissionState.VERIFYING,
            }:
                self.mission_service.fail(mission_id, reason=reason)
        except Exception:  # noqa: BLE001 - preserve the durable finding failure
            pass
        failed = self.lifecycle_engine.mark_verification_failed(
            finding, mission_id, reason
        )
        self.finding_repository.save(failed)
        return MaintenanceRepairResult(
            status=status,
            mission_id=mission_id,
            finding=failed,
            reason=reason,
        )

    @staticmethod
    def _promotion_request(
        *,
        record: Any,
        finding: MaintenanceFinding,
        lease: Any,
        diff: dict[str, object],
        worker_id: str,
        executor_job_id: str,
        environment_digest_value: str,
        verification: Any,
        bundle: EvidenceBundle,
    ) -> Any:
        from aios.domain.promotion import PromotionRequest

        return PromotionRequest(
            mission_id=record.mission_id,
            action_id=f"maintenance-action:{record.mission_id}",
            worker_id=worker_id,
            executor_job_id=executor_job_id,
            environment_digest=environment_digest_value,
            project_root=lease.project_root,
            lease=lease,
            current_state=MissionState.VERIFYING,
            contract_digest=record.contract_digest,
            authoritative_contract_digest=record.contract_digest,
            policy_version=record.policy_version,
            authoritative_policy_version=record.policy_version,
            workspace_digest=str(diff["workspace_digest"]),
            diff_digest=str(diff["diff_digest"]),
            verification_results=(verification,),
            evidence_bundle=bundle,
            required_targets=(finding.target_id,),
            required_strength=verification.required_strength,
            freshness_seconds=300,
            requires_capability=True,
            capability_id=f"mission:{record.mission_id}",
            capability_digest=record.capability_digest,
            authoritative_capability_digest=record.capability_digest,
        )


def _worker_id(result: Any) -> str:
    direct = getattr(result, "worker_id", None)
    if direct:
        return str(direct)
    handle = getattr(result, "handle", None)
    worker_id = getattr(handle, "worker_id", None)
    if worker_id:
        return str(worker_id)
    raise MaintenanceConvergenceError("worker result has no identity")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _source_digest(root: str) -> str:
    try:
        return tree_digest(Path(root).resolve())
    except (OSError, ValueError):
        return _digest(root)


def _is_incomplete_scan(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in ("max_", "deadline", "bounded", "symlink", "escape")
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "MaintenanceConvergenceError",
    "MaintenanceConvergenceService",
    "MaintenanceRepairResult",
    "MaintenanceScanResult",
]
