"""HTTP-level coverage for aios/api/routes/execution_debugger.py — the real,
read-only mission-state view that replaced the previously-phantom
/api/v1/execution/debugger/{state,step,resume} routes ExecutionDebuggerPanel
already called (and 404'd on).
"""
from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app
from aios.api.routes.council import get_council_runtime_root
from aios.runtime.king_report import KingReport, KingReportStore


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client


def test_debugger_state_is_empty_but_real_when_no_missions(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aios.api.routes.council.config.COUNCIL_RUNTIME_DIR", tmp_path / "council_runtime"
    )
    app.dependency_overrides[get_council_runtime_root] = lambda: tmp_path / "council_runtime"
    try:
        resp = client.get("/api/v1/execution/debugger/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["missions"] == []
        assert body["count"] == 0
        assert body["steppable"] is False
    finally:
        app.dependency_overrides.pop(get_council_runtime_root, None)


def test_debugger_state_reflects_real_mission_reports(client, tmp_path) -> None:
    runtime_root = tmp_path / "council_runtime"
    store = KingReportStore(runtime_root)
    report = KingReport(
        mission_id="mission-debug-1",
        mission="test goal",
        status="completed",
        council_summary={"workers_created": ["worker-debug"], "blocked_attempts": 0},
        recommendation="approve",
        risk="GREEN",
        files=["frontend/src/pages/Login.jsx"],
        verification_result={},
        approval_needed=False,
        rollback_available=False,
        rollback_id=None,
        evidence={},
        human_summary="done",
    )
    store.write(report)

    app.dependency_overrides[get_council_runtime_root] = lambda: runtime_root
    try:
        resp = client.get("/api/v1/execution/debugger/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["missions"][0]["missionId"] == "mission-debug-1"
    finally:
        app.dependency_overrides.pop(get_council_runtime_root, None)


def test_debugger_step_is_honestly_not_supported(client) -> None:
    resp = client.post("/api/v1/execution/debugger/step", json={"missionId": "mission-1"})
    assert resp.status_code == 501
    assert "no interruptible step-machine" in resp.json()["detail"]


def test_debugger_resume_is_honestly_not_supported(client) -> None:
    resp = client.post("/api/v1/execution/debugger/resume", json={"missionId": "mission-1"})
    assert resp.status_code == 501
    assert "cannot be paused" in resp.json()["detail"]
