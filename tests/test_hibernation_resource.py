from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aios import config
from aios.api.main import app
from aios.api.routes import sovereignty
from aios.runtime.budget_guard import BudgetGuard
from aios.runtime.contracts import MissionContract
from aios.runtime.hibernation import HibernationManager, HibernationPolicyError


def _contract(tmp_path: Path) -> MissionContract:
    return MissionContract(
        mission_id="m-resource",
        goal="reason with cloud only if budget allows",
        worker_type="scout",
        created_by="test",
        workspace_root=str(tmp_path),
        allowed_files=["x.txt"],
        allowed_tools=["request_plan"],
        metadata={
            "model_policy": {
                "mode": "hybrid",
                "allow_cloud": True,
                "max_cloud_calls": 5,
                "max_tokens_per_request": 2000,
                "max_tokens_total": 8000,
            }
        },
    )


def test_resource_modes_block_cloud_when_conserving_or_hibernating(tmp_path: Path) -> None:
    contract = _contract(tmp_path)

    normal = BudgetGuard(mode="normal").check_cloud_request(
        contract, estimated_tokens=100, estimated_cost=0.01
    )
    conservation = BudgetGuard(mode="conservation").check_cloud_request(
        contract, estimated_tokens=100, estimated_cost=0.01
    )
    hibernation = BudgetGuard(mode="hibernation").check_cloud_request(
        contract, estimated_tokens=100, estimated_cost=0.01
    )

    assert normal.allowed is True
    assert conservation.allowed is False
    assert conservation.reason == "resource mode conservation blocks cloud"
    assert hibernation.allowed is False
    assert hibernation.reason == "resource mode hibernation blocks cloud"


def test_hibernation_cannot_perform_cloud_calls_or_writes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Local project\n", encoding="utf-8")

    class FakeCompactor:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def compact(self, dry_run: bool = True) -> dict:
            self.calls.append(dry_run)
            if not dry_run:
                raise AssertionError("hibernation attempted a write")
            return {"dry_run": dry_run, "semantic_unverified_chat_removed": 0}

    class FakePheromones:
        decay_called = False

        def query(self, *args, **kwargs):  # noqa: ANN001
            return [object(), object()]

        def decay_all(self) -> int:
            self.decay_called = True
            raise AssertionError("hibernation attempted pheromone mutation")

    compactor = FakeCompactor()
    pheromones = FakePheromones()
    manager = HibernationManager(
        repo_root=repo,
        compactor=compactor,
        pheromone_store=pheromones,
        budget_guard=BudgetGuard(mode="normal"),
    )

    report = manager.run()

    assert compactor.calls == [True]
    assert pheromones.decay_called is False
    assert report.local_only is True
    assert report.writes_performed is False
    assert report.cloud_calls == 0
    assert report.pheromones["signals_seen"] == 2
    assert report.project_passport["activation"] == "proposal/evidence"
    assert report.resource_status["mode"] == "hibernation"

    with pytest.raises(HibernationPolicyError, match="cloud"):
        manager.run(allow_cloud=True)
    with pytest.raises(HibernationPolicyError, match="writes"):
        manager.run(allow_writes=True)


def test_resource_status_api_reflects_configured_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "RESOURCE_MODE", "conservation")
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        response = client.get("/api/v1/resource/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "conservation"
    assert payload["cloud_allowed"] is False
    assert payload["source"] == "process_default"


def test_hibernation_api_rejects_cloud_and_reports_local_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCompactor:
        def compact(self, dry_run: bool = True) -> dict:
            assert dry_run is True
            return {"dry_run": True}

    monkeypatch.setattr("aios.api.main.get_compactor", lambda: FakeCompactor())
    monkeypatch.setattr(config, "PHEROMONE_ENABLED", False)
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        denied = client.post("/api/v1/hibernation/run", json={"allowCloud": True})
        allowed = client.post(
            "/api/v1/hibernation/run",
            json={"rebuildRepoMap": False},
        )
        status = client.get("/api/v1/hibernation/status")

    assert denied.status_code == 400
    assert "cloud" in denied.json()["detail"]
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["localOnly"] is True
    assert payload["writesPerformed"] is False
    assert payload["cloudCalls"] == 0
    assert payload["projectPassport"]["skipped"] is True
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["localOnly"] is True
    assert status_payload["writesAllowed"] is False
    assert status_payload["cloudAllowed"] is False
    assert status_payload["lastRun"]["cloudCalls"] == 0
    assert status_payload["lastRun"]["projectPassport"]["skipped"] is True


def test_hibernation_status_is_read_only_policy_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sovereignty, "_LAST_HIBERNATION_REPORT", None)
    monkeypatch.setattr(config, "RESOURCE_MODE", "normal")

    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        response = client.get("/api/v1/hibernation/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configuredMode"] == "normal"
    assert payload["hibernationMode"] == "hibernation"
    assert payload["localOnly"] is True
    assert payload["writesAllowed"] is False
    assert payload["cloudAllowed"] is False
    assert payload["lastRun"] is None
