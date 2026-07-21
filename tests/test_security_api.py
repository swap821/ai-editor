"""HTTP-level coverage for aios/api/routes/security.py — the real audit-ledger
read surface, key-rotation, and gated sandbox-reset action added 2026-07-10
to replace the previously-phantom /api/v1/security/audit,
/api/v1/security/sandbox/clear, and /api/v1/security/tokens/rotate calls the
frontend SecurityAuditPanel already shipped (and 404'd on).
"""
from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios import config
from aios.api.main import app
from aios.security.audit_logger import log_action


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client


def test_security_audit_returns_real_ledger_entries(client) -> None:
    log_action("tester", "did a green thing", "GREEN")
    log_action("tester", "did a risky thing", "RED")

    resp = client.get("/api/v1/security/audit", params={"limit": 5})

    assert resp.status_code == 200
    body = resp.json()
    assert body["entries"], "expected real ledger entries, not an empty stub"
    assert body["entries"][0]["zone"] == "RED"  # newest first
    assert "chainValid" in body
    assert "anchor" in body


def test_security_audit_filters_by_zone(client) -> None:
    log_action("tester", "green one", "GREEN")
    log_action("tester", "red one", "RED")

    resp = client.get("/api/v1/security/audit", params={"zone": "RED"})

    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert entries
    assert all(e["zone"] == "RED" for e in entries)


def test_security_audit_rejects_invalid_zone(client) -> None:
    resp = client.get("/api/v1/security/audit", params={"zone": "PURPLE"})
    assert resp.status_code == 422


def test_tokens_rotate_returns_new_key_id(client) -> None:
    resp = client.post("/api/v1/security/tokens/rotate", json={"confirm": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rotated"
    assert isinstance(body["newKeyId"], int)

    # Rotation itself is audited.
    audit_resp = client.get("/api/v1/security/audit", params={"limit": 1})
    assert "rotated audit signing key" in audit_resp.json()["entries"][0]["payload"]


def test_sandbox_clear_requires_explicit_confirm(client) -> None:
    # Sandbox deletion is RED at the universal action boundary.  The handler
    # must never receive either malformed or merely-confirmed input.
    resp = client.post("/api/v1/security/sandbox/clear", json={"confirm": False})
    assert resp.status_code == 403

    resp2 = client.post("/api/v1/security/sandbox/clear", json={})
    assert resp2.status_code == 403


def test_sandbox_clear_removes_only_scope_root_contents(client, tmp_path, monkeypatch) -> None:
    sandbox = tmp_path / "training_ground"
    sandbox.mkdir()
    (sandbox / "leftover.txt").write_text("scratch", encoding="utf-8")
    (sandbox / "subdir").mkdir()
    (sandbox / "subdir" / "nested.txt").write_text("scratch2", encoding="utf-8")

    monkeypatch.setattr(
        "aios.api.routes.security.config.SCOPE_ROOTS", (sandbox,), raising=False
    )

    resp = client.post("/api/v1/security/sandbox/clear", json={"confirm": True})

    assert resp.status_code == 403
    assert sandbox.exists()  # the root itself survives
    assert (sandbox / "leftover.txt").exists()
    assert (sandbox / "subdir" / "nested.txt").exists()


def test_sandbox_clear_refuses_project_root(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "aios.api.routes.security.config.SCOPE_ROOTS", (config.PROJECT_ROOT,), raising=False
    )

    resp = client.post("/api/v1/security/sandbox/clear", json={"confirm": True})

    assert resp.status_code == 403
