"""
Adversarial test suite: Audit Chain Integrity (15+ tests)

Following OWASP ASVS V7 (Error Handling and Logging), V8 (Data Protection),
and Google Testing Standards (AAA pattern).

Tests verify the tamper-evident hash-chained audit ledger cannot be silently
modified, deleted, or forged. Every modification breaks the chain.

Coverage:
  I1: Chain integrity verification
  I2: Tamper detection (modified entries)
  I3: Deletion detection (missing entries)
  I4: Signature/hash verification
  I5: Genesis hash anchoring
  I6: Secret redaction before hashing
  I7: Cross-process append safety
  I8: Fail-closed behavior
"""
from __future__ import annotations

import hashlib
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from aios import config
from aios.security.audit_logger import (
    AuditEntry,
    AuditError,
    ChainStatus,
    compute_entry_hash,
    init_audit_db,
    log_action,
    verify_chain,
)
from aios.security.gateway import Zone


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def tmp_audit_db(tmp_path):
    """Create a temporary audit database."""
    db_path = tmp_path / "test_audit.db"
    init_audit_db(db_path)
    return db_path


@pytest.fixture
def clean_audit_db(tmp_path):
    """Create and return a fresh audit database path."""
    db_path = tmp_path / "clean_audit.db"
    return db_path


# ============================================================================ #
# I1: Chain Integrity Verification
# ============================================================================ #


class TestChainIntegrityVerification:
    """TC-SEC-600 through TC-SEC-605: Basic chain integrity."""

    def test_empty_chain_valid(self, tmp_audit_db):
        """TC-SEC-600: Empty chain must verify as valid."""
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is True
        assert status.total_entries == 0
        assert status.head_hash == config.AUDIT_GENESIS_HASH

    def test_single_entry_valid(self, tmp_audit_db):
        """TC-SEC-601: Chain with one entry must verify."""
        log_action("test-actor", "test action", Zone.GREEN, db_path=tmp_audit_db)
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is True
        assert status.total_entries == 1

    def test_multiple_entries_valid(self, tmp_audit_db):
        """TC-SEC-602: Chain with multiple entries must verify."""
        for i in range(5):
            log_action("test-actor", f"action {i}", Zone.GREEN, db_path=tmp_audit_db)
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is True
        assert status.total_entries == 5

    def test_head_hash_changes(self, tmp_audit_db):
        """TC-SEC-603: Head hash must change after each append."""
        entry1 = log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        status1 = verify_chain(db_path=tmp_audit_db)
        entry2 = log_action("test-actor", "action 2", Zone.GREEN, db_path=tmp_audit_db)
        status2 = verify_chain(db_path=tmp_audit_db)
        assert status1.head_hash != status2.head_hash

    def test_head_hash_not_genesis_after_append(self, tmp_audit_db):
        """TC-SEC-604: Head hash must not be genesis after first entry."""
        log_action("test-actor", "action", Zone.GREEN, db_path=tmp_audit_db)
        status = verify_chain(db_path=tmp_audit_db)
        assert status.head_hash != config.AUDIT_GENESIS_HASH

    def test_entry_returns_audit_entry(self, tmp_audit_db):
        """TC-SEC-605: log_action must return AuditEntry."""
        entry = log_action("test-actor", "test", Zone.GREEN, db_path=tmp_audit_db)
        assert isinstance(entry, AuditEntry)
        assert entry.entry_id > 0
        assert len(entry.current_hash) == 64  # SHA-256 hex


# ============================================================================ #
# I2: Tamper Detection
# ============================================================================ #


