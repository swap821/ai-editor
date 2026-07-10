"""HTTP-level coverage for the real /api/v1/system/config and
/api/v1/system/restart endpoints added 2026-07-10 to replace the previously-
phantom routes SettingsPanel.jsx already called (and 404'd on).
"""
from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client


def test_get_system_config_returns_defaults_when_unset(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aios.api.routes.system._SETTINGS_PATH", tmp_path / "system_settings.json"
    )

    resp = client.get("/api/v1/system/config")

    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "Ollama"
    assert body["autonomy"] is True
    assert body["theme"] == "Superbrain"


def test_post_system_config_persists_and_get_reflects_it(client, tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "system_settings.json"
    monkeypatch.setattr("aios.api.routes.system._SETTINGS_PATH", settings_path)

    resp = client.post(
        "/api/v1/system/config",
        json={"provider": "Gemini", "autonomy": False, "theme": "Dark"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"
    assert settings_path.exists()

    resp2 = client.get("/api/v1/system/config")
    body = resp2.json()
    assert body["provider"] == "Gemini"
    assert body["autonomy"] is False
    assert body["theme"] == "Dark"


def test_post_system_config_rejects_missing_fields(client) -> None:
    resp = client.post("/api/v1/system/config", json={"provider": "Gemini"})
    assert resp.status_code == 422


def test_restart_requires_explicit_confirm(client) -> None:
    resp = client.post("/api/v1/system/restart", json={"confirm": False})
    assert resp.status_code == 422

    resp2 = client.post("/api/v1/system/restart", json={})
    assert resp2.status_code == 422


def test_restart_confirmed_schedules_reexec_without_blocking_response(client, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "aios.api.routes.system._reexec_after_delay",
        lambda delay: calls.append(delay),
    )

    resp = client.post("/api/v1/system/restart", json={"confirm": True})

    assert resp.status_code == 200
    assert resp.json()["status"] == "restarting"
    # The background thread races the test process; give it a moment.
    import time

    for _ in range(20):
        if calls:
            break
        time.sleep(0.05)
    assert calls, "expected the restart thread to invoke _reexec_after_delay"
