"""Tests for sovereign roadmap Wave 2B write/mutation API endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aios import config
from aios.api.main import app


_LOOPBACK = ("127.0.0.1", 12345)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "")
    monkeypatch.setattr(config, "TRUST_PROXY_HEADERS", False)
    with TestClient(app, raise_server_exceptions=False, client=_LOOPBACK) as c:
        yield c


# ── Pheromone Endpoints ──────────────────────────────────────────────────────


def test_pheromone_deposit(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PHEROMONE_ENABLED", True)
    monkeypatch.setattr(config, "PHEROMONE_DB", tmp_path / "ph.db")
    monkeypatch.setattr(config, "PHEROMONE_LAMBDA_DECAY", 0.02)
    monkeypatch.setattr(config, "PHEROMONE_FLOOR", 0.01)

    resp = client.post("/api/v1/pheromones/deposit", json={
        "ptype": "success-trail",
        "resource": "src/main.py",
        "depositor": "worker-1",
        "strength": 0.8,
        "payload": {"note": "completed"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "pheromone_id" in data
    assert data["pheromone_id"] >= 1


def test_pheromone_deposit_invalid_type(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PHEROMONE_ENABLED", True)
    monkeypatch.setattr(config, "PHEROMONE_DB", tmp_path / "ph.db")

    resp = client.post("/api/v1/pheromones/deposit", json={
        "ptype": "not-a-real-type",
        "resource": "x.py",
        "depositor": "w",
    })
    assert resp.status_code == 400


def test_pheromone_reinforce(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PHEROMONE_ENABLED", True)
    monkeypatch.setattr(config, "PHEROMONE_DB", tmp_path / "ph.db")
    monkeypatch.setattr(config, "PHEROMONE_LAMBDA_DECAY", 0.02)
    monkeypatch.setattr(config, "PHEROMONE_FLOOR", 0.01)

    deposit_resp = client.post("/api/v1/pheromones/deposit", json={
        "ptype": "file-lock",
        "resource": "a.py",
        "depositor": "w",
    })
    pid = deposit_resp.json()["pheromone_id"]

    resp = client.post("/api/v1/pheromones/reinforce", json={
        "pheromoneId": pid,
        "boost": 0.3,
    })
    assert resp.status_code == 200
    assert resp.json()["reinforced"] is True


def test_pheromone_decay(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PHEROMONE_ENABLED", True)
    monkeypatch.setattr(config, "PHEROMONE_DB", tmp_path / "ph.db")
    monkeypatch.setattr(config, "PHEROMONE_LAMBDA_DECAY", 0.02)
    monkeypatch.setattr(config, "PHEROMONE_FLOOR", 0.01)

    resp = client.post("/api/v1/pheromones/decay")
    assert resp.status_code == 200
    assert "pruned" in resp.json()


def test_pheromone_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "PHEROMONE_ENABLED", False)
    resp = client.post("/api/v1/pheromones/deposit", json={
        "ptype": "file-lock", "resource": "x", "depositor": "w",
    })
    assert resp.status_code == 404


# ── Live Surface Endpoints ───────────────────────────────────────────────────


def test_live_surface_emit(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LIVE_SURFACE", True)
    monkeypatch.setattr(config, "LIVE_SURFACE_DB", tmp_path / "ls.db")

    resp = client.post("/api/v1/runtime/surface/emit", json={
        "stype": "worker-active",
        "resource": "src/app.py",
        "workerId": "worker-7",
        "ttlSeconds": 60,
        "payload": {"progress": 0.5},
    })
    assert resp.status_code == 200
    assert resp.json()["signal_id"] >= 1


def test_live_surface_emit_invalid_type(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LIVE_SURFACE", True)
    monkeypatch.setattr(config, "LIVE_SURFACE_DB", tmp_path / "ls.db")

    resp = client.post("/api/v1/runtime/surface/emit", json={
        "stype": "bogus-type",
        "resource": "x",
        "workerId": "w",
    })
    assert resp.status_code == 400


def test_live_surface_revoke(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LIVE_SURFACE", True)
    monkeypatch.setattr(config, "LIVE_SURFACE_DB", tmp_path / "ls.db")

    emit_resp = client.post("/api/v1/runtime/surface/emit", json={
        "stype": "file-lock",
        "resource": "x.py",
        "workerId": "w1",
    })
    signal_id = emit_resp.json()["signal_id"]

    resp = client.delete(f"/api/v1/runtime/surface/{signal_id}")
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True


def test_live_surface_revoke_not_found(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LIVE_SURFACE", True)
    monkeypatch.setattr(config, "LIVE_SURFACE_DB", tmp_path / "ls.db")

    resp = client.delete("/api/v1/runtime/surface/99999")
    assert resp.status_code == 404


def test_live_surface_sweep(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LIVE_SURFACE", True)
    monkeypatch.setattr(config, "LIVE_SURFACE_DB", tmp_path / "ls.db")

    resp = client.post("/api/v1/runtime/surface/sweep")
    assert resp.status_code == 200
    assert "swept" in resp.json()


def test_live_surface_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "LIVE_SURFACE", False)
    resp = client.post("/api/v1/runtime/surface/emit", json={
        "stype": "file-lock", "resource": "x", "workerId": "w",
    })
    assert resp.status_code == 404


# ── Rollback Registry Endpoints ──────────────────────────────────────────────


def test_rollback_register(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROLLBACK_REGISTRY", True)
    monkeypatch.setattr(config, "ROLLBACK_REGISTRY_DB", tmp_path / "rr.db")
    monkeypatch.setattr(config, "ROLLBACK_RETENTION_DAYS", 30)

    resp = client.post("/api/v1/runtime/rollbacks/register", json={
        "snapshotId": "snap-001",
        "missionId": "mission-42",
        "workspaceRoot": "/tmp/ws",
        "filesCovered": ["a.py", "b.py"],
        "metadata": {"reason": "pre-deploy"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["registered"] is True
    assert data["snapshot_id"] == "snap-001"


def test_rollback_prune(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROLLBACK_REGISTRY", True)
    monkeypatch.setattr(config, "ROLLBACK_REGISTRY_DB", tmp_path / "rr.db")
    monkeypatch.setattr(config, "ROLLBACK_RETENTION_DAYS", 30)

    resp = client.post("/api/v1/runtime/rollbacks/prune")
    assert resp.status_code == 200
    assert "pruned" in resp.json()


def test_rollback_register_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "ROLLBACK_REGISTRY", False)
    resp = client.post("/api/v1/runtime/rollbacks/register", json={
        "snapshotId": "s", "missionId": "m", "workspaceRoot": "/w",
    })
    assert resp.status_code == 404


# ── Audit Anchor History ─────────────────────────────────────────────────────


def test_audit_anchor_history(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIT_ANCHOR_API", True)
    monkeypatch.setattr("aios.audit_anchor._DEFAULT_DATA_DIR", str(tmp_path))

    resp = client.get("/api/v1/audit/anchor/history?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert data["count"] == 0


def test_audit_anchor_history_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "AUDIT_ANCHOR_API", False)
    resp = client.get("/api/v1/audit/anchor/history")
    assert resp.status_code == 404


# ── Policy Engine Write Endpoints ────────────────────────────────────────────


def test_policy_vote(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "POLICY_ENGINE", True)
    monkeypatch.setattr(config, "POLICY_DB", tmp_path / "policy.db")

    propose_resp = client.post("/api/v1/policy/propose", json={
        "constraint": "All workers MUST log actions",
        "proposedBy": "security-queen",
    })
    assert propose_resp.status_code == 200
    policy_id = propose_resp.json()["policy_id"]

    resp = client.post(f"/api/v1/policy/{policy_id}/vote", json={
        "queen": "critique",
        "approve": True,
        "reason": "good constraint",
    })
    assert resp.status_code == 200
    assert resp.json()["voted"] is True


def test_policy_vote_duplicate(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "POLICY_ENGINE", True)
    monkeypatch.setattr(config, "POLICY_DB", tmp_path / "policy.db")

    propose_resp = client.post("/api/v1/policy/propose", json={
        "constraint": "Workers MUST use snapshots",
        "proposedBy": "planner-queen",
    })
    policy_id = propose_resp.json()["policy_id"]

    client.post(f"/api/v1/policy/{policy_id}/vote", json={
        "queen": "security", "approve": True,
    })
    resp = client.post(f"/api/v1/policy/{policy_id}/vote", json={
        "queen": "security", "approve": False,
    })
    assert resp.status_code == 400


def test_policy_enact(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "POLICY_ENGINE", True)
    monkeypatch.setattr(config, "POLICY_DB", tmp_path / "policy.db")

    propose_resp = client.post("/api/v1/policy/propose", json={
        "constraint": "Workers MUST verify output",
        "proposedBy": "testing-queen",
    })
    policy_id = propose_resp.json()["policy_id"]

    for queen in ("security", "critique", "planner"):
        client.post(f"/api/v1/policy/{policy_id}/vote", json={
            "queen": queen, "approve": True,
        })

    resp = client.post(f"/api/v1/policy/{policy_id}/enact", json={
        "requiredApprovals": 3,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["enacted"] is True
    assert data["policy_id"] == policy_id


def test_policy_enact_insufficient_votes(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "POLICY_ENGINE", True)
    monkeypatch.setattr(config, "POLICY_DB", tmp_path / "policy.db")

    propose_resp = client.post("/api/v1/policy/propose", json={
        "constraint": "Workers MUST audit trail",
        "proposedBy": "memory-queen",
    })
    policy_id = propose_resp.json()["policy_id"]

    client.post(f"/api/v1/policy/{policy_id}/vote", json={
        "queen": "security", "approve": True,
    })

    resp = client.post(f"/api/v1/policy/{policy_id}/enact", json={
        "requiredApprovals": 3,
    })
    assert resp.status_code == 400


def test_policy_suspend(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "POLICY_ENGINE", True)
    monkeypatch.setattr(config, "POLICY_DB", tmp_path / "policy.db")

    propose_resp = client.post("/api/v1/policy/propose", json={
        "constraint": "Workers MUST run tests",
        "proposedBy": "testing-queen",
    })
    policy_id = propose_resp.json()["policy_id"]

    for queen in ("security", "critique", "planner"):
        client.post(f"/api/v1/policy/{policy_id}/vote", json={
            "queen": queen, "approve": True,
        })
    client.post(f"/api/v1/policy/{policy_id}/enact", json={"requiredApprovals": 3})

    resp = client.post(f"/api/v1/policy/{policy_id}/suspend", json={
        "suspendedBy": "security-queen",
    })
    assert resp.status_code == 200
    assert resp.json()["suspended"] is True


def test_policy_chain(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "POLICY_ENGINE", True)
    monkeypatch.setattr(config, "POLICY_DB", tmp_path / "policy.db")

    client.post("/api/v1/policy/propose", json={
        "constraint": "Workers MUST sign output",
        "proposedBy": "security-queen",
    })

    resp = client.get("/api/v1/policy/chain")
    assert resp.status_code == 200
    data = resp.json()
    assert "policies" in data
    assert len(data["policies"]) >= 1


def test_policy_endpoints_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "POLICY_ENGINE", False)
    assert client.post("/api/v1/policy/test-id/vote", json={
        "queen": "x", "approve": True,
    }).status_code == 404
    assert client.post("/api/v1/policy/test-id/enact", json={}).status_code == 404
    assert client.post("/api/v1/policy/test-id/suspend", json={
        "suspendedBy": "x",
    }).status_code == 404
    assert client.get("/api/v1/policy/chain").status_code == 404


# ── Queen Services Management ────────────────────────────────────────────────


def test_queen_service_start_stop(client, monkeypatch):
    monkeypatch.setattr(config, "QUEEN_SERVICES", True)

    from aios.council.queen_service import QUEEN_SERVICES, register_service, unregister_service
    from tests.test_queen_service import DummyQueenService

    svc = DummyQueenService()
    register_service(svc)
    try:
        resp = client.post("/api/v1/council/services/dummy/start")
        assert resp.status_code == 200
        assert resp.json()["started"] is True

        resp = client.post("/api/v1/council/services/dummy/stop")
        assert resp.status_code == 200
        assert resp.json()["stopped"] is True
    finally:
        unregister_service("dummy")


def test_queen_service_not_found(client, monkeypatch):
    monkeypatch.setattr(config, "QUEEN_SERVICES", True)

    from aios.council.queen_service import QUEEN_SERVICES
    QUEEN_SERVICES.clear()

    resp = client.post("/api/v1/council/services/nonexistent/start")
    assert resp.status_code == 404


def test_queen_service_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "QUEEN_SERVICES", False)
    resp = client.post("/api/v1/council/services/any/start")
    assert resp.status_code == 404
