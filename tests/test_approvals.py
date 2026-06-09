from __future__ import annotations

import sqlite3

import pytest

from aios.core.approvals import ApprovalError, ApprovalStore


def test_approval_token_is_exact_session_bound_and_single_use() -> None:
    store = ApprovalStore(timeout_ms=1000)
    token = store.issue("edit", {"filepath": "x.txt", "content": "x"}, "s1")

    with pytest.raises(ApprovalError, match="different session"):
        store.consume(token, "s2")
    with pytest.raises(ApprovalError, match="already used"):
        store.consume(token, "s1")


def test_approval_token_expires() -> None:
    now = [10.0]
    store = ApprovalStore(timeout_ms=100, clock=lambda: now[0])
    token = store.issue("command", {"command": "echo ok"}, "s1")
    now[0] = 10.2

    with pytest.raises(ApprovalError, match="expired"):
        store.consume(token, "s1")


def test_redeemed_grant_expires() -> None:
    now = [10.0]
    store = ApprovalStore(timeout_ms=100, clock=lambda: now[0])
    token = store.issue("command", {"command": "echo ok"}, "s1")
    store.redeem(token, "s1")
    assert len(store.grants("s1")) == 1

    now[0] = 10.2
    assert store.grants("s1") == []


def test_durable_token_survives_store_restart_and_is_single_use(tmp_path) -> None:
    path = tmp_path / "approvals.sqlite"
    first = ApprovalStore(timeout_ms=1000, db_path=path)
    token = first.issue("edit", {"filepath": "x.txt", "content": "x"}, "s1")

    second = ApprovalStore(timeout_ms=1000, db_path=path)
    assert second.consume(token, "s1").payload["filepath"] == "x.txt"
    with pytest.raises(ApprovalError, match="already used"):
        first.consume(token, "s1")


def test_durable_store_never_persists_raw_bearer_token_or_session_id(tmp_path) -> None:
    path = tmp_path / "approvals.sqlite"
    store = ApprovalStore(timeout_ms=1000, db_path=path)
    session_id = "private-session-id"
    token = store.issue("command", {"command": "echo ok"}, session_id)

    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT token_digest FROM approval_pending").fetchone()

    assert row is not None
    assert row[0] != token
    assert token not in path.read_bytes().decode("latin-1")
    assert session_id not in path.read_bytes().decode("latin-1")


def test_durable_grant_survives_store_restart_and_expires(tmp_path) -> None:
    now = [10.0]
    path = tmp_path / "approvals.sqlite"
    first = ApprovalStore(timeout_ms=100, clock=lambda: now[0], db_path=path)
    token = first.issue("command", {"command": "echo ok"}, "s1")
    first.redeem(token, "s1")

    second = ApprovalStore(timeout_ms=100, clock=lambda: now[0], db_path=path)
    assert len(second.grants("s1")) == 1
    now[0] = 10.2
    assert second.grants("s1") == []


def test_durable_store_migrates_legacy_raw_session_ids(tmp_path) -> None:
    path = tmp_path / "approvals.sqlite"
    ApprovalStore(timeout_ms=1000, db_path=path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO approval_pending "
            "(token_digest, action_type, payload_json, session_id, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("digest", "command", '{"command":"echo ok"}', "legacy-session", 9999999999),
        )

    ApprovalStore(timeout_ms=1000, db_path=path)

    assert b"legacy-session" not in path.read_bytes()


def test_durable_store_refuses_payload_containing_a_secret(tmp_path) -> None:
    store = ApprovalStore(timeout_ms=1000, db_path=tmp_path / "approvals.sqlite")
    secret = "sk-" + "a" * 40

    with pytest.raises(ApprovalError, match="credential-like data"):
        store.issue("create", {"filepath": "secret.txt", "content": secret}, "s1")
