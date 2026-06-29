"""Phase 3 — audit ledger tamper-evidence hardening.

Two properties on top of the existing Ed25519 + hash-chain ledger:
  1. a collision-resistant, VERSIONED chain preimage (v2 = canonical JSON), with v1
     kept so pre-existing chains still verify;
  2. a signed tip-anchor so tail-truncation (lopping the latest entries) is detected.
Strengthen-only; the runtime frozen-spine refusal is untouched.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios import config
from aios.security.audit_logger import (
    compute_entry_hash,
    init_audit_db,
    log_action,
    verify_chain,
)
from aios.security.gateway import Zone

_GENESIS = config.AUDIT_GENESIS_HASH


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / "audit.db"
    init_audit_db(path)
    return path


# --- collision-resistant preimage (versioned) -------------------------------

def test_v1_preimage_has_the_field_boundary_collision() -> None:
    # Documents WHY v2 exists: the legacy concat is ambiguous at field boundaries.
    a = compute_entry_hash(_GENESIS, "ts", "ab", "c", "GREEN", version=1)
    b = compute_entry_hash(_GENESIS, "ts", "a", "bc", "GREEN", version=1)
    assert a == b


def test_v2_preimage_resists_field_boundary_collision() -> None:
    a = compute_entry_hash(_GENESIS, "ts", "ab", "c", "GREEN", version=2)
    b = compute_entry_hash(_GENESIS, "ts", "a", "bc", "GREEN", version=2)
    assert a != b


def test_compute_entry_hash_defaults_to_v2() -> None:
    assert compute_entry_hash(_GENESIS, "ts", "ab", "c", "GREEN") == compute_entry_hash(
        _GENESIS, "ts", "ab", "c", "GREEN", version=2
    )
    # ...and remains deterministic + zone-sensitive (preserves existing contract).
    assert compute_entry_hash(_GENESIS, "ts", "a", "p", "GREEN") != compute_entry_hash(
        _GENESIS, "ts", "a", "p", "RED"
    )


# --- versioned verify (a legacy v1 entry still verifies) --------------------

def test_legacy_v1_entry_still_verifies(db: Path) -> None:
    # Simulate a pre-migration entry: written with the v1 preimage + hash_version=1,
    # unsigned. verify_chain must recompute it under its own version and pass.
    ts = "2026-01-01T00:00:00+00:00"
    chash = compute_entry_hash(_GENESIS, ts, "legacy", "payload", "GREEN", version=1)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO tamper_audit_trail (timestamp, actor, action_payload, "
        "security_zone, current_hash, previous_hash, hash_version) "
        "VALUES (?, ?, ?, ?, ?, ?, 1)",
        (ts, "legacy", "payload", "GREEN", chash, _GENESIS),
    )
    conn.commit()
    conn.close()
    status = verify_chain(db_path=db, verify_signatures=False)
    assert status.valid is True
    assert status.total_entries == 1


# --- tail-truncation detection (signed tip-anchor) --------------------------

def test_intact_chain_has_valid_tip_anchor(db: Path) -> None:
    log_action("actor", "a1", Zone.GREEN, db_path=db)
    log_action("actor", "a2", Zone.GREEN, db_path=db)
    status = verify_chain(db_path=db)
    assert status.valid is True
    assert status.tip_anchor_valid is True


def test_tail_truncation_is_detected(db: Path) -> None:
    log_action("actor", "a1", Zone.GREEN, db_path=db)
    entry2 = log_action("actor", "a2", Zone.GREEN, db_path=db)
    # Lop off the latest entry WITHOUT re-signing the anchor.
    conn = sqlite3.connect(str(db))
    conn.execute("DELETE FROM tamper_audit_trail WHERE entry_id = ?", (entry2.entry_id,))
    conn.commit()
    conn.close()
    status = verify_chain(db_path=db)
    assert status.valid is False
    assert status.tip_anchor_valid is False


def test_truncation_to_empty_is_detected(db: Path) -> None:
    log_action("actor", "a1", Zone.GREEN, db_path=db)
    conn = sqlite3.connect(str(db))
    conn.execute("DELETE FROM tamper_audit_trail")
    conn.commit()
    conn.close()
    status = verify_chain(db_path=db)
    # The anchor proves an entry existed -> truncation-to-empty, distinct from a
    # never-written DB.
    assert status.valid is False
    assert status.tip_anchor_valid is False


def test_truncation_with_anchor_deletion_is_detected(db: Path) -> None:
    # The adversarial-review MEDIUM: a DB-write attacker deletes the latest entry AND
    # the anchor row, hoping verify reads "legacy, no anchor". A v2 entry remains, so
    # the missing anchor on a hardened chain is fail-closed -> detected.
    log_action("actor", "a1", Zone.GREEN, db_path=db)
    log_action("actor", "a2", Zone.GREEN, db_path=db)
    entry3 = log_action("actor", "a3", Zone.GREEN, db_path=db)
    conn = sqlite3.connect(str(db))
    conn.execute("DELETE FROM tamper_audit_trail WHERE entry_id = ?", (entry3.entry_id,))
    conn.execute("DELETE FROM audit_tip_anchor")
    conn.commit()
    conn.close()
    status = verify_chain(db_path=db)
    assert status.valid is False
    assert status.tip_anchor_valid is False


def test_pure_legacy_v1_chain_without_anchor_is_not_flagged(db: Path) -> None:
    # Back-compat guard: a pre-Phase-3 chain (v1-only, no anchor) must NOT be flagged
    # as anchor-deletion — only v2 (hardened) chains expect an anchor.
    ts = "2026-01-01T00:00:00+00:00"
    chash = compute_entry_hash(_GENESIS, ts, "legacy", "p", "GREEN", version=1)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO tamper_audit_trail (timestamp, actor, action_payload, "
        "security_zone, current_hash, previous_hash, hash_version) "
        "VALUES (?, ?, ?, ?, ?, ?, 1)",
        (ts, "legacy", "p", "GREEN", chash, _GENESIS),
    )
    conn.commit()
    conn.close()
    status = verify_chain(db_path=db, verify_signatures=False)
    assert status.valid is True
    assert status.tip_anchor_valid is None


def test_anchor_tamper_is_detected(db: Path) -> None:
    log_action("actor", "a1", Zone.GREEN, db_path=db)
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE audit_tip_anchor SET tip_hash = ?", ("deadbeef" * 8,))
    conn.commit()
    conn.close()
    status = verify_chain(db_path=db)
    assert status.valid is False
    assert status.tip_anchor_valid is False


def test_fresh_db_has_no_anchor_and_is_valid(db: Path) -> None:
    status = verify_chain(db_path=db)
    assert status.valid is True
    assert status.tip_anchor_valid is None  # never written -> no anchor (not a truncation)


def test_pre_signature_db_is_migrated_so_guarded_writes_do_not_brick(tmp_path: Path) -> None:
    # A PRE-SIGNATURE ledger (created before Ed25519 support): core columns +
    # hash_version, but NO signature/key_id. init_audit_db must ALTER-add them, else
    # every guarded write fail-closes on "no column named signature" — bricking all
    # supervised actions. (Surfaced by the live supervised-loop proof on the real DB.)
    db = tmp_path / "legacy_audit.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE tamper_audit_trail ("
        "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, "
        "actor TEXT NOT NULL, action_payload TEXT NOT NULL, security_zone TEXT NOT NULL, "
        "current_hash TEXT NOT NULL, previous_hash TEXT NOT NULL, "
        "hash_version INTEGER NOT NULL DEFAULT 1)"
    )
    ts = "2026-01-01T00:00:00+00:00"
    chash = compute_entry_hash(_GENESIS, ts, "legacy", "payload", "GREEN", version=1)
    conn.execute(
        "INSERT INTO tamper_audit_trail (timestamp, actor, action_payload, "
        "security_zone, current_hash, previous_hash, hash_version) "
        "VALUES (?, ?, ?, ?, ?, ?, 1)",
        (ts, "legacy", "payload", "GREEN", chash, _GENESIS),
    )
    conn.commit()
    conn.close()

    init_audit_db(db)  # migration must add the missing columns

    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tamper_audit_trail)")}
    conn.close()
    assert "signature" in cols
    assert "key_id" in cols

    # A guarded write now succeeds instead of raising AuditError...
    entry = log_action("actor", "guarded-action", Zone.GREEN, db_path=db)
    assert entry.entry_id is not None
    # ...and the chain (legacy unsigned row + the new row) still verifies.
    status = verify_chain(db_path=db, verify_signatures=False)
    assert status.valid is True
    assert status.total_entries == 2


def test_append_re_anchors_after_a_deletion(db: Path) -> None:
    log_action("actor", "a1", Zone.GREEN, db_path=db)
    entry2 = log_action("actor", "a2", Zone.GREEN, db_path=db)
    conn = sqlite3.connect(str(db))
    conn.execute("DELETE FROM tamper_audit_trail WHERE entry_id = ?", (entry2.entry_id,))
    conn.commit()
    conn.close()
    log_action("actor", "a3", Zone.GREEN, db_path=db)  # re-anchors to the new tip
    status = verify_chain(db_path=db)
    assert status.valid is True
    assert status.tip_anchor_valid is True
