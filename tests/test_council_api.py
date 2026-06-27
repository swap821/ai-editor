from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from aios.api.main import app, get_council_runtime_root
from aios.runtime.contracts import KingReport, MissionContract, QueenVerdict, RunLedger
from aios.runtime.king_report import KingReportStore
from aios.runtime.run_ledger import RunLedgerStore


def _seed_mission(runtime_root: Path, mission_id: str = "mission-api-1") -> None:
    contract = MissionContract(
        mission_id=mission_id,
        goal="Improve the login page without backend changes.",
        worker_type="hybrid_plan_worker",
        created_by="planner_queen",
        workspace_root=str(runtime_root / "workspace"),
        allowed_files=["frontend/src/pages/Login.jsx"],
        forbidden_files=["backend/", ".env", "aios/security/"],
        allowed_tools=["read_file", "write_file", "run_command"],
        verification_commands=["python -m pytest tests -q"],
    )
    verdict = QueenVerdict(
        queen="security",
        verdict="allow_with_approval",
        risk="YELLOW",
        reason="MissionContract passed deterministic security review.",
    )
    ledger = RunLedger(
        mission_id=mission_id,
        mission=contract.goal,
        risk_before="YELLOW",
        risk_after="YELLOW",
        contract=contract,
        workers_created=["worker-api"],
        files_allowed=list(contract.allowed_files),
        files_touched=["frontend/src/pages/Login.jsx"],
        blocked_attempts=[{"tool": "read_file", "reason": "path forbidden"}],
        verification={"commands": [{"command": ["python", "-m", "pytest"], "returncode": 0}]},
        council_verdicts=[verdict],
        status="completed",
        created_at="2026-06-27T00:00:00+00:00",
        completed_at="2026-06-27T00:00:01+00:00",
        evidence={"council": [verdict.model_dump()]},
    )
    report = KingReport(
        mission_id=mission_id,
        mission=contract.goal,
        status="completed",
        council_summary={
            "workers_created": ["worker-api"],
            "blocked_attempts": 1,
            "council_verdicts": [verdict.model_dump()],
            "model_routing": {
                "provider": "ollama",
                "model": "llama3.1:8b",
                "used_cloud": False,
                "fallback_used": False,
            },
        },
        recommendation="approve",
        risk="YELLOW",
        files=["frontend/src/pages/Login.jsx"],
        verification_result=dict(ledger.verification),
        approval_needed=True,
        rollback_available=False,
        evidence=dict(ledger.evidence),
        human_summary="Worker completed the mission under its MissionContract.",
    )
    RunLedgerStore(runtime_root).write(ledger)
    KingReportStore(runtime_root).write(report)


