"""Unit coverage for the server-side SessionManager (OWASP A07 mitigation).

This is live security code — it backs the API's httpOnly-cookie session auth — but
its core logic (create / validate / invalidate / upgrade / expiry / cleanup) was
unit-untested (~46%). These characterization tests pin the real behavior, especially
the session-fixation-prevention path.
"""
from __future__ import annotations

import hashlib
import time

from aios.core.session_manager import Session, SessionManager


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def test_is_expired_boundaries() -> None:
    fresh = Session("id", "h", created_at=0.0, last_accessed=time.time())
    assert fresh.is_expired(3600) is False
    stale = Session("id", "h", created_at=0.0, last_accessed=time.time() - 10_000)
    assert stale.is_expired(3600) is True


def test_create_and_validate_roundtrip() -> None:
    manager = SessionManager()
    raw = manager.create_session({"user": "x"})
    session = manager.validate_session(_hash(raw))
    assert session is not None
    assert session.data["user"] == "x"
    assert isinstance(session.data["csrf_token"], str)
    assert len(session.data["csrf_token"]) >= 32
    assert session.session_id == raw  # raw kept only in memory


def test_ensure_csrf_token_repairs_legacy_session() -> None:
    manager = SessionManager()
    raw = manager.create_session()
    cookie_hash = _hash(raw)
    del manager._sessions[cookie_hash].data["csrf_token"]

    token = manager.ensure_csrf_token(cookie_hash)

    assert isinstance(token, str)
    assert len(token) >= 32
    assert manager.validate_session(cookie_hash).data["csrf_token"] == token


def test_validate_rejects_missing_and_unknown() -> None:
    manager = SessionManager()
    assert manager.validate_session(None) is None
    assert manager.validate_session("") is None
    assert manager.validate_session("deadbeef") is None


def test_validate_rejects_expired() -> None:
    manager = SessionManager(max_age=1)
    raw = manager.create_session()
    manager._sessions[_hash(raw)].last_accessed = time.time() - 100
    assert manager.validate_session(_hash(raw)) is None


def test_validate_refreshes_last_accessed() -> None:
    manager = SessionManager()
    raw = manager.create_session()
    manager._sessions[_hash(raw)].last_accessed = time.time() - 50
    before = manager._sessions[_hash(raw)].last_accessed
    assert manager.validate_session(_hash(raw)) is not None
    assert manager._sessions[_hash(raw)].last_accessed > before


def test_invalidate_removes_and_is_noop_on_missing() -> None:
    manager = SessionManager()
    raw = manager.create_session()
    manager.invalidate_session(_hash(raw))
    assert manager.validate_session(_hash(raw)) is None
    manager.invalidate_session(None)  # no-op, no raise
    manager.invalidate_session("unknown")  # no-op, no raise


def test_upgrade_session_prevents_fixation_and_carries_data() -> None:
    manager = SessionManager()
    raw = manager.create_session({"role": "user"})
    old_hash = _hash(raw)
    new_raw = manager.upgrade_session(old_hash)

    assert new_raw != raw  # a fresh id is minted
    assert manager.validate_session(old_hash) is None  # the old id is destroyed
    upgraded = manager.validate_session(_hash(new_raw))
    assert upgraded is not None
    assert upgraded.data["role"] == "user"  # data carried across


def test_upgrade_unknown_creates_a_fresh_session() -> None:
    manager = SessionManager()
    new_raw = manager.upgrade_session("nonexistent-hash")
    assert manager.validate_session(_hash(new_raw)) is not None


def test_session_count_and_cleanup_purges_expired() -> None:
    manager = SessionManager(max_age=1, cleanup_interval=0)
    manager.create_session()
    manager.create_session()
    assert manager.session_count() >= 1

    for session in manager._sessions.values():
        session.last_accessed = time.time() - 100  # expire them all
    manager._last_cleanup = 0.0  # bypass the cleanup throttle
    assert manager.session_count() == 0


def test_durable_store_validates_cookie_hash_after_restart(tmp_path) -> None:
    store = tmp_path / "sessions.db"
    first = SessionManager(store_path=store)
    raw = first.create_session({"user": "operator"})
    cookie_hash = _hash(raw)

    second = SessionManager(store_path=store)
    session = second.validate_session(cookie_hash)

    assert session is not None
    assert session.session_hash == cookie_hash
    assert session.session_id == ""  # raw id is intentionally not persisted
    assert session.data["user"] == "operator"
    assert isinstance(session.data["csrf_token"], str)
    assert raw not in store.read_bytes().decode("latin1", errors="ignore")


def test_durable_invalidate_removes_session_across_restarts(tmp_path) -> None:
    store = tmp_path / "sessions.db"
    first = SessionManager(store_path=store)
    raw = first.create_session()
    cookie_hash = _hash(raw)

    second = SessionManager(store_path=store)
    second.invalidate_session(cookie_hash)

    third = SessionManager(store_path=store)
    assert third.validate_session(cookie_hash) is None


def test_durable_upgrade_carries_data_and_destroys_old_hash(tmp_path) -> None:
    store = tmp_path / "sessions.db"
    first = SessionManager(store_path=store)
    raw = first.create_session({"role": "user"})
    old_hash = _hash(raw)

    second = SessionManager(store_path=store)
    new_raw = second.upgrade_session(old_hash)
    new_hash = _hash(new_raw)

    third = SessionManager(store_path=store)
    assert third.validate_session(old_hash) is None
    upgraded = third.validate_session(new_hash)
    assert upgraded is not None
    assert upgraded.data["role"] == "user"
    assert isinstance(upgraded.data["csrf_token"], str)
