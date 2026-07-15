"""Slice 23 launcher and same-origin packaging conformance tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios import launcher


def _config(tmp_path: Path, profile: str = "production") -> launcher.LauncherConfig:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    return launcher.LauncherConfig(
        repo_root=repo,
        data_dir=tmp_path / "data",
        profile=profile,
        api_port=8000,
        gateway_port=3000,
        compose_file=repo / "docker-compose.yml",
        state_file=tmp_path / "data" / "launcher-state.json",
        log_file=tmp_path / "data" / "launcher.log",
    )


def test_production_refuses_without_docker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    monkeypatch.setenv("AIOS_API_TOKEN", "a" * 40)
    monkeypatch.setenv("AIOS_EXECUTOR_TOKEN", "b" * 40)
    monkeypatch.setenv("AIOS_GRAFANA_ADMIN_PASSWORD", "c" * 20)
    with pytest.raises(launcher.LauncherError, match="Docker is unavailable"):
        launcher._production_preflight(config)


def test_production_refuses_placeholder_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setenv("AIOS_API_TOKEN", "change-me-to-a-32-character-secret")
    monkeypatch.setenv("AIOS_EXECUTOR_TOKEN", "b" * 40)
    monkeypatch.setenv("AIOS_GRAFANA_ADMIN_PASSWORD", "c" * 20)
    with pytest.raises(launcher.LauncherError, match="AIOS_API_TOKEN"):
        launcher._production_preflight(config)


def test_production_refuses_host_execution_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setenv("AIOS_API_TOKEN", "a" * 40)
    monkeypatch.setenv("AIOS_EXECUTOR_TOKEN", "b" * 40)
    monkeypatch.setenv("AIOS_GRAFANA_ADMIN_PASSWORD", "c" * 20)
    monkeypatch.setenv("AIOS_APPROVED_EXECUTION_BACKEND", "host")
    with pytest.raises(launcher.LauncherError, match="host execution backend"):
        launcher._production_preflight(config)


def test_development_start_uses_argument_vector_and_records_pid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path, "development")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_popen(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(pid=1234)

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    assert launcher.start(config) == 0
    assert calls and calls[0][0][-2:] == ["-m", "aios"]
    assert calls[0][1].get("shell") is not True
    state = json.loads(config.state_file.read_text(encoding="utf-8"))
    assert state["mode"] == "local"
    assert state["pid"] == 1234


def test_launcher_status_does_not_claim_missing_local_process_is_running(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    config = _config(tmp_path, "development")
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.state_file.write_text(
        json.dumps({"mode": "local", "pid": 999999, "profile": "development"}),
        encoding="utf-8",
    )
    assert launcher.status(config, as_json=True) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is False


def test_same_origin_gateway_is_loopback_only_and_proxies_api() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    nginx = Path("gateway/nginx.conf").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile.frontend").read_text(encoding="utf-8")
    assert "127.0.0.1:${AIOS_GATEWAY_PORT:-3000}:8080" in compose
    assert "dockerfile: Dockerfile.frontend" in compose
    assert "proxy_pass http://aios:8000" in nginx
    assert "proxy_set_header Host gateway" in nginx
    assert "server_name localhost 127.0.0.1 gateway" in nginx
    assert "proxy_buffering off" in nginx
    assert "nginxinc/nginx-unprivileged" in dockerfile


def test_production_frontend_build_uses_relative_api_base() -> None:
    vite = Path("frontend/vite.config.js").read_text(encoding="utf-8")
    config = Path("frontend/src/config.js").read_text(encoding="utf-8")
    assert "mode === 'production' ? ''" in vite
    assert "import.meta.env.PROD ? ''" in config
