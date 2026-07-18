"""Lifecycle engine for Maintenance Findings."""
from aios.domain.maintenance.contracts import MaintenanceFinding

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
        mission_id: str,
        scan_id: str,
        scan_status: str,
        rescan_of: str | None,
        verification_ids: tuple[str, ...],
    ) -> MaintenanceFinding:
        """Allow resolution only after the exact completed rescan."""
        self._require_mission(finding, mission_id)
        if scan_status != "completed":
            raise SecurityViolationError(
                "incomplete or failed scan cannot resolve a maintenance finding"
            )
        if rescan_of != finding.fingerprint:
            raise SecurityViolationError("rescan is not bound to this finding")
        if not scan_id or not verification_ids:
            raise SecurityViolationError(
                "current rescan and verification evidence are required"
            )
        return self.attempt_resolution(
            finding,
            actor="system_verifier",
            deterministic_evidence=(
                f"deterministic_rescan:{scan_id};"
                f"verification_ids:{','.join(verification_ids)}"
            ),
        )

    @staticmethod
    def _require_mission(finding: MaintenanceFinding, mission_id: str) -> None:
        if not mission_id or finding.mission_id != mission_id:
            raise SecurityViolationError("finding and mission are not bound")

    def attempt_resolution(self, finding: MaintenanceFinding, actor: str, deterministic_evidence: str | None = None) -> MaintenanceFinding:
        """Mark a finding as resolved.
        
        Security rules:
        - Local models cannot alter severity or status.
        - Cloud models cannot mark resolution.
        - VERIFIED_RESOLVED requires deterministic evidence.
        """
        if actor in ["local_model", "cloud_model"]:
            raise SecurityViolationError(f"Actor '{actor}' is not authorized to mark findings as resolved.")
            
        if not deterministic_evidence:
            raise SecurityViolationError("VERIFIED_RESOLVED requires current deterministic rescan evidence.")
            
        return finding.model_copy(update={
            "status": "VERIFIED_RESOLVED",
            "resolution_evidence": deterministic_evidence
        })

    def mark_missing_in_scan(self, finding: MaintenanceFinding) -> MaintenanceFinding:
        """A finding was not seen in the latest scan.
        
        Rule: A missing scan result alone does not prove resolution.
        The status remains unchanged until explicit verification.
        """
        return finding
