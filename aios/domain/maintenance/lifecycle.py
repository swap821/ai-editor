"""Lifecycle engine for Maintenance Findings."""
from datetime import datetime
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
