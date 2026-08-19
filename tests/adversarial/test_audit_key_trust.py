"""The audit verifier must not take its trust from the database it verifies.

§VIII controlled self-modification, operator-approved 2026-08-19.

`verify_chain` loaded every verification key with
``SELECT key_id, public_key_hex FROM audit_keys`` -- a table inside the same
SQLite file as ``tamper_audit_trail``. An attacker with write access to that file
could therefore supply the key that vouches for their own forgery: insert a
public key, re-sign forged entries, recompute the hash chain, re-point the tip
anchor, and every in-database check passes because the attacker controlled every
input to those checks.

The signing key was never the weakness. It is volatile, read from
``AIOS_AUDIT_PRIVATE_KEY`` and never persisted (AGENTS.md VII.4) -- but a
volatile signing key protects SIGNING, not TRUST.

These tests state the attack and the fix together, so the property cannot quietly
regress into "internally consistent" being reported as "attested".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios import config
from aios.security.audit_logger import (
    init_audit_db,
    log_action,
    verify_chain,
)
from aios.security.gateway import Zone

ed25519 = pytest.importorskip(
    "cryptography.hazmat.primitives.asymmetric.ed25519",
    reason="Ed25519 unavailable; signatures are disabled entirely",
)
Ed25519PrivateKey = ed25519.Ed25519PrivateKey


def _forge_entire_chain(db_path: Path) -> None:
    """Rewrite the ledger end to end as an attacker with database write access.

    Not a single-field mutation -- the whole attack, including registering the
    attacker's own key in ``audit_keys`` and re-pointing the signed tip anchor.
    """
    from aios.security.audit_logger import (
        _sign_entry,
        _sign_tip_anchor,
        compute_entry_hash,
    )

    attacker = Ed25519PrivateKey.generate()
    attacker_hex = attacker.public_key().public_bytes_raw().hex()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "INSERT INTO audit_keys (public_key_hex, created_at, active) VALUES (?, ?, 1)",
            (attacker_hex, "2026-08-19T00:00:00Z"),
        )
        attacker_key_id = cur.lastrowid

        previous_hash = config.AUDIT_GENESIS_HASH
        for row in conn.execute(
            "SELECT * FROM tamper_audit_trail ORDER BY entry_id ASC"
        ).fetchall():
            payload = "ATTACKER REWROTE THIS ENTRY"
            new_hash = compute_entry_hash(
                previous_hash,
                row["timestamp"],
                row["actor"],
                payload,
                row["security_zone"],
                version=int(row["hash_version"] or 1),
            )
            # Signed through the PRODUCTION signing path, so the forgery is
            # genuinely well-formed rather than merely plausible.
            signature = _sign_entry(
                attacker,
                previous_hash,
                row["timestamp"],
                row["actor"],
                payload,
                row["security_zone"],
                new_hash,
            )
            conn.execute(
                "UPDATE tamper_audit_trail SET action_payload = ?, current_hash = ?, "
                "previous_hash = ?, signature = ?, key_id = ? WHERE entry_id = ?",
                (
                    payload,
                    new_hash,
                    previous_hash,
                    signature,
                    attacker_key_id,
                    row["entry_id"],
                ),
            )
            previous_hash = new_hash

        tip = conn.execute(
            "SELECT entry_id, current_hash FROM tamper_audit_trail "
            "ORDER BY entry_id DESC LIMIT 1"
        ).fetchone()
        if tip is not None:
            anchor_sig = _sign_tip_anchor(
                attacker, int(tip["entry_id"]), tip["current_hash"]
            )
            conn.execute(
                "UPDATE audit_tip_anchor SET tip_entry_id = ?, tip_hash = ?, "
                "signature = ?, key_id = ? WHERE anchor_id = 1",
                (
                    int(tip["entry_id"]),
                    tip["current_hash"],
                    anchor_sig,
                    attacker_key_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def test_a_pinned_key_refuses_a_fully_forged_chain(tmp_path, monkeypatch) -> None:
    """The fix, stated as the attack it defeats.

    The forged chain is INTERNALLY PERFECT: linkage recomputed, payload hashes
    consistent, every signature valid under a key the ledger itself vouches for,
    anchor re-pointed. It is refused anyway, because the key that matters was
    never in the database.
    """
    seed = bytes(range(32))
    monkeypatch.setenv("AIOS_AUDIT_PRIVATE_KEY", seed.hex())
    monkeypatch.delenv("AIOS_AUDIT_PUBLIC_KEY", raising=False)

    db_path = tmp_path / "pinned.db"
    init_audit_db(db_path)
    for i in range(3):
        log_action(f"actor-{i}", f"honest action {i}", Zone.GREEN, db_path=db_path)

    honest = verify_chain(db_path=db_path)
    assert honest.valid is True
    assert honest.trust_anchored is True, "a configured signing key must anchor trust"

    _forge_entire_chain(db_path)

    forged = verify_chain(db_path=db_path)

    assert forged.valid is False, (
        "a chain re-signed with a key the attacker inserted into audit_keys was "
        "accepted -- the verifier is still taking its trust from the database it "
        "is verifying"
    )
    assert forged.signature_valid is False
    assert forged.invalid_signatures, (
        "the forged entries must be named, not just counted"
    )


def test_key_id_cannot_choose_the_verifying_key(tmp_path, monkeypatch) -> None:
    """`key_id` is a column in the file under suspicion.

    Letting it select the verifying key hands the attacker back the choice the
    pin exists to take away, so the pinned path ignores it entirely: an entry
    counts only if it verifies under a key the OPERATOR pinned.
    """
    seed = bytes(range(32))
    monkeypatch.setenv("AIOS_AUDIT_PRIVATE_KEY", seed.hex())

    db_path = tmp_path / "keyid.db"
    init_audit_db(db_path)
    log_action("actor", "honest", Zone.GREEN, db_path=db_path)

    # Point every entry at a key_id that does not exist. Under a pin this is
    # irrelevant: the signature is still the operator's, so it still verifies.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE tamper_audit_trail SET key_id = 9999")
        conn.commit()
    finally:
        conn.close()

    status = verify_chain(db_path=db_path)

    assert status.valid is True, (
        "a bogus key_id must not invalidate an entry whose signature verifies "
        "under the pinned key"
    )
    assert status.trust_anchored is True


def test_an_unpinned_verification_says_it_is_unanchored(tmp_path, monkeypatch) -> None:
    """The honest half: never imply attestation that was not performed.

    An ephemeral per-process key cannot anchor a chain written by another
    process, so trust here is genuinely unanchorable rather than merely
    unconfigured. `valid=True` then means "internally consistent", NOT
    "attested", and the status must say which. C5's own rule -- unavailable
    rather than a plausible zero -- applies to trust as much as to counts.
    """
    monkeypatch.delenv("AIOS_AUDIT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("AIOS_AUDIT_PUBLIC_KEY", raising=False)

    db_path = tmp_path / "unpinned.db"
    init_audit_db(db_path)
    log_action("actor", "an action", Zone.GREEN, db_path=db_path)

    status = verify_chain(db_path=db_path)

    assert status.trust_anchored is False
    assert status.reason and "audited database" in status.reason, (
        "an unanchored pass must name the limitation rather than pass silently"
    )


def test_pinning_a_key_set_preserves_rotation(tmp_path, monkeypatch) -> None:
    """Rotation must survive the fix, or it trades one failure for another.

    `audit_keys` exists so retired keys keep verifying the history they signed
    (module docstring). A pinned SET keeps that true, which is why
    AIOS_AUDIT_PUBLIC_KEY accepts more than one key.
    """
    old_seed, new_seed = bytes(range(32)), bytes(range(32, 64))
    old_key = Ed25519PrivateKey.from_private_bytes(old_seed)
    new_key = Ed25519PrivateKey.from_private_bytes(new_seed)

    db_path = tmp_path / "rotate.db"
    monkeypatch.setenv("AIOS_AUDIT_PRIVATE_KEY", old_seed.hex())
    init_audit_db(db_path)
    log_action("actor", "signed by the retired key", Zone.GREEN, db_path=db_path)

    monkeypatch.setenv(
        "AIOS_AUDIT_PUBLIC_KEY",
        ", ".join(
            (
                new_key.public_key().public_bytes_raw().hex(),
                old_key.public_key().public_bytes_raw().hex(),
            )
        ),
    )
    status = verify_chain(db_path=db_path)

    assert status.valid is True, "a rotated-out key must still verify its own history"
    assert status.trust_anchored is True


def test_a_malformed_pin_does_not_silently_disable_verification(
    tmp_path, monkeypatch
) -> None:
    """A typo in the pin must not degrade into 'trust the database again'.

    The dangerous failure is a malformed AIOS_AUDIT_PUBLIC_KEY that parses to
    nothing while the operator believes trust is anchored. The private key
    remains configured here, so the derived pin still applies and the status
    still reports anchored.
    """
    seed = bytes(range(32))
    monkeypatch.setenv("AIOS_AUDIT_PRIVATE_KEY", seed.hex())
    monkeypatch.setenv("AIOS_AUDIT_PUBLIC_KEY", "not-hex, also-not-hex")

    db_path = tmp_path / "malformed.db"
    init_audit_db(db_path)
    log_action("actor", "honest", Zone.GREEN, db_path=db_path)

    status = verify_chain(db_path=db_path)

    assert status.valid is True
    assert status.trust_anchored is True, (
        "an unparseable pin must fall back to the configured private key, not to "
        "trusting the audited database"
    )


# --------------------------------------------------------------------------- #
# Downgrade and erasure: pinning a key is not enough on its own
# --------------------------------------------------------------------------- #


def test_stripping_signatures_is_tampering_not_legacy_data(
    tmp_path, monkeypatch
) -> None:
    """The downgrade attack: remove the crypto and the checker stops checking.

    `chain_valid` counted only `invalid_sigs`, and an entry with no signature
    merely incremented `unsigned_entries`. So an attacker could forge every
    payload, recompute the chain, DELETE the signatures, re-point an unsigned
    anchor -- and the verifier returned valid=True. Pinning a key did not help,
    because the pinned path was never reached for an entry that carried no
    signature to check.
    """
    seed = bytes(range(32))
    monkeypatch.setenv("AIOS_AUDIT_PRIVATE_KEY", seed.hex())

    db_path = tmp_path / "stripped.db"
    init_audit_db(db_path)
    for i in range(3):
        log_action(f"actor-{i}", f"honest {i}", Zone.GREEN, db_path=db_path)

    from aios.security.audit_logger import compute_entry_hash

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        previous_hash = config.AUDIT_GENESIS_HASH
        for row in conn.execute(
            "SELECT * FROM tamper_audit_trail ORDER BY entry_id ASC"
        ).fetchall():
            payload = "ATTACKER REWROTE THIS, SIGNATURE REMOVED"
            new_hash = compute_entry_hash(
                previous_hash,
                row["timestamp"],
                row["actor"],
                payload,
                row["security_zone"],
                version=int(row["hash_version"] or 1),
            )
            conn.execute(
                "UPDATE tamper_audit_trail SET action_payload=?, current_hash=?, "
                "previous_hash=?, signature=NULL, key_id=NULL WHERE entry_id=?",
                (payload, new_hash, previous_hash, row["entry_id"]),
            )
            previous_hash = new_hash
        tip = conn.execute(
            "SELECT entry_id, current_hash FROM tamper_audit_trail "
            "ORDER BY entry_id DESC LIMIT 1"
        ).fetchone()
        conn.execute(
            "UPDATE audit_tip_anchor SET tip_entry_id=?, tip_hash=?, signature=NULL, "
            "key_id=NULL WHERE anchor_id=1",
            (int(tip["entry_id"]), tip["current_hash"]),
        )
        conn.commit()
    finally:
        conn.close()

    status = verify_chain(db_path=db_path)

    assert status.valid is False, (
        "a chain whose signatures were deleted was accepted -- stripping the "
        "crypto must be tampering, not a downgrade to 'legacy unsigned'"
    )
    assert status.unsigned_entries == 3


def test_a_pre_signature_ledger_is_still_accepted(tmp_path, monkeypatch) -> None:
    """The counterpart that must NOT regress: genuine legacy data still verifies.

    Treating every unsigned entry as tampering would condemn ledgers written
    before signing existed. The discriminator is whether this chain is KNOWN to
    sign -- a pinned key, or a key the ledger registered itself. A pre-signature
    ledger has neither, and is left exactly as lenient as it was.
    """
    monkeypatch.delenv("AIOS_AUDIT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("AIOS_AUDIT_PUBLIC_KEY", raising=False)

    db_path = tmp_path / "legacy.db"
    init_audit_db(db_path)
    log_action("actor", "written before signing existed", Zone.GREEN, db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE tamper_audit_trail SET signature=NULL, key_id=NULL")
        conn.execute("UPDATE audit_tip_anchor SET signature=NULL, key_id=NULL")
        conn.execute("DELETE FROM audit_keys")  # no key was ever registered
        conn.commit()
    finally:
        conn.close()

    status = verify_chain(db_path=db_path)

    assert status.valid is True, (
        "a genuinely pre-signature ledger must still verify; the strip check "
        "keys off whether this chain signs at all"
    )


def test_deleting_the_entire_ledger_is_detected(tmp_path, monkeypatch) -> None:
    """Total erasure was the one tamper that reported perfectly clean.

    An emptied ledger that still has its anchor is caught by the anchor naming a
    tip that no longer exists. Deleting the anchor TOO left nothing to disagree
    with: no rows to iterate, no anchor to check, so every test passed vacuously
    and verify_chain returned valid=True.

    A key row appears on the first append, so "registered a key, holds no
    entries" is a deletion.
    """
    seed = bytes(range(32))
    monkeypatch.setenv("AIOS_AUDIT_PRIVATE_KEY", seed.hex())

    db_path = tmp_path / "wiped.db"
    init_audit_db(db_path)
    for i in range(3):
        log_action(f"actor-{i}", f"honest {i}", Zone.GREEN, db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM tamper_audit_trail")
        conn.execute("DELETE FROM audit_tip_anchor")
        conn.commit()
    finally:
        conn.close()

    status = verify_chain(db_path=db_path)

    assert status.valid is False, "deleting every entry AND the anchor was accepted"
    assert status.reason and "emptied" in status.reason.lower()


def test_a_never_written_ledger_is_not_mistaken_for_a_wiped_one(
    tmp_path, monkeypatch
) -> None:
    """A fresh install must not be reported as tampered.

    This is the false positive the erasure check has to avoid, and the reason it
    keys off a REGISTERED KEY rather than emptiness alone: a never-written
    ledger has no key, a wiped one kept the key it registered on first append.
    """
    seed = bytes(range(32))
    monkeypatch.setenv("AIOS_AUDIT_PRIVATE_KEY", seed.hex())

    db_path = tmp_path / "brand_new.db"
    init_audit_db(db_path)

    status = verify_chain(db_path=db_path)

    assert status.valid is True, "a fresh, never-written ledger must verify clean"
    assert status.total_entries == 0
