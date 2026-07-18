"""Tests for Maintenance-to-Mission Repair Bridge."""
import pytest

from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.mission_bridge import MaintenanceMissionBridge
from aios.domain.missions.mission_contract import MissionContract


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


def test_bridge_creates_valid_mission(base_finding):
    mission = MaintenanceMissionBridge.create_repair_mission(base_finding, "operator-1")
    
    assert isinstance(mission, MissionContract)
    assert mission.operator_id == "operator-1"
    assert "find-999" in mission.goal
    assert "Unused variable" in mission.goal
    
    # Assert bindings
    assert mission.allowed_files == ["src/main.py"]
    assert mission.metadata["finding_id"] == "find-999"
    assert mission.metadata["finding_fingerprint"] == "hash_dead_code"
    assert mission.metadata["scanner_id"] == "vulture"
    assert mission.metadata["scanner_version"] == "2.0.0"
    assert mission.metadata["required_post_repair_rescan"] is True
    
    # Assert verification plan explicitly requires rescan
    assert any("vulture" in cmd and "src/main.py" in cmd for cmd in mission.verification_plan.commands)
