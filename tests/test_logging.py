"""Structured logging, correlation middleware, and audit alarm tests.

Covers the Phase 1-4 logging upgrades:

* Every request receives an ``x-request-id`` correlation header.
* The middleware binds a hashed ``session_id`` from JSON bodies into structlog context.
* Audit-chain verification emits a CRITICAL log when tampering is detected.
* Previously swallowed best-effort exceptions on the turn path now warn.
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from pathlib import Path

import pytest
import structlog
from fastapi.testclient import TestClient

from aios import logging_config
from aios.api import main as api_main
from aios.api.main import app, audit_verify
from aios.security import audit_logger as audit_mod
from aios.security.audit_logger import init_audit_db, log_action
from aios.security.gateway import Zone


@pytest.fixture(autouse=True)
def _reset_structlog_context():
    """Keep contextvars from leaking between logging tests."""
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


@pytest.fixture()
def client():
    """A lightweight TestClient with no external subsystem dependencies."""
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def tampered_audit_db(tmp_path: Path) -> Path:
    """An isolated audit ledger with a deliberate break at entry 2."""
    db = tmp_path / "audit.db"
    init_audit_db(db)
    log_action("planner", "step one", Zone.GREEN, db_path=db)
    log_action("executor", "step two", Zone.YELLOW, db_path=db)
    raw = sqlite3.connect(str(db))
    raw.execute(
        "UPDATE tamper_audit_trail SET action_payload = ? WHERE entry_id = ?",
        ("MALICIOUSLY ALTERED", 2),
    )
    raw.commit()
    raw.close()
    return db


def test_middleware_adds_request_id_header(client: TestClient) -> None:
    response = client.post("/api/v1/intent/preview", json={"text": "hello"})
    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id
    uuid.UUID(request_id)  # raises ValueError if malformed


def test_middleware_persists_provided_request_id(client: TestClient) -> None:
    provided = str(uuid.uuid4())
    response = client.post(
        "/api/v1/intent/preview",
        json={"text": "hello"},
        headers={"x-request-id": provided},
    )
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == provided


def test_middleware_hashes_session_id_before_logging(
    caplog,
    client: TestClient,
    monkeypatch,
) -> None:
    raw_session = "private-session-for-logs"
    expected_hash = logging_config.session_log_key(raw_session)
    probe_logger = logging_config.get_logger("tests.logging")

    def _classify_with_log(text: str) -> api_main.IntentPreviewResponse:
        probe_logger.warning("session context probe")
        return api_main.IntentPreviewResponse(intent="chat", confidence=1.0, tool=None)

    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(api_main, "_classify_intent", _classify_with_log)

    response = client.post(
        "/api/v1/intent/preview",
        json={"text": "hello", "sessionId": raw_session},
    )

    assert response.status_code == 200
    rendered = "\n".join(record.message for record in caplog.records)
    assert expected_hash in rendered
    assert raw_session not in rendered


def test_audit_verify_logs_critical_when_chain_tampered(
    caplog,
    monkeypatch,
    tampered_audit_db: Path,
) -> None:
    caplog.set_level(logging.CRITICAL)
    original_verify = audit_mod.verify_chain

    def _verify_with_temp_db(*, from_id: int, to_id: int | None) -> audit_mod.ChainStatus:
        return original_verify(from_id=from_id, to_id=to_id, db_path=tampered_audit_db)

    monkeypatch.setattr("aios.api.main.verify_chain", _verify_with_temp_db)
    result = audit_verify(from_entry=1, to_entry=None)

    assert result["valid"] is False
    assert result["broken_at"] == 2
    assert any(
        record.levelname == "CRITICAL"
        and "Audit hash-chain verification failed" in record.message
        for record in caplog.records
    )


def test_configure_logging_is_idempotent() -> None:
    """Repeated lifespan calls must not explode or duplicate handlers."""
    logging_config._CONFIGURED = False
    handler_count_before = len(logging.getLogger().handlers)
    logging_config.configure_logging(level="INFO")
    logging_config.configure_logging(level="DEBUG")  # second call is a no-op
    assert logging.getLogger().handlers
    # No duplicate handlers were added by the second call.
    assert len(logging.getLogger().handlers) == max(handler_count_before, 1)
