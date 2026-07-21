"""HTTP-level coverage for the real /api/v1/system/config and
/api/v1/system/restart endpoints added 2026-07-10 to replace the previously-
phantom routes SettingsPanel.jsx already called (and 404'd on).
"""
from __future__ import annotations

import subprocess
import sys
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app
from aios.api.routes.system import _reexec_after_delay


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client


def test_get_system_config_returns_defaults_when_unset(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aios.api.routes.system._SETTINGS_PATH", tmp_path / "system_settings.json"
    )
    monkeypatch.delenv("AIOS_EARNED_AUTONOMY", raising=False)
    monkeypatch.delenv("AIOS_LLM_MODEL", raising=False)
    monkeypatch.delenv("AIOS_BEDROCK_MODEL", raising=False)
    monkeypatch.delenv("AIOS_GEMINI_MODEL", raising=False)

    resp = client.get("/api/v1/system/config")

    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "Ollama"
    assert body["autonomy"] is True


def test_post_system_config_persists_and_get_reflects_it(client, tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "system_settings.json"
    monkeypatch.setattr("aios.api.routes.system._SETTINGS_PATH", settings_path)
    monkeypatch.delenv("AIOS_EARNED_AUTONOMY", raising=False)
    monkeypatch.delenv("AIOS_LLM_MODEL", raising=False)
    monkeypatch.delenv("AIOS_BEDROCK_MODEL", raising=False)
    monkeypatch.delenv("AIOS_GEMINI_MODEL", raising=False)

    resp = client.post(
        "/api/v1/system/config",
        json={"provider": "Gemini", "autonomy": False},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"
    assert settings_path.exists()

    resp2 = client.get("/api/v1/system/config")
    body = resp2.json()
    assert body["provider"] == "Gemini"
    assert body["autonomy"] is False


def test_post_system_config_rejects_missing_fields(client) -> None:
    resp = client.post("/api/v1/system/config", json={"provider": "Gemini"})
    assert resp.status_code == 422


def test_restart_requires_explicit_confirm(client) -> None:
    resp = client.post("/api/v1/system/restart", json={"confirm": False})
    assert resp.status_code == 403

    resp2 = client.post("/api/v1/system/restart", json={})
    assert resp2.status_code == 403


def test_restart_is_blocked_before_reexec(client, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "aios.api.routes.system._reexec_after_delay",
        lambda delay: calls.append(delay),
    )

    resp = client.post("/api/v1/system/restart", json={"confirm": True})

    assert resp.status_code == 403
    assert calls == []


def test_reexec_argv_reconstruction_is_actually_importable(monkeypatch) -> None:
    """Regression for the 2026-07-10 adversarial audit: the original
    [sys.executable] + sys.argv reconstruction re-invoked as a direct script
    (python aios/__main__.py ...), not `-m aios`, which sets sys.path[0] to
    aios/ itself and breaks `from aios import config` with
    ModuleNotFoundError -- verified as a real, reproducible crash, not a
    theoretical one. This test does NOT mock the argv-construction logic
    (only os.execv itself, since calling the real one would replace this
    test process) -- it captures the exact argv _reexec_after_delay would
    hand to execv, then runs those exact argv as a real subprocess to prove
    the reconstruction is genuinely valid and importable, not just
    plausible-looking."""
    captured: list[list[str]] = []
    monkeypatch.setattr("os.execv", lambda path, argv: captured.append(list(argv)))
    monkeypatch.setattr("sys.argv", ["<ignored-under-broken-argv0>", "--help"])

    _reexec_after_delay(0.0)

    assert captured, "expected os.execv to have been called"
    argv = captured[0]
    assert argv[0] == sys.executable
    assert argv[1:3] == ["-m", "aios"], (
        "must re-invoke with an explicit -m aios, not sys.argv[0] "
        "(which degrades to a bare script path under python -m launch)"
    )
    assert argv[3:] == ["--help"], "sys.argv[1:] (the real CLI flags) must be preserved"

    # Prove it's not just plausible -- actually run it as a real subprocess.
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, (
        f"reconstructed argv failed to run: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "ModuleNotFoundError" not in result.stderr

    # Anchor the bug this fixes: the OLD reconstruction (sys.argv[0] as a
    # literal script path) really does crash, confirming this isn't a
    # hypothetical regression test for a hypothetical bug.
    broken_argv = [sys.executable, "aios/__main__.py", "--help"]
    broken_result = subprocess.run(broken_argv, capture_output=True, text=True, timeout=30)
    assert broken_result.returncode != 0
    assert "ModuleNotFoundError" in broken_result.stderr
