"""Autonomous Maintenance Force service."""
from typing import Sequence, Callable, Any

from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine


class ScanExecutionError(RuntimeError):
    """Raised when a scan violates bounds or fails unexpectedly."""


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
        scanner_func: Callable[[], Sequence[MaintenanceFinding]]
    ) -> Sequence[MaintenanceFinding]:
        """Safely execute a scanner within the boundaries of the contract.
        
        In a full implementation, this would enforce `max_files`, timeouts, and
        the network sandbox during the execution of `scanner_func`.
        """
        if contract.network_allowed:
            raise ScanExecutionError("Network access is strictly forbidden in bounded maintenance scans.")
            
        # Execute the raw scan (assuming the wrapper enforces limits in reality)
        try:
            raw_findings = scanner_func()
        except Exception as e:
            raise ScanExecutionError(f"Scanner failed during execution: {e}")
            
        # Enforce max findings
        if len(raw_findings) > contract.max_findings:
            raw_findings = raw_findings[:contract.max_findings]
            
        return raw_findings

    def reconcile_findings(
        self, 
        existing_findings: dict[str, MaintenanceFinding], 
        new_raw_findings: Sequence[MaintenanceFinding]
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
            if fingerprint not in seen_fingerprints and existing.status not in ["VERIFIED_RESOLVED", "FALSE_POSITIVE", "HUMAN_SUPPRESSED"]:
                updated_findings[fingerprint] = self.lifecycle_engine.mark_missing_in_scan(existing)
                
        return updated_findings

    def prepare_repair_proposal(self, finding: MaintenanceFinding) -> dict[str, Any]:
        """Generate a proposal for fixing an issue, preventing direct mutation."""
        if finding.status not in ["OPEN", "REOPENED"]:
            raise ValueError(f"Cannot propose repair for finding in state: {finding.status}")
            
        return {
            "proposal_type": "maintenance_repair",
            "finding_id": finding.finding_id,
            "target_id": finding.target_id,
            "justification": f"Durable finding {finding.finding_id} needs repair: {finding.deterministic_evidence}",
            "proposed_by": "AutonomousMaintenanceForce"
        }
