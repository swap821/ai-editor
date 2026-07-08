from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aios import config
from aios.api.main import app, get_council_runtime_root
from aios.council.council_orchestrator import CouncilOrchestrator
from aios.council.queens.planner import CouncilMissionRequest
from aios.council.royal_decree import apply_royal_decree, draft_royal_decree


def _request(tmp_path: Path, **overrides: object) -> CouncilMissionRequest:
    data: dict[str, object] = {
        "mission_id": "m-decree",
        "goal": "Integrate a complex feature with tests",
        "workspace_root": tmp_path / "workspace",
        "allowed_files": ["src/a.py", "tests/test_a.py"],
        "allowed_tools": ["read_file", "write_file", "run_command"],
        "verification_commands": [f"{sys.executable} -m pytest tests -q"],
        "risk_level": "YELLOW",
    }
    data.update(overrides)
    return CouncilMissionRequest(**data)  # type: ignore[arg-type]


def test_royal_decree_drafts_scout_first_advisory_contracts(tmp_path: Path) -> None:
    decree = draft_royal_decree(_request(tmp_path))

    assert decree.advisory is True
    assert decree.scout_first is True
    assert decree.sequence[0]["stage"] == "scout"
    assert decree.sequence[-1]["stage"] == "king_report"
    assert decree.scout_contract.metadata["caste"] == "forager"
    assert "write_file" not in decree.scout_contract.allowed_tools
    assert decree.worker_contracts[0].metadata["caste"] == "builder"
    assert decree.worker_contracts[1].metadata["caste"] == "scout"

    metadata = decree.as_metadata()
    assert metadata["authority"].startswith("advisory only")
    assert metadata["worker_contracts"][0]["metadata"]["caste"] == "builder"


def test_royal_decree_request_is_advisory_and_builder_bounded(tmp_path: Path) -> None:
    request = apply_royal_decree(_request(tmp_path), force=True)

    assert request.metadata["royal_decree_advisory"] is True
    assert request.metadata["royal_decree_execution_gate"] == "king_approval"
    assert request.metadata["royal_decree_verifier_gate"] == "TestingQueen"
    assert request.metadata["caste"] == "builder"
    assert "write_file" in request.allowed_tools
    assert "request_approval" in request.forbidden_tools


def test_royal_decree_cannot_override_red_security_decision(tmp_path: Path) -> None:
    request = apply_royal_decree(
        _request(
            tmp_path,
            mission_id="m-decree-red",
            allowed_files=["aios/security/gateway.py"],
            verification_commands=[],
        ),
        force=True,
    )

    run = CouncilOrchestrator(runtime_root=tmp_path / "runtime").deliberate(request)

    security_verdict = next(v for v in run.verdicts if v.queen == "security")
    assert security_verdict.verdict == "deny"
    assert security_verdict.risk == "RED"
    assert run.worker_run is None
    assert run.report.risk == "RED"
    assert run.contract.metadata["royal_decree"]["advisory"] is True


def test_council_origination_complex_task_uses_royal_decree_and_waits_for_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COUNCIL_ORIGINATION", True)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "target.txt").write_text("original\n", encoding="utf-8")
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_smoke.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", workspace)
    runtime_root = tmp_path / "runtime"
    app.dependency_overrides[get_council_runtime_root] = lambda: runtime_root
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            originated = client.post(
                "/api/v1/council/missions",
                json={
                    "goal": "Integrate a complex target change with verification",
                    "allowedFiles": ["target.txt"],
                    "verificationCommands": [f"{sys.executable} -m pytest tests -q"],
                    "complexTask": True,
                    "sessionId": "royal-decree-test",
                },
            )
            mission_id = originated.json()["missionId"]
            detail = client.get(f"/api/v1/council/missions/{mission_id}")
    finally:
        app.dependency_overrides.clear()

    assert originated.status_code == 200
    payload = detail.json()
    assert payload["report"]["status"] == "awaiting_approval"
    assert payload["ledger"]["status"] == "awaiting_approval"
    assert payload["ledger"]["workers_created"] == []
    assert payload["summary"]["royalDecree"]["advisory"] is True
    assert payload["ledger"]["contract"]["metadata"]["royal_decree"]["scout_first"] is True
    assert (workspace / "target.txt").read_text(encoding="utf-8") == "original\n"