def test_council_missions_lists_stored_reports(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    _seed_mission(runtime_root)
    app.dependency_overrides[get_council_runtime_root] = lambda: runtime_root
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.get("/api/v1/council/missions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    mission = body["missions"][0]
    assert mission["missionId"] == "mission-api-1"
    assert mission["status"] == "completed"
    assert mission["recommendation"] == "approve"
    assert mission["blockedAttempts"] == 1
    assert mission["verificationPassed"] is True
    assert mission["modelRouting"]["provider"] == "ollama"


def test_council_missions_skips_corrupt_artifacts(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    _seed_mission(runtime_root, mission_id="mission-api-valid")
    corrupt_dir = runtime_root / "missions" / "mission-api-corrupt"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "king_report.json").write_text("{not valid json", encoding="utf-8")
    app.dependency_overrides[get_council_runtime_root] = lambda: runtime_root
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.get("/api/v1/council/missions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert [mission["missionId"] for mission in body["missions"]] == ["mission-api-valid"]


def test_council_detail_and_report_return_422_on_corrupt_artifact(tmp_path: Path) -> None:
    """A corrupt single-mission artifact is a clean 422, not an unhandled 500
    (the list route already skips corrupt artifacts; these routes did not)."""
    runtime_root = tmp_path / "runtime"
    _seed_mission(runtime_root)
    KingReportStore(runtime_root).path_for("mission-api-1").write_text(
        "{not valid json", encoding="utf-8"
    )
    app.dependency_overrides[get_council_runtime_root] = lambda: runtime_root
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            detail = client.get("/api/v1/council/missions/mission-api-1")
            report = client.get("/api/v1/council/reports/mission-api-1")
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 422
    assert report.status_code == 422


def test_council_mission_detail_and_report_reject_path_escape(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    _seed_mission(runtime_root)
    app.dependency_overrides[get_council_runtime_root] = lambda: runtime_root
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            detail = client.get("/api/v1/council/missions/mission-api-1")
            report = client.get("/api/v1/council/reports/mission-api-1")
            escaped = client.get("/api/v1/council/reports/..%2Fsecret")
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 200
    assert detail.json()["ledger"]["blocked_attempts"][0]["reason"] == "path forbidden"
    assert report.status_code == 200
    assert report.json()["report"]["human_summary"].startswith("Worker completed")
    assert escaped.status_code in {404, 422}


def test_council_routes_reject_dotdot_traversal(tmp_path: Path) -> None:
    """A mission_id of '..' must not escape the missions/ tree on read or write.

    Uses %2e%2e (which survives client-side URL normalization) for GET, and the
    POST body for the write path, mirroring the two real escapes the review
    reproduced.
    """
    runtime_root = tmp_path / "runtime"
    _seed_mission(runtime_root)
    # A sibling artifact a single-level '..' escape would have reached/clobbered.
    (runtime_root / "king_report.json").write_text("{}", encoding="utf-8")
    app.dependency_overrides[get_council_runtime_root] = lambda: runtime_root
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            report_escape = client.get("/api/v1/council/reports/%2e%2e")
            detail_escape = client.get("/api/v1/council/missions/%2e%2e")
            write_escape = client.post(
                "/api/v1/council/approve",
                json={"missionId": "..", "reason": "traversal attempt"},
            )
    finally:
        app.dependency_overrides.clear()

    assert report_escape.status_code == 422
    assert detail_escape.status_code == 422
    assert write_escape.status_code == 422
    # The write must never have landed a decision outside missions/.
    assert not (runtime_root / "king_decision.json").exists()


def test_council_approve_records_king_report_decision(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    _seed_mission(runtime_root)
    app.dependency_overrides[get_council_runtime_root] = lambda: runtime_root
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            approved = client.post(
                "/api/v1/council/approve",
                json={"missionId": "mission-api-1", "reason": "verified by operator"},
            )
            detail = client.get("/api/v1/council/missions/mission-api-1")
    finally:
        app.dependency_overrides.clear()

    assert approved.status_code == 200
    assert approved.json()["decision"]["decision"] == "approve"
    assert approved.json()["approvalResponseWritten"] is False
    assert detail.json()["kingDecision"]["approved"] is True
    assert detail.json()["summary"]["kingDecision"]["reason"] == "verified by operator"


def test_council_reject_writes_pending_approval_response_once(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    _seed_mission(runtime_root)
    approvals_dir = runtime_root / "missions" / "mission-api-1" / "approvals"
    approvals_dir.mkdir(parents=True)
    request_id = "approval-api-1"
    (approvals_dir / f"{request_id}.request.json").write_text(
        json.dumps(
            {
                "request_id": request_id,
                "mission_id": "mission-api-1",
                "worker_id": "worker-api",
                "action": "write_file",
                "reason": "YELLOW write needs King decision",
                "created_at": "2026-06-27T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    app.dependency_overrides[get_council_runtime_root] = lambda: runtime_root
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            before = client.get("/api/v1/council/missions/mission-api-1")
            rejected = client.post(
                "/api/v1/council/reject",
                json={
                    "missionId": "mission-api-1",
                    "requestId": request_id,
                    "reason": "scope too broad",
                },
            )
            repeated = client.post(
                "/api/v1/council/reject",
                json={"missionId": "mission-api-1", "requestId": request_id},
            )
    finally:
        app.dependency_overrides.clear()

    assert before.json()["pendingApprovals"][0]["requestId"] == request_id
    assert rejected.status_code == 200
    assert rejected.json()["approvalResponseWritten"] is True
    response = json.loads((approvals_dir / f"{request_id}.response.json").read_text(encoding="utf-8"))
    assert response["approved"] is False
    assert response["reason"] == "scope too broad"
    assert repeated.status_code == 409
