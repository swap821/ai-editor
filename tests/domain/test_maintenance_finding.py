"""Tests for the Durable Maintenance Finding Lifecycle."""
import pytest
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine, SecurityViolationError

@pytest.fixture
def base_finding():
    return MaintenanceFinding(
        finding_id="find-123",
        fingerprint="hash_of_dead_code_at_foo_bar",
        scanner_id="vulture",
        scanner_version="2.0.0",
        kind="dead_code",
        severity="medium",
        confidence=0.9,
        evidence_quality="deterministic",
        target_id="src/foo.py",
        target_digest="hash1",
        source_digest="hash2",
        first_seen="2026-07-18T00:00:00Z",
        last_seen="2026-07-18T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="Unused function 'bar' at line 42",
        local_clerk_enrichment=None,
        frontier_analysis=None,
        mission_id=None,
        verification_ids=[],
        resolution_evidence=None,
        human_disposition=None
    )

def test_engine_reopens_suppressed_finding_on_reappearance(base_finding):
    engine = MaintenanceLifecycleEngine()
    
    # Simulate an existing finding that was suppressed
    existing = base_finding.model_copy(update={"status": "HUMAN_SUPPRESSED"})
    
    # A new scan reports the same finding
    new_report = base_finding.model_copy(update={
        "last_seen": "2026-07-18T01:00:00Z",
        "target_digest": "hash3"
    })
    
    updated = engine.report_finding(existing, new_report)
    
    assert updated.status == "REOPENED"
    assert updated.occurrence_count == 2
    assert updated.last_seen == "2026-07-18T01:00:00Z"
    assert updated.target_digest == "hash3"

def test_engine_blocks_unauthorized_resolution(base_finding):
    engine = MaintenanceLifecycleEngine()
    
    with pytest.raises(SecurityViolationError, match="not authorized"):
        engine.attempt_resolution(base_finding, actor="local_model", deterministic_evidence="foo")
        
    with pytest.raises(SecurityViolationError, match="not authorized"):
        engine.attempt_resolution(base_finding, actor="cloud_model", deterministic_evidence="foo")

def test_engine_rejects_free_form_resolution_without_structured_evidence(base_finding):
    engine = MaintenanceLifecycleEngine()
    
    with pytest.raises(SecurityViolationError, match="requires complete governed maintenance evidence"):
        engine.attempt_resolution(base_finding, actor="system_verifier", deterministic_evidence=None)

def test_engine_rejects_free_form_resolution_even_with_text(base_finding):
    engine = MaintenanceLifecycleEngine()
    
    with pytest.raises(SecurityViolationError, match="requires complete governed maintenance evidence"):
        engine.attempt_resolution(base_finding, actor="system_verifier", deterministic_evidence="Scan clean: 0 unused code found.")

def test_missing_scan_does_not_resolve(base_finding):
    engine = MaintenanceLifecycleEngine()
    
    # Calling mark_missing_in_scan should return the finding unchanged
    updated = engine.mark_missing_in_scan(base_finding)
    
    assert updated.status == base_finding.status
    assert updated.status == "OPEN"