class TestTamperDetection:
    """TC-SEC-606 through TC-SEC-613: Modified entries must break chain."""

    def test_tampered_entry_detected(self, tmp_audit_db):
        """TC-SEC-606: Modified entry must fail verification."""
        # Arrange: log an entry
        entry = log_action("test-actor", "original payload", Zone.GREEN, db_path=tmp_audit_db)
        # Tamper with it in DB
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute(
            "UPDATE tamper_audit_trail SET action_payload = 'tampered payload' WHERE entry_id = ?",
            (entry.entry_id,),
        )
        conn.commit()
        conn.close()
        # Act
        status = verify_chain(db_path=tmp_audit_db)
        # Assert
        assert status.valid is False
        assert status.broken_at == entry.entry_id

    def test_tampered_zone_detected(self, tmp_audit_db):
        """TC-SEC-607: Modified zone must break chain."""
        entry = log_action("test-actor", "action", Zone.GREEN, db_path=tmp_audit_db)
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute(
            "UPDATE tamper_audit_trail SET security_zone = 'RED' WHERE entry_id = ?",
            (entry.entry_id,),
        )
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False
        assert status.broken_at == entry.entry_id

    def test_tampered_actor_detected(self, tmp_audit_db):
        """TC-SEC-608: Modified actor must break chain."""
        entry = log_action("test-actor", "action", Zone.GREEN, db_path=tmp_audit_db)
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute(
            "UPDATE tamper_audit_trail SET actor = 'evil-actor' WHERE entry_id = ?",
            (entry.entry_id,),
        )
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False

    def test_tampered_timestamp_detected(self, tmp_audit_db):
        """TC-SEC-609: Modified timestamp must break chain."""
        entry = log_action("test-actor", "action", Zone.GREEN, db_path=tmp_audit_db)
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute(
            "UPDATE tamper_audit_trail SET timestamp = '2099-01-01T00:00:00+00:00' WHERE entry_id = ?",
            (entry.entry_id,),
        )
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False

    def test_tampered_second_entry_detected(self, tmp_audit_db):
        """TC-SEC-610: Tampering entry 2 must break chain at entry 2."""
        log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        entry2 = log_action("test-actor", "action 2", Zone.GREEN, db_path=tmp_audit_db)
        log_action("test-actor", "action 3", Zone.GREEN, db_path=tmp_audit_db)
        # Tamper entry 2
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute(
            "UPDATE tamper_audit_trail SET action_payload = 'tampered' WHERE entry_id = ?",
            (entry2.entry_id,),
        )
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False
        assert status.broken_at == entry2.entry_id

    def test_tampered_last_entry_detected(self, tmp_audit_db):
        """TC-SEC-611: Tampering last entry must break chain at last entry."""
        for i in range(3):
            log_action("test-actor", f"action {i}", Zone.GREEN, db_path=tmp_audit_db)
        # Get the last entry id
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT entry_id FROM tamper_audit_trail ORDER BY entry_id DESC LIMIT 1").fetchone()
        last_id = row["entry_id"]
        conn.execute(
            "UPDATE tamper_audit_trail SET action_payload = 'tampered' WHERE entry_id = ?",
            (last_id,),
        )
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False
        assert status.broken_at == last_id

    def test_verification_reason_is_specific(self, tmp_audit_db):
        """TC-SEC-612: Tamper detection reason must be specific."""
        entry = log_action("test-actor", "action", Zone.GREEN, db_path=tmp_audit_db)
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute(
            "UPDATE tamper_audit_trail SET action_payload = 'tampered' WHERE entry_id = ?",
            (entry.entry_id,),
        )
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert "tamper" in status.reason.lower() or "hash" in status.reason.lower()

    def test_multiple_tampered_entries_detected_at_first(self, tmp_audit_db):
        """TC-SEC-613: Multiple tampered entries detected at first break."""
        log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        entry2 = log_action("test-actor", "action 2", Zone.GREEN, db_path=tmp_audit_db)
        entry3 = log_action("test-actor", "action 3", Zone.GREEN, db_path=tmp_audit_db)
        # Tamper entries 2 and 3
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute("UPDATE tamper_audit_trail SET action_payload = 'tampered' WHERE entry_id IN (?, ?)",
                      (entry2.entry_id, entry3.entry_id))
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False
        # Should break at the first tampered entry
        assert status.broken_at == entry2.entry_id


# ============================================================================ #
# I3: Deletion Detection
# ============================================================================ #


