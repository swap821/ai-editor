"""Adversarial proof for the universal ordinary-route ActionBroker boundary."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app
from aios.api.routes import system


_NO_AUTO = {"X-AIOS-No-Auto-Capability": "1"}


@pytest.fixture
def client():
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client


def test_yellow_route_challenges_before_mutation_and_binds_exact_payload(
    client, monkeypatch, tmp_path: Path
) -> None:
    settings = tmp_path / "system-settings.json"
    monkeypatch.setattr(system, "_SETTINGS_PATH", settings)
    payload = {"provider": "Ollama", "autonomy": False}

    first = client.post("/api/v1/system/config", json=payload, headers=_NO_AUTO)

    assert first.status_code == 428
    token = first.json()["detail"]["approvalToken"]
    assert not settings.exists(), "capability issuance must not run the route handler"

    altered = client.post(
        "/api/v1/system/config",
        json={"provider": "Bedrock", "autonomy": False},
        headers={"X-AIOS-Capability": token},
    )
    assert altered.status_code == 403
    assert not settings.exists(), "altered payload must fail before mutation"

    consumed = client.post(
        "/api/v1/system/config",
        json=payload,
        headers={"X-AIOS-Capability": token},
    )
    assert consumed.status_code == 200
    assert settings.exists()


def test_red_ordinary_route_blocks_before_restart_callable(client, monkeypatch) -> None:
    called = False

    def should_not_run(_delay: float) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(system, "_reexec_after_delay", should_not_run)
    response = client.post(
        "/api/v1/system/restart",
        json={"confirm": True},
        headers=_NO_AUTO,
    )

    assert response.status_code == 403
    assert called is False


def test_yellow_capability_replay_is_single_use(client) -> None:
    payload = {"provider": "Ollama", "autonomy": True}
    first = client.post("/api/v1/system/config", json=payload, headers=_NO_AUTO)
    token = first.json()["detail"]["approvalToken"]
    headers = {"X-AIOS-Capability": token}

    assert client.post("/api/v1/system/config", json=payload, headers=headers).status_code == 200
    assert client.post("/api/v1/system/config", json=payload, headers=headers).status_code == 403
