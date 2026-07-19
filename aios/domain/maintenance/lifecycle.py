"""Lifecycle engine for Maintenance Findings."""

from collections.abc import Callable

from aios.domain.evidence import VerificationResult
from aios.domain.maintenance.contracts import (
    MaintenanceFinding,
    MaintenanceResolutionEvidence,
)
from aios.domain.maintenance.scan_repository import MaintenanceScan
from aios.domain.missions.mission_repository import MissionRecord
from aios.domain.missions.mission_state import MissionState
from aios.domain.promotion import PromotionStatus

class SecurityViolationError(RuntimeError):
    """Raised when an actor attempts an unauthorized state transition."""

class MaintenanceLifecycleEngine:
    """Enforces state transitions and security rules for durable findings."""

    def report_finding(self, existing: MaintenanceFinding | None, new_report: MaintenanceFinding) -> MaintenanceFinding:
        """Process a new scan result for a finding."""
        if not existing:
            return new_report

        # If it reappears after being resolved/suppressed, reopen it
        if existing.status in ["VERIFIED_RESOLVED", "FALSE_POSITIVE", "HUMAN_SUPPRESSED"]:
            new_status = "REOPENED"
        else:
            new_status = existing.status

        return existing.model_copy(update={
            "last_seen": new_report.last_seen,
            "occurrence_count": existing.occurrence_count + 1,
            "status": new_status,
            "deterministic_evidence": new_report.deterministic_evidence,
            "target_digest": new_report.target_digest,
            "source_digest": new_report.source_digest
        })

    def bind_mission(
        self, finding: MaintenanceFinding, mission_id: str
    ) -> MaintenanceFinding:
        """Bind one governed MissionService record to a durable finding."""
        if finding.status not in {"OPEN", "REOPENED", "VERIFICATION_FAILED"}:
            raise SecurityViolationError(
                f"finding cannot create a repair mission from state {finding.status}"
            )
        if not mission_id:
            raise SecurityViolationError("maintenance mission id is required")
        return finding.model_copy(
            update={"mission_id": mission_id, "status": "MISSION_CREATED"}
        )

    def mark_repairing(
        self, finding: MaintenanceFinding, mission_id: str
    ) -> MaintenanceFinding:
        self._require_mission(finding, mission_id)
        if finding.status != "MISSION_CREATED":
            raise SecurityViolationError(
                f"finding cannot start repair from state {finding.status}"
            )
        return finding.model_copy(update={"status": "REPAIRING"})

    def mark_verifying(
        self, finding: MaintenanceFinding, mission_id: str
    ) -> MaintenanceFinding:
        self._require_mission(finding, mission_id)
        if finding.status != "REPAIRING":
            raise SecurityViolationError(
                f"finding cannot verify from state {finding.status}"
            )
        return finding.model_copy(update={"status": "VERIFYING"})

    def mark_verification_failed(
        self, finding: MaintenanceFinding, mission_id: str, reason: str
    ) -> MaintenanceFinding:
        self._require_mission(finding, mission_id)
        return finding.model_copy(
            update={"status": "VERIFICATION_FAILED", "resolution_evidence": reason}
        )

    def resolve_after_rescan(
        self,
        finding: MaintenanceFinding,
        *,
        mission: MissionRecord,
        evidence: MaintenanceResolutionEvidence,
        scan: MaintenanceScan,
        verification_is_current: Callable[[VerificationResult], bool],
    ) -> MaintenanceFinding:
        """Allow resolution only after every governed proof is authoritative."""
        if finding.status != "VERIFYING":
            raise SecurityViolationError(
                "finding must be VERIFYING before governed resolution"
            )
        self._require_mission(finding, evidence.mission_id)
        if mission.mission_id != evidence.mission_id:
            raise SecurityViolationError("mission evidence is not authoritative")
        if mission.state not in (MissionState.VERIFYING, MissionState.COMPLETED):
            raise SecurityViolationError("mission must be verifying or completed for rescan proof")
        if mission.contract_digest != evidence.mission_contract_digest:
            raise SecurityViolationError("mission contract digest does not match")
        if mission.contract.metadata.get("finding_fingerprint") != finding.fingerprint:
            raise SecurityViolationError("mission is not bound to this finding")
        promotion = evidence.promotion
        if promotion.status is not PromotionStatus.PROMOTED:
            raise SecurityViolationError("promotion did not succeed")
        if promotion.mission_id != evidence.mission_id:
            raise SecurityViolationError("promotion mission does not match")
        if promotion.action_id != evidence.action_id:
            raise SecurityViolationError("promotion action does not match")
        if promotion.diff_digest != evidence.diff_digest:
            raise SecurityViolationError("promotion diff does not match")
        if not evidence.verification_results:
            raise SecurityViolationError("verification results are required")
        for result in evidence.verification_results:
            if result.mission_id != evidence.mission_id:
                raise SecurityViolationError("verification mission does not match")
            if result.action_id != evidence.action_id:
                raise SecurityViolationError("verification action does not match")
            if result.target != evidence.target_id:
                raise SecurityViolationError("verification target does not match")
            if result.workspace_digest != evidence.workspace_digest:
                raise SecurityViolationError("verification workspace does not match")
            if result.diff_digest != evidence.diff_digest:
                raise SecurityViolationError("verification diff does not match")
            if not result.meets_requirement or not verification_is_current(result):
                raise SecurityViolationError("verification is stale or insufficient")
        if evidence.rescan_id != scan.scan_id:
            raise SecurityViolationError("rescan identity does not match")
        if scan.status != "completed":
            raise SecurityViolationError(
                "incomplete or failed scan cannot resolve a maintenance finding"
            )
        if scan.rescan_of != finding.fingerprint:
            raise SecurityViolationError("rescan is not bound to this finding")
        if scan.scanner_id != finding.scanner_id or scan.scanner_id != evidence.scanner_id:
            raise SecurityViolationError("scanner identity does not match")
        if (
            scan.scanner_version != finding.scanner_version
            or scan.scanner_version != evidence.scanner_version
        ):
            raise SecurityViolationError("scanner version does not match")
        if scan.target_id != finding.target_id or scan.target_id != evidence.target_id:
            raise SecurityViolationError("scan target does not match")
        if scan.source_digest != evidence.source_digest:
            raise SecurityViolationError("scan source provenance does not match")
        if finding.fingerprint in scan.finding_fingerprints:
            raise SecurityViolationError("finding reappeared in the rescan")
        return finding.model_copy(
            update={
                "status": "VERIFIED_RESOLVED",
                "verification_ids": [
                    result.verification_id for result in evidence.verification_results
                ],
                "resolution_evidence": (
                    f"rescan:{scan.scan_id};promotion:{promotion.status.value};"
                    f"source:{scan.source_digest}"
                ),
            }
        )

    @staticmethod
    def _require_mission(finding: MaintenanceFinding, mission_id: str) -> None:
        if not mission_id or finding.mission_id != mission_id:
            raise SecurityViolationError("finding and mission are not bound")

    def attempt_resolution(
        self,
        finding: MaintenanceFinding,
        actor: str,
        deterministic_evidence: str | None = None,
    ) -> MaintenanceFinding:
        """Reject the legacy free-form resolution escape hatch."""
        if actor in {"local_model", "cloud_model"}:
            raise SecurityViolationError(
                f"Actor '{actor}' is not authorized to mark findings as resolved."
            )
        raise SecurityViolationError(
            "resolution requires complete governed maintenance evidence"
        )

    def mark_missing_in_scan(self, finding: MaintenanceFinding) -> MaintenanceFinding:
        """A finding was not seen in the latest scan.
        
        Rule: A missing scan result alone does not prove resolution.
        The status remains unchanged until explicit verification.
        """
        return finding