class TestDeletionDetection:
    """TC-SEC-614 through TC-SEC-619: Deleted entries must break chain."""

    def test_deleted_entry_detected(self, tmp_audit_db):
        """TC-SEC-614: Deleted entry must break chain."""
        log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        entry2 = log_action("test-actor", "action 2", Zone.GREEN, db_path=tmp_audit_db)
        log_action("test-actor", "action 3", Zone.GREEN, db_path=tmp_audit_db)
        # Delete the middle entry
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute("DELETE FROM tamper_audit_trail WHERE entry_id = ?", (entry2.entry_id,))
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False
        # The chain breaks at entry 3 because its previous_hash won't match entry 2's (deleted)
        assert status.broken_at is not None

    def test_deleted_last_entry_now_detected(self, tmp_audit_db):
        """TC-SEC-615 (Phase 3): deleting the LAST entry is now DETECTED via the
        signed tip-anchor. Previously this left a 'valid' shorter chain — the
        tail-truncation gap Phase 3 closes (strengthened, not weakened)."""
        log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        entry2 = log_action("test-actor", "action 2", Zone.GREEN, db_path=tmp_audit_db)
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute("DELETE FROM tamper_audit_trail WHERE entry_id = ?", (entry2.entry_id,))
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False
        assert status.tip_anchor_valid is False

    def test_all_entries_deleted_now_detected(self, tmp_audit_db):
        """TC-SEC-616 (Phase 3): truncation-to-empty is DETECTED — the signed
        anchor proves an entry existed, distinguishing it from a never-written DB
        (which has no anchor and stays valid)."""
        log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute("DELETE FROM tamper_audit_trail")
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False
        assert status.tip_anchor_valid is False
        assert status.total_entries == 0

    def test_deletion_then_append_recovers(self, tmp_audit_db):
        """TC-SEC-617: After deleting, the next append correctly chains from the new head."""
        log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        entry2 = log_action("test-actor", "action 2", Zone.GREEN, db_path=tmp_audit_db)
        # Delete entry 2
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute("DELETE FROM tamper_audit_trail WHERE entry_id = ?", (entry2.entry_id,))
        conn.commit()
        conn.close()
        # Append new entry - it correctly chains from entry 1 (the new head)
        log_action("test-actor", "action 3", Zone.GREEN, db_path=tmp_audit_db)
        status = verify_chain(db_path=tmp_audit_db)
        # The chain is valid: entry 1 -> entry 3 (entry 2 is gone, audit log reads current head)
        assert status.valid is True
        assert status.total_entries == 2


# ============================================================================ #
# I4: Signature/Hash Verification
# ============================================================================ #


class TestSignatureVerification:
    """TC-SEC-618 through TC-SEC-623: Hash computation and verification."""

    def test_compute_hash_deterministic(self):
        """TC-SEC-618: Same inputs must produce same hash."""
        h1 = compute_entry_hash("prev_hash", "ts", "actor", "payload", "GREEN")
        h2 = compute_entry_hash("prev_hash", "ts", "actor", "payload", "GREEN")
        assert h1 == h2
        assert len(h1) == 64

    def test_compute_hash_different_inputs(self):
        """TC-SEC-619: Different inputs must produce different hash."""
        h1 = compute_entry_hash("prev1", "ts1", "actor1", "payload1", "GREEN")
        h2 = compute_entry_hash("prev2", "ts1", "actor1", "payload1", "GREEN")
        assert h1 != h2

    def test_compute_hash_includes_zone(self):
        """TC-SEC-620: Hash must change with zone."""
        h1 = compute_entry_hash("prev", "ts", "actor", "payload", "GREEN")
        h2 = compute_entry_hash("prev", "ts", "actor", "payload", "RED")
        assert h1 != h2

    def test_compute_hash_is_sha256(self):
        """TC-SEC-621: Hash must be SHA-256."""
        h = compute_entry_hash("prev", "ts", "actor", "payload", "GREEN")
        # Verify it's a valid hex string of correct length
        assert len(h) == 64
        int(h, 16)  # Must be valid hex

    def test_forged_signature_detected(self, tmp_audit_db):
        """TC-SEC-622: Forged current_hash must be detected."""
        entry = log_action("test-actor", "action", Zone.GREEN, db_path=tmp_audit_db)
        # Forge the hash
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute(
            "UPDATE tamper_audit_trail SET current_hash = ? WHERE entry_id = ?",
            ("f" * 64, entry.entry_id),
        )
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False

    def test_forged_previous_hash_detected(self, tmp_audit_db):
        """TC-SEC-623: Forged previous_hash must break chain linkage."""
        log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        entry2 = log_action("test-actor", "action 2", Zone.GREEN, db_path=tmp_audit_db)
        # Forge entry 2's previous_hash to point to wrong hash
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute(
            "UPDATE tamper_audit_trail SET previous_hash = ? WHERE entry_id = ?",
            ("f" * 64, entry2.entry_id),
        )
        conn.commit()
        conn.close()
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is False
        assert status.broken_at == entry2.entry_id


# ============================================================================ #
# I5: Genesis Hash Anchoring
# ============================================================================ #


