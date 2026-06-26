"""Prometheus `/metrics` endpoint tests.

Covers P1-5: the observability surface re-emits DevelopmentTracker data plus
approval, earned-autonomy, and audit-chain counters.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import aios
import pytest
from fastapi.testclient import TestClient

from aios.api.main import (
    app,
    get_approval_store,
    get_autonomy,
    get_development_tracker,
    _METRICS,
)
from aios.core.approvals import ApprovalStore
from aios.core.autonomy import AutonomyLedger
from aios.memory.development import DevelopmentTracker
from aios.security import audit_logger as audit_mod
from aios.security.audit_logger import init_audit_db, log_action
from aios.security.gateway import Zone


@pytest.fixture(autouse=True)
def _reset_collector():
    """Give every metrics test a fresh collector/registry."""
    _METRICS.clear()
    yield


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    """TestClient with isolated approval/memory/audit databases."""
    app.dependency_overrides[get_approval_store] = lambda: ApprovalStore(
        db_path=tmp_path / "approvals.db"
    )
    app.dependency_overrides[get_development_tracker] = lambda: DevelopmentTracker(
        db_path=tmp_path / "memory.db"
    )
    app.dependency_overrides[get_autonomy] = lambda: AutonomyLedger(
        db_path=tmp_path / "memory.db"
    )
    monkeypatch.setattr("aios.config.AUDIT_DB_PATH", tmp_path / "audit.db")
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "aios_tasks_total" in body
    assert "aios_approvals_total" in body
    assert "aios_earned_autonomy_grants_total" in body
    assert "aios_audit_chain_valid" in body
    assert "aios_audit_verify_failures_total" in body


def test_metrics_reflect_development_summary(client: TestClient, tmp_path: Path) -> None:
    tracker = DevelopmentTracker(db_path=tmp_path / "memory.db")
    tracker.record("test task", "verified_success", blocked_actions=1)

    response = client.get("/metrics")
    body = response.text
    assert "aios_tasks_total 1.0" in body
    assert "aios_blocked_actions_total 1.0" in body
    assert "aios_verified_success_rate 1.0" in body
    assert "aios_verification_coverage 1.0" in body


def test_metrics_reflect_approval_and_autonomy_counts(
    client: TestClient, tmp_path: Path
) -> None:
    # One approval issued and redeemed.
    store = ApprovalStore(db_path=tmp_path / "approvals.db")
    token = store.issue("edit", {"path": "training_ground/a.py"}, "session-1")
    store.redeem(token, "session-1")

    # One earned-autonomy signature (min_successes=1 so a single success earns).
    app.dependency_overrides[get_autonomy] = lambda: AutonomyLedger(
        db_path=tmp_path / "memory.db", min_successes=1
    )
    ledger = app.dependency_overrides[get_autonomy]()
    ledger.record_outcome("edit_file", "training_ground/a.py", success=True)

    response = client.get("/metrics")
    body = response.text
    assert "aios_approvals_total 1.0" in body
    assert "aios_earned_autonomy_grants_total 1.0" in body


def test_audit_verify_increments_failure_counter_and_sets_gauge(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    audit_db = tmp_path / "audit.db"
    init_audit_db(audit_db)
    log_action("planner", "step one", Zone.GREEN, db_path=audit_db)
    log_action("executor", "step two", Zone.YELLOW, db_path=audit_db)
    raw = sqlite3.connect(str(audit_db))
    raw.execute(
        "UPDATE tamper_audit_trail SET action_payload = ? WHERE entry_id = ?",
        ("MALICIOUSLY ALTERED", 2),
    )
    raw.commit()
    raw.close()

    def _verify_with_temp_db(*, from_id: int = 1, to_id: int | None = None, db_path=None):
        return audit_mod.verify_chain(from_id=from_id, to_id=to_id, db_path=audit_db)

    monkeypatch.setattr("aios.api.main.verify_chain", _verify_with_temp_db)
    monkeypatch.setattr("aios.core.metrics.verify_chain", _verify_with_temp_db)

    verify_resp = client.get("/api/v1/audit/verify")
    assert verify_resp.json()["valid"] is False

    metrics_resp = client.get("/metrics")
    body = metrics_resp.text
    assert "aios_audit_verify_failures_total 1.0" in body
    assert "aios_audit_chain_valid 0.0" in body


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == aios.__version__


def test_middleware_records_http_request_metrics(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    metrics_response = client.get("/metrics")
    body = metrics_response.text
    assert 'aios_http_requests_total{method="GET",route="/health",status_code="200"} 1.0' in body
    assert 'aios_http_request_duration_seconds_count{method="GET",route="/health"} 1.0' in body


def test_metrics_endpoint_is_not_self_counted(client: TestClient) -> None:
    client.get("/metrics")
    response = client.get("/metrics")
    body = response.text
    # The scrape itself should not add a /metrics sample line.
    assert 'route="/metrics"' not in body
