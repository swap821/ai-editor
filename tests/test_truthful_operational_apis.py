"""Mounted proof that operational panels expose durable truth only."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import (
    get_anthropic_client,
    get_bedrock_client,
    get_gemini_client,
    get_hiring_repository,
    get_maintenance_finding_repository,
    get_maintenance_scan_repository,
    get_ollama_client,
    get_openai_client,
    get_skill_repository,
)
from aios.api.main import app
from aios.domain.intelligence.repository import HiringRecord, HiringRecordRepository
from aios.domain.learning.repository import SkillRecord, SkillRepository
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.repository import MaintenanceFindingRepository
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.scan_repository import (
    MaintenanceScan,
    MaintenanceScanRepository,
)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, client=("127.0.0.1", 12345))


@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/hiring/proposals",
        "/api/v1/skills",
        "/api/v1/maintenance/findings",
        "/api/v1/maintenance/scans",
    ),
)
def test_default_operational_reads_are_truthful_empty_states(
    client: TestClient, path: str
) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "status": "empty",
        "source": "durable_repository",
    }


def _hiring_record(request_id: str = "request-1") -> HiringRecord:
    return HiringRecord(
        request_id=request_id,
        mission_id="mission-1",
        purpose="bounded diagnosis",
        task_class="reasoning",
        data_classification="public",
        candidate_providers=["ollama", "gemini"],
        eligible_providers=["ollama"],
        selected_provider="ollama",
        selected_model="qwen2.5:3b",
        reason="local adapter is available within policy",
        redactions=[],
        cost_class="free",
        external_data_scope="none",
        human_approval_required=False,
        status="verified",
        created_at="2026-07-18T00:00:00Z",
        updated_at="2026-07-18T00:00:01Z",
        provider_call_provenance={"provider_call_id": "call-1"},
    )


def _skill_record(skill_id: str = "skill-1") -> SkillRecord:
    return SkillRecord(
        skill_id=skill_id,
        version=1,
        problem_signature="bounded-diagnosis",
        applicability_conditions={"task_class": "reasoning"},
        known_exclusions=["secret-data"],
        required_inputs=["mission_id"],
        required_project_state={"branch": "master"},
        procedure="Read evidence and run the deterministic verifier.",
        allowed_tools=["read_file"],
        allowed_scope_pattern="training_ground/**",
        expected_observations=["verification_passed"],
        verification_plan="Run the bounded verifier.",
        escalation_conditions=["state mismatch"],
        source_trajectory_ids=["trajectory-1"],
        confidence=0.9,
        success_count=3,
        failure_count=0,
        last_validated_versions=["5e73a37"],
        state="active",
        created_at="2026-07-18T00:00:00Z",
        updated_at="2026-07-18T00:00:01Z",
    )


def _finding() -> MaintenanceFinding:
    return MaintenanceFinding(
        finding_id="finding-1",
        fingerprint="fingerprint-1",
        scanner_id="deterministic-scanner",
        scanner_version="1",
        kind="missing-test",
        severity="medium",
        confidence=1.0,
        evidence_quality="deterministic",
        target_id="training_ground/example.py",
        target_digest="target-1",
        source_digest="source-1",
        first_seen="2026-07-18T00:00:00Z",
        last_seen="2026-07-18T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="test is missing",
    )


def _scan() -> MaintenanceScan:
    return MaintenanceScan(
        scan_id="scan-1",
        scanner_id="deterministic-scanner",
        scanner_version="1",
        target_id="training_ground",
        source_digest="source-1",
        contract=BoundedScanContract(
            allowed_root="training_ground",
            max_files=10,
            max_total_bytes=1000,
            max_file_bytes=200,
            deadline=123,
            max_findings=5,
            git_history_allowed=False,
        ),
        status="completed",
        started_at="2026-07-18T00:00:00Z",
        completed_at="2026-07-18T00:00:01Z",
        finding_count=1,
    )


def test_operational_repositories_survive_restart_and_update(tmp_path) -> None:
    database = tmp_path / "operational.db"
    hiring = HiringRecordRepository(database)
    hiring.save(_hiring_record())
    hiring.save(_hiring_record().model_copy(update={"status": "reused"}))

    skills = SkillRepository(database)
    skills.save(_skill_record())
    scans = MaintenanceScanRepository(database)
    scans.save(_scan())

    assert HiringRecordRepository(database).get("request-1").status == "reused"
    assert SkillRepository(database).list_skills()[0].skill_id == "skill-1"
    assert MaintenanceScanRepository(database).list_scans()[0].scan_id == "scan-1"


def test_mounted_operational_reads_use_durable_repositories(tmp_path) -> None:
    database = tmp_path / "operational.db"
    hiring = HiringRecordRepository(database)
    skills = SkillRepository(database)
    findings = MaintenanceFindingRepository(database)
    scans = MaintenanceScanRepository(database)
    hiring.save(_hiring_record())
    skills.save(_skill_record())
    findings.save(_finding())
    scans.save(_scan())

    app.dependency_overrides[get_hiring_repository] = lambda: hiring
    app.dependency_overrides[get_skill_repository] = lambda: skills
    app.dependency_overrides[get_maintenance_finding_repository] = lambda: findings
    app.dependency_overrides[get_maintenance_scan_repository] = lambda: scans
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as mounted:
            for path, key, expected_id in (
                ("/api/v1/hiring/proposals", "request_id", "request-1"),
                ("/api/v1/skills", "skill_id", "skill-1"),
                ("/api/v1/maintenance/findings", "finding_id", "finding-1"),
                ("/api/v1/maintenance/scans", "scan_id", "scan-1"),
            ):
                body = mounted.get(path).json()
                assert body["status"] == "available"
                assert body["source"] == "durable_repository"
                assert body["items"][0][key] == expected_id
    finally:
        app.dependency_overrides.clear()


def test_hiring_status_uses_injected_runtime_adapters() -> None:
    class LiveLocal:
        def is_available(self) -> bool:
            return True

    app.dependency_overrides[get_ollama_client] = lambda: LiveLocal()
    app.dependency_overrides[get_bedrock_client] = lambda: None
    app.dependency_overrides[get_gemini_client] = lambda: object()
    app.dependency_overrides[get_openai_client] = lambda: None
    app.dependency_overrides[get_anthropic_client] = lambda: None
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as mounted:
            body = mounted.get("/api/v1/hiring/status").json()
    finally:
        app.dependency_overrides.clear()

    assert body["status"] == "available"
    assert body["source"] == "runtime_adapters"
    assert body["providers"] == [
        {"provider": "ollama", "configured": True, "availability": "available"},
        {"provider": "bedrock", "configured": False, "availability": "unavailable"},
        {"provider": "gemini", "configured": True, "availability": "unknown"},
        {"provider": "openai", "configured": False, "availability": "unavailable"},
        {"provider": "anthropic", "configured": False, "availability": "unavailable"},
    ]