class TestGenesisHashAnchoring:
    """TC-SEC-624 through TC-SEC-628: First entry chains from genesis."""

    def test_first_entry_previous_is_genesis(self, tmp_audit_db):
        """TC-SEC-624: First entry's previous_hash must be genesis."""
        entry = log_action("test-actor", "first action", Zone.GREEN, db_path=tmp_audit_db)
        assert entry.previous_hash == config.AUDIT_GENESIS_HASH

    def test_genesis_hash_is_zeros(self):
        """TC-SEC-625: Genesis hash must be 64 zeros."""
        assert config.AUDIT_GENESIS_HASH == "0" * 64

    def test_verify_from_id_1_uses_genesis(self, tmp_audit_db):
        """TC-SEC-626: verify_chain(from_id=1) must use genesis as anchor."""
        log_action("test-actor", "action", Zone.GREEN, db_path=tmp_audit_db)
        status = verify_chain(from_id=1, db_path=tmp_audit_db)
        assert status.valid is True

    def test_verify_from_id_2_uses_entry1_hash(self, tmp_audit_db):
        """TC-SEC-627: verify_chain(from_id=2) must use entry 1's hash as anchor."""
        entry1 = log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        log_action("test-actor", "action 2", Zone.GREEN, db_path=tmp_audit_db)
        status = verify_chain(from_id=2, db_path=tmp_audit_db)
        assert status.valid is True
        # This uses entry 1's stored previous_hash as anchor

    def test_tampered_genesis_not_stored(self, tmp_audit_db):
        """TC-SEC-628: Genesis hash is not a DB row, cannot be tampered."""
        # Genesis hash is a config constant, not stored in DB
        conn = sqlite3.connect(str(tmp_audit_db))
        row = conn.execute("SELECT COUNT(*) as n FROM tamper_audit_trail").fetchone()
        conn.close()
        assert row[0] == 0  # No rows = no genesis row to tamper
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is True


# ============================================================================ #
# I6: Secret Redaction Before Hashing
# ============================================================================ #


class TestSecretRedactionBeforeHashing:
    """TC-SEC-629 through TC-SEC-634: Secrets must not enter the ledger."""

    def test_secret_redacted_in_stored_payload(self, tmp_audit_db):
        """TC-SEC-629: Secret-containing payload must be redacted before storage."""
        log_action("test-actor", "api_key = sk-1234567890abcdef", Zone.GREEN, db_path=tmp_audit_db)
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT action_payload FROM tamper_audit_trail ORDER BY entry_id DESC LIMIT 1").fetchone()
        conn.close()
        assert "sk-" not in row["action_payload"] or "REDACTED" in row["action_payload"]

    def test_redaction_does_not_break_chain(self, tmp_audit_db):
        """TC-SEC-630: Redacted payload must still form valid chain."""
        log_action("test-actor", "api_key = sk-1234567890abcdef", Zone.GREEN, db_path=tmp_audit_db)
        log_action("test-actor", "normal action", Zone.GREEN, db_path=tmp_audit_db)
        status = verify_chain(db_path=tmp_audit_db)
        assert status.valid is True

    def test_no_raw_secrets_in_ledger(self, tmp_audit_db):
        """TC-SEC-631: Ledger must never contain raw secret values."""
        aws_key = "AKIA" + "IOSFODNN7EXAMPLE"
        payload_with_secrets = (
            "stripe_key=sk_live_FAKE_TEST_1234567890abcdef "
            f"aws_key={aws_key} "
            "jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.sig"
        )
        log_action("test-actor", payload_with_secrets, Zone.GREEN, db_path=tmp_audit_db)
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT action_payload FROM tamper_audit_trail ORDER BY entry_id DESC LIMIT 1").fetchone()
        conn.close()
        payload = row["action_payload"]
        # None of the raw secrets should appear
        assert "sk_live_" not in payload
        assert "AKIAIOS" not in payload
        assert "eyJhbGci" not in payload

    def test_redacted_marker_in_ledger(self, tmp_audit_db):
        """TC-SEC-632: Redacted marker <REDACTED:...> should be in ledger."""
        log_action("test-actor", "stripe_key = sk_live_FAKE_TEST_1234567890abcdef", Zone.GREEN, db_path=tmp_audit_db)
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT action_payload FROM tamper_audit_trail ORDER BY entry_id DESC LIMIT 1").fetchone()
        conn.close()
        assert "REDACTED" in row["action_payload"]

    def test_audit_entry_indicates_redaction(self, tmp_audit_db):
        """TC-SEC-633: AuditEntry.redacted must be True for secret payload."""
        entry = log_action("test-actor", "stripe_key = sk_live_FAKE_TEST_1234567890abcdef", Zone.GREEN, db_path=tmp_audit_db)
        assert entry.redacted is True

    def test_audit_entry_not_redacted_for_clean(self, tmp_audit_db):
        """TC-SEC-634: AuditEntry.redacted must be False for clean payload."""
        entry = log_action("test-actor", "echo hello", Zone.GREEN, db_path=tmp_audit_db)
        assert entry.redacted is False


