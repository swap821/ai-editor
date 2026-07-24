"""Phase 3 — Mounted HTTP proof for governed Maintenance API.

Tests:
1. Unauthenticated refusal / action boundary enforcement.
2. Capability challenge, retry, and replay protection on YELLOW routes.
3. Payload mismatch capability refusal.
4. Emergency stop refusal (503).
5. Invalid/unadmitted scanner ID refusal (400).
6. Target path escape refusal (400).
7. Shell metacharacter / forbidden path target refusal (400).
8. Governed end-to-end flow: scan → create repair mission → approve → run repair → status.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import (
    get_emergency_stop,
    get_maintenance_convergence_service,
)
from aios.api.main import app
from aios.application.evidence.verification import VerificationAuthority
from aios.application.evidence.verifier_registry import VerifierRegistry
from aios.application.executor.service import ExecutorService
from aios.application.governance import EmergencyStopController
from aios.application.maintenance.service import MaintenanceConvergenceService
from aios.application.missions.mission_service import MissionService
from aios.application.promotion.authority import PromotionAuthority
from aios.application.workspaces import StagedWorkspaceManager
from aios.domain.governance import EmergencyStopRequest
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
from aios.domain.maintenance.repository import MaintenanceFindingRepository
from aios.domain.maintenance.scan_repository import MaintenanceScanRepository
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from tests.helpers import executor_repair_result

_NO_AUTO = {"X-AIOS-No-Auto-Capability": "1"}


def _finding(*, target_digest: str, source_digest: str) -> MaintenanceFinding:
    return MaintenanceFinding(
        finding_id="finding-api-test",
        fingerprint="api-defect-fingerprint",
        scanner_id="admitted-scanner",
        scanner_version="1",
        kind="api_defect",
        severity="medium",
        confidence=1.0,
        evidence_quality="deterministic",
        target_id="bug.txt",
        target_digest=target_digest,
        source_digest=source_digest,
        first_seen="2026-07-19T00:00:00Z",
        last_seen="2026-07-19T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="api defect marker present",
    )


class _WorkerFoundry:
    def __init__(self) -> None:
        self.workspace_manager: StagedWorkspaceManager | None = None

    async def run(self, contract, **_kwargs):  # noqa: ANN001
        if (
            self.workspace_manager is not None
            and self.workspace_manager.for_mission(contract.mission_id) is None
        ):
            self.workspace_manager.stage(contract.mission_id, contract.workspace_root)
        lease = self.workspace_manager.for_mission(contract.mission_id)
        Path(lease.workspace_path, "bug.txt").write_text("fixed\n", encoding="utf-8")
        return SimpleNamespace(worker_id="worker-api-1", status="completed")


class _Executor:
    def execute(self, job):  # noqa: ANN001
        return executor_repair_result(job)


def _scanner(context):  # noqa: ANN001
    payload = context.read_text("bug.txt")
    if "API_DEFECT" not in payload:
        return ()
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return (_finding(target_digest=digest, source_digest=digest),)


@pytest.fixture()
def maintenance_env(
    tmp_path: Path,
) -> Iterator[
    tuple[TestClient, MaintenanceConvergenceService, EmergencyStopController, Path]
]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "bug.txt").write_text("API_DEFECT\n", encoding="utf-8")

    workspace = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    missions = SqliteMissionRepository(tmp_path / "missions.db")
    mission_service = MissionService(missions, workspace_manager=workspace)
    finding_repository = MaintenanceFindingRepository(tmp_path / "operational.db")
    scan_repository = MaintenanceScanRepository(tmp_path / "operational.db")

    worker = _WorkerFoundry()
    executor = _Executor()
    emergency_stop = get_emergency_stop()

    service = MaintenanceConvergenceService(
        finding_repository=finding_repository,
        scan_repository=scan_repository,
        mission_service=mission_service,
        worker_foundry=worker,
        executor_service=ExecutorService(
            profile="test",
            runner=executor.execute,
            backend_name="private_service",
        ),
        verifier_registry=VerifierRegistry(
            scanner_adapters={"admitted-scanner": _scanner}
        ),
        verification_authority=VerificationAuthority(),
        promotion_authority=PromotionAuthority(
            workspace, emergency_stop=emergency_stop
        ),
        workspace_manager=workspace,
        lifecycle_engine=MaintenanceLifecycleEngine(),
    )
    worker.workspace_manager = workspace

    app.dependency_overrides[get_maintenance_convergence_service] = lambda: service
    app.dependency_overrides[get_emergency_stop] = lambda: emergency_stop

    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            yield client, service, emergency_stop, project
    finally:
        if emergency_stop.is_engaged():
            clear_token = emergency_stop.issue_clear_capability(
                operator_id="op-clear-1",
                authentication_event_id="auth-clear-1",
                session_id="session-clear-1",
            )
            emergency_stop.clear(
                operator_id="op-clear-1",
                authentication_event_id="auth-clear-1",
                session_id="session-clear-1",
                clear_capability=clear_token,
            )
        app.dependency_overrides.clear()


def _challenge(
    client: TestClient, method: str, path: str, payload: dict | None = None
) -> str:
    response = client.request(method, path, json=payload, headers=_NO_AUTO)
    assert response.status_code == 428, (
        f"Expected 428 challenge, got {response.status_code}: {response.text}"
    )
    detail = response.json()["detail"]
    assert detail["error"] == "exact_capability_required"
    return detail["approvalToken"]


def _approved_post(client: TestClient, path: str, payload: dict) -> TestClient:
    token = _challenge(client, "POST", path, payload)
    return client.post(path, json=payload, headers={"X-AIOS-Capability": token})


# ---------------------------------------------------------------------------
# Test 1: Capability challenge, retry, replay on YELLOW route
# ---------------------------------------------------------------------------


def test_maintenance_scan_capability_challenge_and_retry(maintenance_env) -> None:
    client, _service, _stop, _project = maintenance_env

    payload = {
        "scanner_id": "admitted-scanner",
        "target_id": "bug.txt",
        "scanner_version": "1",
    }

    # Step 1: Challenge
    cap_token = _challenge(client, "POST", "/api/v1/maintenance/scans", payload)
    assert cap_token

    # Step 2: Retry with capability token succeeds (200)
    retry_response = client.post(
        "/api/v1/maintenance/scans",
        json=payload,
        headers={"X-AIOS-Capability": cap_token},
    )
    assert retry_response.status_code == 200, f"Retry failed: {retry_response.text}"
    result = retry_response.json()
    assert result["status"] == "completed"
    assert result["finding_count"] == 1

    # Step 3: Replay with spent token fails
    replay_response = client.post(
        "/api/v1/maintenance/scans",
        json=payload,
        headers={"X-AIOS-Capability": cap_token},
    )
    assert replay_response.status_code in (400, 403, 409), (
        f"Replay should be refused, got {replay_response.status_code}"
    )


# ---------------------------------------------------------------------------
# Test 2: Payload mismatch capability refusal
# ---------------------------------------------------------------------------


def test_capability_payload_mismatch_refused(maintenance_env) -> None:
    client, _service, _stop, _project = maintenance_env

    payload1 = {"scanner_id": "admitted-scanner", "target_id": "bug.txt"}
    payload2 = {"scanner_id": "admitted-scanner", "target_id": "other.txt"}

    cap_token = _challenge(client, "POST", "/api/v1/maintenance/scans", payload1)

    # Attempt to use payload1's cap_token for payload2 → refused
    resp2 = client.post(
        "/api/v1/maintenance/scans",
        json=payload2,
        headers={"X-AIOS-Capability": cap_token},
    )
    assert resp2.status_code in (400, 403, 409), (
        f"Payload mismatch should be refused, got {resp2.status_code}"
    )


# ---------------------------------------------------------------------------
# Test 3: Emergency stop engaged → 503
# ---------------------------------------------------------------------------


def test_emergency_stop_blocks_scans_and_repairs(maintenance_env) -> None:
    client, _service, emergency_stop, _project = maintenance_env

    payload = {"scanner_id": "admitted-scanner", "target_id": "bug.txt"}
    cap_token = _challenge(client, "POST", "/api/v1/maintenance/scans", payload)

    emergency_stop.engage(
        EmergencyStopRequest(
            reason="test-emergency",
            operator_id="operator-1",
            authentication_event_id="auth-event-1",
        )
    )

    response = client.post(
        "/api/v1/maintenance/scans",
        json=payload,
        headers={"X-AIOS-Capability": cap_token},
    )
    assert response.status_code in (403, 503), (
        f"Expected 403/503 on emergency stop, got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Test 4: Unadmitted scanner ID → 400
# ---------------------------------------------------------------------------


def test_unadmitted_scanner_id_refused(maintenance_env) -> None:
    client, _service, _stop, _project = maintenance_env

    payload = {"scanner_id": "evil-unadmitted-scanner", "target_id": "bug.txt"}
    response = _approved_post(client, "/api/v1/maintenance/scans", payload)
    assert response.status_code == 400, (
        f"Expected 400 for invalid scanner, got {response.status_code}"
    )
    assert "not an admitted scanner adapter" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test 5: Target path escape → 400
# ---------------------------------------------------------------------------


def test_escaped_target_path_refused(maintenance_env) -> None:
    client, _service, _stop, _project = maintenance_env

    payload = {"scanner_id": "admitted-scanner", "target_id": "../../../etc/passwd"}
    response = _approved_post(client, "/api/v1/maintenance/scans", payload)
    assert response.status_code == 400, (
        f"Expected 400 for path escape, got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Test 6: Shell metacharacter in target → 400
# ---------------------------------------------------------------------------


def test_shell_metacharacter_target_refused(maintenance_env) -> None:
    client, _service, _stop, _project = maintenance_env

    payload = {"scanner_id": "admitted-scanner", "target_id": "bug.txt; rm -rf /"}
    response = _approved_post(client, "/api/v1/maintenance/scans", payload)
    assert response.status_code == 400, (
        f"Expected 400 for shell metacharacters, got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Test 7: Governed flow: scan → create repair mission → approve → run repair → status
# ---------------------------------------------------------------------------


def test_governed_maintenance_flow_end_to_end(maintenance_env) -> None:
    client, service, _stop, project = maintenance_env

    # 1. Start bounded scan
    scan_resp = _approved_post(
        client,
        "/api/v1/maintenance/scans",
        {"scanner_id": "admitted-scanner", "target_id": "bug.txt"},
    )
    assert scan_resp.status_code == 200
    scan_data = scan_resp.json()
    assert scan_data["status"] == "completed"
    assert scan_data["finding_count"] == 1

    findings = service.finding_repository.list_findings()
    assert len(findings) == 1
    fingerprint = findings[0].fingerprint

    # 2. Create repair mission
    create_resp = _approved_post(
        client,
        "/api/v1/maintenance/repairs/missions",
        {"finding_fingerprint": fingerprint, "operator_id": "op-api-1"},
    )
    assert create_resp.status_code == 200
    mission_data = create_resp.json()
    mission_id = mission_data["mission_id"]
    assert mission_data["state"] == "draft"

    # 3. Check status (GET — GREEN route, no capability required)
    status_resp = client.get(f"/api/v1/maintenance/repairs/{mission_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["state"] == "draft"

    # 4. Attempt to run unapproved repair → refused (400)
    run_unapproved = _approved_post(
        client,
        "/api/v1/maintenance/repairs/run",
        {"mission_id": mission_id},
    )
    assert run_unapproved.status_code == 400
    assert "APPROVED" in run_unapproved.json()["detail"]

    # 5. Approve mission through the real HTTP route (organ 42) -- a genuine
    # DRAFT -> AWAITING_APPROVAL -> APPROVED transition via one governed
    # POST, not a direct in-process MissionService bypass.
    approve_resp = _approved_post(
        client,
        f"/api/v1/maintenance/repairs/{mission_id}/approve",
        {"contract_digest": mission_data["contract_digest"]},
    )
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["state"] == "approved"

    # 6. Run approved repair → 200 VERIFIED_RESOLVED
    run_resp = _approved_post(
        client,
        "/api/v1/maintenance/repairs/run",
        {"mission_id": mission_id},
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["status"] == "VERIFIED_RESOLVED"
    assert run_data["mission_id"] == mission_id

    # 7. Check final status → COMPLETED
    final_status = client.get(f"/api/v1/maintenance/repairs/{mission_id}/status")
    assert final_status.status_code == 200
    assert final_status.json()["state"] == "completed"

    # 8. Check finding status → VERIFIED_RESOLVED
    updated_finding = service.finding_repository.get(fingerprint)
    assert updated_finding.status == "VERIFIED_RESOLVED"


# ---------------------------------------------------------------------------
# Test 9: Organ 42 -- the real approval route's own refusal paths
# ---------------------------------------------------------------------------


def test_approve_unknown_mission_is_404(maintenance_env) -> None:
    client, _service, _stop, _project = maintenance_env

    resp = _approved_post(
        client,
        "/api/v1/maintenance/repairs/no-such-mission/approve",
        {"contract_digest": "irrelevant"},
    )
    assert resp.status_code == 404


def test_approve_contract_digest_mismatch_refused(maintenance_env) -> None:
    client, service, _stop, _project = maintenance_env

    scan_resp = _approved_post(
        client,
        "/api/v1/maintenance/scans",
        {"scanner_id": "admitted-scanner", "target_id": "bug.txt"},
    )
    fingerprint = service.finding_repository.list_findings()[0].fingerprint
    create_resp = _approved_post(
        client,
        "/api/v1/maintenance/repairs/missions",
        {"finding_fingerprint": fingerprint, "operator_id": "op-api-1"},
    )
    mission_id = create_resp.json()["mission_id"]

    resp = _approved_post(
        client,
        f"/api/v1/maintenance/repairs/{mission_id}/approve",
        {"contract_digest": "not-the-real-digest"},
    )
    assert resp.status_code == 403
    assert "contract digest" in resp.json()["detail"]

    status_resp = client.get(f"/api/v1/maintenance/repairs/{mission_id}/status")
    assert status_resp.json()["state"] == "draft"


def test_approve_blocked_by_emergency_stop(maintenance_env) -> None:
    client, service, emergency_stop, _project = maintenance_env

    scan_resp = _approved_post(
        client,
        "/api/v1/maintenance/scans",
        {"scanner_id": "admitted-scanner", "target_id": "bug.txt"},
    )
    fingerprint = service.finding_repository.list_findings()[0].fingerprint
    create_resp = _approved_post(
        client,
        "/api/v1/maintenance/repairs/missions",
        {"finding_fingerprint": fingerprint, "operator_id": "op-api-1"},
    )
    mission_data = create_resp.json()
    approve_path = f"/api/v1/maintenance/repairs/{mission_data['mission_id']}/approve"
    approve_payload = {"contract_digest": mission_data["contract_digest"]}
    cap_token = _challenge(client, "POST", approve_path, approve_payload)

    emergency_stop.engage(
        EmergencyStopRequest(
            reason="test-emergency",
            operator_id="operator-1",
            authentication_event_id="auth-event-1",
        )
    )

    resp = client.post(
        approve_path,
        json=approve_payload,
        headers={"X-AIOS-Capability": cap_token},
    )
    assert resp.status_code in (403, 503), (
        f"Expected 403/503 on emergency stop, got {resp.status_code}"
    )
