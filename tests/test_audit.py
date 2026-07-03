"""Hash-chain audit logger tests — integrity, tamper detection, redaction.

Covers the blueprint's "altering any audit entry breaks verify_chain()" case,
the genesis linkage, deterministic hashing, the fail-closed invalid-zone guard,
and the no-secret-persistence guarantee.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from aios import config
from aios.security.audit_logger import (
    AuditError,
    compute_entry_hash,
    init_audit_db,
    log_action,
    verify_chain,
)
from aios.security.gateway import Zone


@pytest.fixture()
def audit_db(tmp_path: Path) -> Path:
    """An initialised, isolated audit database."""
    path = tmp_path / "audit.db"
    init_audit_db(path)
    return path


def test_chain_links_from_genesis_and_verifies(audit_db: Path) -> None:
    e1 = log_action("planner", "read config", Zone.GREEN, db_path=audit_db)
    e2 = log_action("executor", "pip install flask", Zone.YELLOW, db_path=audit_db)
    e3 = log_action("human", "approve deletion", Zone.RED, db_path=audit_db)

    assert e1.previous_hash == config.AUDIT_GENESIS_HASH
    assert e2.previous_hash == e1.current_hash
    assert e3.previous_hash == e2.current_hash

    status = verify_chain(db_path=audit_db)
    assert status.valid is True
    assert status.total_entries == 3
    assert status.head_hash == e3.current_hash


def test_tampering_breaks_chain_at_offending_entry(audit_db: Path) -> None:
    log_action("planner", "step one", Zone.GREEN, db_path=audit_db)
    log_action("executor", "step two", Zone.YELLOW, db_path=audit_db)
    log_action("executor", "step three", Zone.GREEN, db_path=audit_db)

    # Tamper with entry 2's payload directly in the database.
    raw = sqlite3.connect(str(audit_db))
    raw.execute(
        "UPDATE tamper_audit_trail SET action_payload = ? WHERE entry_id = ?",
        ("MALICIOUSLY ALTERED", 2),
    )
    raw.commit()
    raw.close()

    status = verify_chain(db_path=audit_db)
    assert status.valid is False
    assert status.broken_at == 2


def test_hash_is_deterministic_and_64_hex() -> None:
    h1 = compute_entry_hash("0" * 64, "2026-01-01T00:00:00+00:00", "actor", "payload", "GREEN")
    h2 = compute_entry_hash("0" * 64, "2026-01-01T00:00:00+00:00", "actor", "payload", "GREEN")
    assert h1 == h2
    assert len(h1) == 64
    # A single-field change must produce a different hash.
    h3 = compute_entry_hash("0" * 64, "2026-01-01T00:00:00+00:00", "actor", "payload", "RED")
    assert h3 != h1


def test_secret_is_redacted_before_persistence(audit_db: Path) -> None:
    aws_key = "AKIA" + "IOSFODNN7EXAMPLE"
    entry = log_action(
        "executor",
        f"deploy with key {aws_key} now",
        Zone.YELLOW,
        db_path=audit_db,
    )
    assert entry.redacted is True

    raw = sqlite3.connect(str(audit_db))
    stored = raw.execute(
        "SELECT action_payload FROM tamper_audit_trail WHERE entry_id = ?",
        (entry.entry_id,),
    ).fetchone()[0]
    raw.close()

    assert aws_key not in stored
    assert "REDACTED" in stored
    # The chain remains valid because the hash was computed over redacted text.
    assert verify_chain(db_path=audit_db).valid is True


def test_invalid_zone_raises_fail_closed(audit_db: Path) -> None:
    with pytest.raises(AuditError):
        log_action("actor", "payload", "PURPLE", db_path=audit_db)


def test_empty_chain_is_valid(audit_db: Path) -> None:
    status = verify_chain(db_path=audit_db)
    assert status.valid is True
    assert status.total_entries == 0
    assert status.head_hash == config.AUDIT_GENESIS_HASH


def test_concurrent_appends_keep_one_valid_chain(audit_db: Path) -> None:
    errors: list[Exception] = []

    def append_many(actor: str) -> None:
        try:
            for i in range(20):
                log_action(actor, f"event {i}", Zone.GREEN, db_path=audit_db)
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [threading.Thread(target=append_many, args=(f"worker-{i}",)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    status = verify_chain(db_path=audit_db)
    assert status.valid is True
    assert status.total_entries == 80