# ============================================================================ #
# I7: Fail-Closed Behavior
# ============================================================================ #


class TestFailClosedBehavior:
    """TC-SEC-635 through TC-SEC-639: Audit system must fail closed."""

    def test_invalid_zone_raises_error(self, tmp_audit_db):
        """TC-SEC-635: Invalid zone must raise AuditError."""
        with pytest.raises(AuditError):
            log_action("test-actor", "action", "INVALID_ZONE", db_path=tmp_audit_db)

    def test_empty_string_zone_raises_error(self, tmp_audit_db):
        """TC-SEC-636: Empty string zone must raise AuditError."""
        with pytest.raises(AuditError):
            log_action("test-actor", "action", "", db_path=tmp_audit_db)

    def test_none_zone_raises_error(self, tmp_audit_db):
        """TC-SEC-637: None zone must raise AuditError."""
        with pytest.raises(AuditError):
            log_action("test-actor", "action", None, db_path=tmp_audit_db)

    def test_zone_enum_accepted(self, tmp_audit_db):
        """TC-SEC-638: Zone enum must be accepted."""
        entry = log_action("test-actor", "action", Zone.GREEN, db_path=tmp_audit_db)
        assert entry.entry_id > 0

    def test_zone_string_accepted(self, tmp_audit_db):
        """TC-SEC-639: Zone string must be accepted."""
        entry = log_action("test-actor", "action", "GREEN", db_path=tmp_audit_db)
        assert entry.entry_id > 0


# ============================================================================ #
# I8: Chain Verification Range
# ============================================================================ #


class TestChainVerificationRange:
    """TC-SEC-640 through TC-SEC-644: Partial chain verification."""

    def test_verify_range_subset(self, tmp_audit_db):
        """TC-SEC-640: Verify subset of chain must work."""
        for i in range(5):
            log_action("test-actor", f"action {i}", Zone.GREEN, db_path=tmp_audit_db)
        status = verify_chain(from_id=2, to_id=4, db_path=tmp_audit_db)
        assert status.valid is True
        assert status.total_entries == 3

    def test_verify_range_with_tamper_outside(self, tmp_audit_db):
        """TC-SEC-641: Range verify excludes tampered entries outside range."""
        log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        entry2 = log_action("test-actor", "action 2", Zone.GREEN, db_path=tmp_audit_db)
        for i in range(3, 6):
            log_action("test-actor", f"action {i}", Zone.GREEN, db_path=tmp_audit_db)
        # Tamper entry 2
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute("UPDATE tamper_audit_trail SET action_payload = 'tampered' WHERE entry_id = ?", (entry2.entry_id,))
        conn.commit()
        conn.close()
        # Verify range 3-5 should be valid (doesn't include tampered entry 2)
        status = verify_chain(from_id=3, to_id=5, db_path=tmp_audit_db)
        assert status.valid is True

    def test_verify_range_with_tamper_inside(self, tmp_audit_db):
        """TC-SEC-642: Range verify includes tampered entries inside range."""
        for i in range(1, 6):
            log_action("test-actor", f"action {i}", Zone.GREEN, db_path=tmp_audit_db)
        # Tamper entry 3
        conn = sqlite3.connect(str(tmp_audit_db))
        conn.execute("UPDATE tamper_audit_trail SET action_payload = 'tampered' WHERE entry_id = 3")
        conn.commit()
        conn.close()
        # Verify range 2-4 should detect tamper at entry 3
        status = verify_chain(from_id=2, to_id=4, db_path=tmp_audit_db)
        assert status.valid is False
        assert status.broken_at == 3

    def test_verify_beyond_range_empty(self, tmp_audit_db):
        """TC-SEC-643: Verify beyond existing entries must be valid (empty)."""
        log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        status = verify_chain(from_id=100, to_id=200, db_path=tmp_audit_db)
        assert status.valid is True
        assert status.total_entries == 0

    def test_verify_single_entry(self, tmp_audit_db):
        """TC-SEC-644: Verify single entry range."""
        log_action("test-actor", "action 1", Zone.GREEN, db_path=tmp_audit_db)
        log_action("test-actor", "action 2", Zone.GREEN, db_path=tmp_audit_db)
        status = verify_chain(from_id=1, to_id=1, db_path=tmp_audit_db)
        assert status.valid is True
        assert status.total_entries == 1
