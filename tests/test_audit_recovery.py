"""Audit ledger recovery machinery — characterization tests for the uncovered
regions of the frozen security spine (key rotation, retroactive signing,
anchors, and verify_chain's failure branches).

Written after a LIVE finding (2026-07-02): the operator's real ledger reported
``valid=False, broken_at=None, reason=None`` on every /metrics scrape. The
tip-anchor was fine — the failure was verify_chain's key lookup: the
``tamper_audit_trail.key_id`` column is TEXT (so every stored key_id is a
string) while the loaded public-key map is keyed by int. The lookup missed on
every signed entry of every real database, flagging honest signatures as
"key unknown — suspicious". The anchor check coerces (``int(anchor['key_id'])``)
— the entry check did not. These tests pin the CORRECT behavior; the two
bug-reproducers run red until the (RED-gated, operator-approved) two-line fix
lands in the frozen file.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios import config
from aios.security.audit_logger import (
    compute_entry_hash,
    get_active_public_key,
    get_anchor,
    init_audit_db,
    log_action,
    retroactively_sign_unsinged_entries,
    rotate_audit_key,
    verify_chain,
)
from aios.security.gateway import Zone

_GENESIS = config.AUDIT_GENESIS_HASH


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / "audit.db"
    init_audit_db(path)
    return path


def _log(db: Path, n: int, actor: str = "tester") -> None:
    for i in range(n):
        log_action(actor, f"action-{i}", Zone.GREEN, db_path=db)


# --- THE LIVE BUG: signed chains must verify end-to-end from disk ------------

def test_fresh_ledger_signed_chain_verifies(db: Path) -> None:
    """Baseline: a ledger born on current schema (INTEGER key_id) verifies."""
    _log(db, 3)
    status = verify_chain(db_path=db)
    assert status.invalid_signatures == ()
    assert status.valid is True


def _make_pre_signing_ledger(path: Path) -> None:
    """A ledger as it existed before Phase 3: no hash_version, signature, or
    key_id columns — the shape the operator's live ledger had before the
    June-29 migration ALTER-added them (key_id as TEXT)."""
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE tamper_audit_trail ("
            "  entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  timestamp TEXT NOT NULL,"
            "  actor TEXT NOT NULL,"
            "  action_payload TEXT NOT NULL,"
            "  security_zone TEXT NOT NULL,"
            "  previous_hash TEXT NOT NULL,"
            "  current_hash TEXT NOT NULL"
            ")"
        )


def test_migrated_ledger_signed_chain_verifies(tmp_path: Path) -> None:
    """The operator's live failure, reproduced through the REAL lifecycle: a
    pre-signing ledger is migrated by init_audit_db (ALTER ... ADD COLUMN
    key_id TEXT), so signed entries land in a TEXT column and read back
    STRING key ids. Honest signatures must verify — not be flagged
    'key unknown — suspicious'. (A fresh ledger's INTEGER-affinity column
    silently re-coerces numeric text, so only the migrated shape exposes
    this; simulating with CAST is impossible by design.)"""
    db = tmp_path / "migrated.db"
    _make_pre_signing_ledger(db)
    init_audit_db(db)  # the June-29 migration path
    _log(db, 3)
    with sqlite3.connect(db) as conn:
        stored = conn.execute(
            "SELECT DISTINCT typeof(key_id) FROM tamper_audit_trail "
            "WHERE signature IS NOT NULL"
        ).fetchall()
    assert stored == [("text",)]  # the live ledger's exact storage shape
    status = verify_chain(db_path=db)
    assert status.invalid_signatures == ()
    assert status.signature_valid is True
    assert status.valid is True


def test_a_failed_verification_always_states_its_reason(db: Path) -> None:
    """valid=False with reason=None is an alarm that explains nothing — every
    failure path must name its failure mode."""
    _log(db, 2)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE tamper_audit_trail SET signature = ? WHERE entry_id = 2",
            ("ab" * 64,),  # valid hex, invalid signature
        )
    status = verify_chain(db_path=db)
    assert status.valid is False
    assert status.reason is not None


# --- key rotation -------------------------------------------------------------

def test_rotation_issues_a_new_key_and_old_entries_still_verify(db: Path) -> None:
    _log(db, 2)
    old_key = get_active_public_key(db_path=db)
    new_key_id = rotate_audit_key(db_path=db)
    _log(db, 2)

    new_key = get_active_public_key(db_path=db)
    assert new_key["key_id"] == new_key_id
    assert new_key["public_key_hex"] != old_key["public_key_hex"]

    status = verify_chain(db_path=db)
    assert status.valid is True  # pre-rotation signatures still verify
    assert status.invalid_signatures == ()


# --- retroactive signing --------------------------------------------------------

def _insert_legacy_unsigned(db: Path, count: int) -> None:
    """Simulate a pre-signing ledger: hash-chained v1 rows with no signatures."""
    with sqlite3.connect(db) as conn:
        prev = _GENESIS
        for i in range(count):
            ts = f"2026-01-01T00:00:0{i}+00:00"
            actor, payload, zone = "legacy", f"old-{i}", "GREEN"
            cur = compute_entry_hash(prev, ts, actor, payload, zone, version=1)
            conn.execute(
                "INSERT INTO tamper_audit_trail "
                "(timestamp, actor, action_payload, security_zone, previous_hash, "
                " current_hash, hash_version) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (ts, actor, payload, zone, prev, cur),
            )
            prev = cur


def test_retroactive_signing_upgrades_a_legacy_ledger(db: Path) -> None:
    _insert_legacy_unsigned(db, 3)
    before = verify_chain(db_path=db)
    assert before.unsigned_entries == 3

    signed = retroactively_sign_unsinged_entries(db_path=db)
    assert signed == 3

    after = verify_chain(db_path=db)
    assert after.unsigned_entries == 0
    assert after.invalid_signatures == ()
    assert after.valid is True


# --- anchors --------------------------------------------------------------------

def test_get_anchor_on_an_empty_ledger_returns_genesis(db: Path) -> None:
    anchor = get_anchor(db_path=db)
    assert anchor["head_hash"] == _GENESIS
    assert anchor["entry_id"] is None
    assert anchor["signature"] is None


def test_get_anchor_tracks_the_tip(db: Path) -> None:
    _log(db, 2)
    anchor = get_anchor(db_path=db)
    status = verify_chain(db_path=db)
    assert anchor["entry_id"] == 2
    assert anchor["head_hash"] == status.head_hash
    assert anchor["signature"] is not None


def test_tail_truncation_is_detected_with_its_reason(db: Path) -> None:
    _log(db, 3)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM tamper_audit_trail WHERE entry_id = 3")
    status = verify_chain(db_path=db)
    assert status.valid is False
    assert status.tip_anchor_valid is False
    assert status.reason is not None
    assert "trunc" in status.reason.lower() or "anchor" in status.reason.lower()


def test_deleted_anchor_on_a_hardened_chain_is_tampering(db: Path) -> None:
    _log(db, 2)  # v2 entries → hardened chain
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM audit_tip_anchor")
    status = verify_chain(db_path=db)
    assert status.valid is False
    assert status.tip_anchor_valid is False


def test_pure_legacy_ledger_without_anchor_is_not_flagged(db: Path) -> None:
    """v1-only chains predate the anchor feature — absence is legitimate there."""
    _insert_legacy_unsigned(db, 2)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM audit_tip_anchor")
    status = verify_chain(db_path=db)
    assert status.tip_anchor_valid is None
    assert status.valid is True  # unsigned legacy entries are counted, not fatal


# --- verify_chain failure branches ----------------------------------------------

def test_broken_linkage_names_the_entry_and_the_reason(db: Path) -> None:
    _log(db, 3)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE tamper_audit_trail SET previous_hash = ? WHERE entry_id = 2",
            ("f0" * 32,),
        )
    status = verify_chain(db_path=db)
    assert status.valid is False
    assert status.broken_at == 2
    assert "linkage" in (status.reason or "").lower()


def test_payload_tampering_is_detected_at_the_entry(db: Path) -> None:
    _log(db, 3)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE tamper_audit_trail SET action_payload = 'forged' WHERE entry_id = 2"
        )
    status = verify_chain(db_path=db)
    assert status.valid is False
    assert status.broken_at == 2
    assert "tamper" in (status.reason or "").lower()


def test_corrupt_public_key_row_flags_entries_not_crashes(db: Path) -> None:
    _log(db, 2)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE audit_keys SET public_key_hex = 'zz-not-hex'")
    status = verify_chain(db_path=db)  # key fails to load → entries suspicious
    assert status.valid is False
    assert len(status.invalid_signatures) == 2


def test_bounded_window_verification(db: Path) -> None:
    _log(db, 4)
    windowed = verify_chain(from_id=2, to_id=3, db_path=db)
    assert windowed.total_entries == 2
    assert windowed.valid is True
    assert windowed.tip_anchor_valid is None  # anchor only checked on verify-to-tip


def test_tampered_anchor_signature_is_detected(db: Path) -> None:
    _log(db, 2)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE audit_tip_anchor SET signature = ? WHERE anchor_id = 1",
            ("ab" * 64,),
        )
    status = verify_chain(db_path=db)
    assert status.valid is False
    assert status.tip_anchor_valid is False


# --- signing-key lifecycle --------------------------------------------------------

def test_operator_seed_yields_a_deterministic_key_across_ledgers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A configured AIOS_AUDIT_PRIVATE_KEY seed must produce the SAME key on
    every ledger — the property that makes signatures survive restarts."""
    monkeypatch.setenv("AIOS_AUDIT_PRIVATE_KEY", "ab" * 32)
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    init_audit_db(a)
    init_audit_db(b)
    _log(a, 1)
    _log(b, 1)
    key_a = get_active_public_key(db_path=a)
    key_b = get_active_public_key(db_path=b)
    assert key_a is not None and key_b is not None
    assert key_a["public_key_hex"] == key_b["public_key_hex"]
    assert verify_chain(db_path=a).valid is True


def test_corrupt_seed_falls_back_to_ephemeral_and_still_signs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_AUDIT_PRIVATE_KEY", "zz-not-hex")
    db = tmp_path / "corrupt-seed.db"
    init_audit_db(db)
    _log(db, 1)
    status = verify_chain(db_path=db)
    assert status.valid is True
    assert status.unsigned_entries == 0  # the fallback key still signs


def test_wrong_length_seed_falls_back_to_ephemeral(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_AUDIT_PRIVATE_KEY", "abcd")  # 2 bytes, not 32
    db = tmp_path / "short-seed.db"
    init_audit_db(db)
    _log(db, 1)
    assert verify_chain(db_path=db).valid is True


# --- key export -----------------------------------------------------------------

def test_active_public_key_is_exported_for_external_verification(db: Path) -> None:
    _log(db, 1)
    key = get_active_public_key(db_path=db)
    assert key["public_key_hex"]
    assert int(key["key_id"]) >= 1


def test_active_key_export_is_none_before_any_signing(db: Path) -> None:
    assert get_active_public_key(db_path=db) is None  # keys register on first signed write
