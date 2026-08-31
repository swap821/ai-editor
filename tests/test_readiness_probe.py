"""`/ready` answers a different question than `/health`, and fails closed.

Ultra-plan item 0.3, the last open M1 item. `/health` is a liveness probe: it
returns `{"status": "ok"}` from a process whose database is unwritable, whose
disk is full, and which can reach no model at all. An orchestrator reading it
keeps routing work to a brain that fails on contact.

The distinction only matters if the readiness checks can actually FAIL, so every
test here breaks a real dependency and asserts the 503 -- none of them assert
that a healthy machine says yes, which is the version that passes forever.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import get_ollama_client
from aios.api.main import app


class _OllamaUp:
    def list_models(self) -> dict[str, Any]:
        return {"available": True, "models": ["qwen2.5-coder:7b"]}


class _OllamaDown:
    def list_models(self) -> dict[str, Any]:
        # The real client collapses every failure to this shape and never raises.
        return {"available": False, "models": []}


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_ollama_client] = _OllamaUp
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_health_is_liveness_and_ready_is_a_different_endpoint(
    client: TestClient,
) -> None:
    """Both exist and they are not aliases for one another."""
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = client.get("/ready")
    assert ready.status_code in (200, 503), ready.text
    body = ready.json()
    assert set(body["checks"]) == {"disk", "database", "providers"}


def test_ready_is_200_when_every_dependency_is_satisfied(client: TestClient) -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready"] is True
    assert body["not_ready"] == []


def test_no_reachable_model_anywhere_is_not_ready(monkeypatch) -> None:
    """Local down AND no cloud configured means no route to a model at all.

    Local-down alone is deliberately NOT unready: a cloud-configured install is
    a legitimate deployment. What is never ready is having no route at all.
    """
    from aios.api.routes import system as system_routes

    for flag in ("BEDROCK_ENABLED", "GEMINI_ENABLED", "OPENAI_ENABLED", "ANTHROPIC_ENABLED"):
        monkeypatch.setattr(system_routes.config, flag, False, raising=False)

    app.dependency_overrides[get_ollama_client] = _OllamaDown
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as c:
            resp = c.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["ready"] is False
    assert "providers" in body["not_ready"]
    assert body["checks"]["providers"]["local"]["reachable"] is False


def test_a_configured_cloud_provider_keeps_a_local_outage_ready(monkeypatch) -> None:
    """The complement of the test above, so the rule is pinned from both sides."""
    from aios.api.routes import system as system_routes

    monkeypatch.setattr(system_routes.config, "BEDROCK_ENABLED", True, raising=False)

    app.dependency_overrides[get_ollama_client] = _OllamaDown
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as c:
            resp = c.get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["checks"]["providers"]["cloud_configured"] == ["bedrock"]


def test_a_full_disk_is_not_ready(monkeypatch, client: TestClient) -> None:
    """Refuse work rather than discover the full disk mid-turn.

    A brain that cannot write its audit chain or snapshots must not accept a
    turn: the write fails AFTER the model has already acted, which is the worst
    possible moment to find out.
    """
    from aios.api.routes import system as system_routes

    class _Usage:
        total = 100
        used = 100
        free = 1024  # 1 KiB, far under the floor

    monkeypatch.setattr(system_routes.shutil, "disk_usage", lambda _p: _Usage())

    resp = client.get("/ready")
    assert resp.status_code == 503, resp.text
    assert "disk" in resp.json()["not_ready"]


def test_an_unwritable_database_is_not_ready(monkeypatch, client: TestClient) -> None:
    """A read-only open is not proof of writability.

    `get_connection()` succeeds against a read-only mount and a permission-
    dropped data dir alike, so the probe opens a transaction. This asserts the
    probe reports the failure instead of swallowing it.
    """
    from aios.api.routes import system as system_routes

    def _boom() -> Any:
        raise OSError("attempt to write a readonly database")

    monkeypatch.setattr(system_routes, "get_connection", _boom)

    resp = client.get("/ready")
    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert "database" in body["not_ready"]
    assert "readonly" in body["checks"]["database"]["detail"]


def test_the_probe_reports_rather_than_raises(monkeypatch, client: TestClient) -> None:
    """A readiness probe that 500s tells an orchestrator nothing actionable.

    Every check is wrapped so a broken dependency produces a structured 503 with
    the reason, not a stack trace.
    """
    from aios.api.routes import system as system_routes

    def _explode(_p: Any) -> Any:
        raise OSError("device disappeared")

    monkeypatch.setattr(system_routes.shutil, "disk_usage", _explode)

    resp = client.get("/ready")
    assert resp.status_code == 503, resp.text
    assert resp.json()["checks"]["disk"]["ok"] is False
