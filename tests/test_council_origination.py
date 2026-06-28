"""API tests for chat -> council mission origination (deliberate -> approve -> act).

Note: Starlette's TestClient runs BackgroundTasks to completion before the POST
returns, so after originate the deliberation has run, and after approve the
execution (real deterministic worker subprocess) has run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aios import config
from aios.api.main import app, get_council_runtime_root


def _client_overrides(runtime_root: Path):
    app.dependency_overrides[get_council_runtime_root] = lambda: runtime_root


def test_originate_disabled_returns_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_ORIGINATION", False)
    _client_overrides(tmp_path / "runtime")
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            r = client.post(
                "/api/v1/council/missions",
                json={"goal": "improve login", "allowedFiles": ["x.txt"], "sessionId": "s-off"},
            )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404


def test_originate_deliberates_to_awaiting_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "COUNCIL_ORIGINATION", True)
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", tmp_path / "ws")
    (tmp_path / "ws").mkdir()
    runtime_root = tmp_path / "runtime"
    _client_overrides(runtime_root)
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            r = client.post(
                "/api/v1/council/missions",
                json={
                    "goal": "Improve the login page",
                    "allowedFiles": ["Login.jsx"],
                    "verificationCommands": [],
                    "sessionId": "s-delib",
                },
            )
            assert r.status_code == 200
            mission_id = r.json()["missionId"]
            assert r.json()["status"] == "deliberating"
            detail = client.get(f"/api/v1/council/missions/{mission_id}")
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 200
    assert detail.json()["report"]["status"] == "awaiting_approval"


def test_approve_triggers_execution_and_worker_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "COUNCIL_ORIGINATION", True)
    # Verification runs in the spawned worker subprocess; pin host (no Docker in CI;
    # isolation backend is orthogonal, Phase 2b — the var propagates to the worker).
    monkeypatch.setenv("AIOS_APPROVED_EXECUTION_BACKEND", "host")
    workspace = tmp_path / "ws"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "tests" / "test_smoke.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (workspace / "target.txt").write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", workspace)
    runtime_root = tmp_path / "runtime"
    _client_overrides(runtime_root)
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            originated = client.post(
                "/api/v1/council/missions",
                json={
                    "goal": "Append a worker heartbeat to target.txt",
                    "allowedFiles": ["target.txt"],
                    "verificationCommands": [f"{sys.executable} -m pytest tests -q"],
                    "sessionId": "s-exec",
                },
            )
            mission_id = originated.json()["missionId"]
            assert client.get(
                f"/api/v1/council/missions/{mission_id}"
            ).json()["report"]["status"] == "awaiting_approval"

            approve = client.post("/api/v1/council/approve", json={"missionId": mission_id})
            after = client.get(f"/api/v1/council/missions/{mission_id}")
    finally:
        app.dependency_overrides.clear()

    assert approve.status_code == 200
    assert approve.json().get("execution") == "scheduled"
    # The worker acted only AFTER approval — the target now carries the edit.
    assert after.json()["report"]["status"] == "completed"
    assert "heartbeat" in (workspace / "target.txt").read_text(encoding="utf-8")


def test_reject_does_not_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_ORIGINATION", True)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "target.txt").write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", workspace)
    runtime_root = tmp_path / "runtime"
    _client_overrides(runtime_root)
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            mission_id = client.post(
                "/api/v1/council/missions",
                json={
                    "goal": "Append a worker heartbeat",
                    "allowedFiles": ["target.txt"],
                    "verificationCommands": [],
                    "sessionId": "s-reject",
                },
            ).json()["missionId"]
            rejected = client.post("/api/v1/council/reject", json={"missionId": mission_id})
            after = client.get(f"/api/v1/council/missions/{mission_id}")
    finally:
        app.dependency_overrides.clear()

    assert rejected.status_code == 200
    assert "execution" not in rejected.json()
    assert after.json()["report"]["status"] == "awaiting_approval"  # never executed
    assert (workspace / "target.txt").read_text(encoding="utf-8") == "original\n"


def test_second_decision_is_rejected_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One-shot King decision: a second approve/reject after the first is 409
    (closes the double-execute race and makes a decision final)."""
    monkeypatch.setattr(config, "COUNCIL_ORIGINATION", True)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "target.txt").write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", workspace)
    _client_overrides(tmp_path / "runtime")
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            mission_id = client.post(
                "/api/v1/council/missions",
                json={
                    "goal": "edit target",
                    "allowedFiles": ["target.txt"],
                    "verificationCommands": [],
                    "sessionId": "s-2dec",
                },
            ).json()["missionId"]
            first = client.post("/api/v1/council/approve", json={"missionId": mission_id})
            second = client.post("/api/v1/council/approve", json={"missionId": mission_id})
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 409  # decision is one-shot


def test_reject_blocks_a_later_approve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejected mission is terminal: a later approve is 409 and never executes."""
    monkeypatch.setattr(config, "COUNCIL_ORIGINATION", True)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "target.txt").write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", workspace)
    _client_overrides(tmp_path / "runtime")
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            mission_id = client.post(
                "/api/v1/council/missions",
                json={
                    "goal": "edit target",
                    "allowedFiles": ["target.txt"],
                    "verificationCommands": [],
                    "sessionId": "s-rblock",
                },
            ).json()["missionId"]
            rejected = client.post("/api/v1/council/reject", json={"missionId": mission_id})
            approved = client.post("/api/v1/council/approve", json={"missionId": mission_id})
            after = client.get(f"/api/v1/council/missions/{mission_id}")
    finally:
        app.dependency_overrides.clear()

    assert rejected.status_code == 200
    assert approved.status_code == 409  # reject was terminal
    assert after.json()["report"]["status"] == "awaiting_approval"  # never executed
    assert (workspace / "target.txt").read_text(encoding="utf-8") == "original\n"


def test_originate_rejects_glob_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_ORIGINATION", True)
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", tmp_path / "ws")
    (tmp_path / "ws").mkdir()
    _client_overrides(tmp_path / "runtime")
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            r = client.post(
                "/api/v1/council/missions",
                json={"goal": "x", "allowedFiles": ["*"], "sessionId": "s-glob"},
            )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422


def test_originate_rejects_escaping_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_ORIGINATION", True)
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", tmp_path / "ws")
    (tmp_path / "ws").mkdir()
    _client_overrides(tmp_path / "runtime")
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            escape = client.post(
                "/api/v1/council/missions",
                json={"goal": "x", "allowedFiles": ["../escape.txt"], "sessionId": "s-esc"},
            )
            empty = client.post(
                "/api/v1/council/missions",
                json={"goal": "x", "allowedFiles": [], "sessionId": "s-empty"},
            )
    finally:
        app.dependency_overrides.clear()

    assert escape.status_code == 422
    assert empty.status_code == 422
