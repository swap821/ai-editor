"""Tests for the Autonomous Maintenance Force service."""
import pytest
from pydantic import ValidationError

from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
from aios.domain.maintenance.service import AutonomousMaintenanceForce, ScanExecutionError

@pytest.fixture
def lifecycle():
    return MaintenanceLifecycleEngine()

@pytest.fixture
def service(lifecycle):
    return AutonomousMaintenanceForce(lifecycle)

@pytest.fixture
def base_finding():
    return MaintenanceFinding(
        finding_id="find-999",
        fingerprint="hash_dead_code",
        scanner_id="vulture",
        scanner_version="2.0.0",
        kind="dead_code",
        severity="medium",
        confidence=0.9,
        evidence_quality="deterministic",
        target_id="src/main.py",
        target_digest="hash_a",
        source_digest="hash_b",
        first_seen="2026-07-18T00:00:00Z",
        last_seen="2026-07-18T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="Unused variable 'x'",
    )

def test_bounded_scan_contract_forbids_network():
    with pytest.raises(ValidationError):
        # The contract uses a Literal[False] for network_allowed, preventing runtime overrides
        BoundedScanContract(
            allowed_root="/tmp",
            max_files=10,
            max_total_bytes=1000,
            max_file_bytes=100,
            deadline=10000,
            max_findings=5,
            network_allowed=True,  # This should fail validation
            git_history_allowed=False
        )

def test_service_enforces_max_findings(service, base_finding):
    contract = BoundedScanContract(
        allowed_root="/tmp",
        max_files=10,
        max_total_bytes=1000,
        max_file_bytes=100,
        deadline=10000,
        max_findings=1,  # Only allow 1 finding
        git_history_allowed=False
    )
    
    # Scanner returns 3 findings
    def mock_scanner():
        return [base_finding, base_finding, base_finding]
        
    results = service.run_bounded_scan(contract, mock_scanner)
    assert len(results) == 1

def test_reconcile_findings_updates_durable_state(service, base_finding):
    existing = {
        "hash_dead_code": base_finding.model_copy(update={"occurrence_count": 1})
    }
    
    new_report = base_finding.model_copy(update={"last_seen": "2026-07-18T02:00:00Z"})
    
    updated = service.reconcile_findings(existing, [new_report])
    
    assert "hash_dead_code" in updated
    assert updated["hash_dead_code"].occurrence_count == 2
    assert updated["hash_dead_code"].last_seen == "2026-07-18T02:00:00Z"

def test_service_prepares_proposal_instead_of_mutating(service, base_finding):
    proposal = service.prepare_repair_proposal(base_finding)
    
    # Service creates a proposal payload rather than fixing it directly
    assert proposal["proposal_type"] == "maintenance_repair"
    assert proposal["finding_id"] == "find-999"
    assert proposal["proposed_by"] == "AutonomousMaintenanceForce"
