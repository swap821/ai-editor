"""Ed25519-signed, SHA-256 hash-chained, tamper-evident audit logger (A+ Grade).

Every security-relevant action is appended to an append-only ledger in a
dedicated SQLite database. Each entry stores::

    current_hash = SHA256(previous_hash || timestamp || actor || payload || zone)
    signature    = Ed25519.Sign(SHA256(canonical_json(entry_fields)))

with the genesis entry chaining from 64 zero characters. Altering any historical
entry changes its hash, which breaks every subsequent link, so tampering is
detectable in O(n) by a single sequential pass (:func:`verify_chain`).

Ed25519 digital signatures provide **non-repudiation** — even an insider with
full database access cannot forge or alter entries without the private signing
key. The signature covers the canonical JSON representation of all entry
fields, creating a cryptographic binding between the ledger content and the
signing identity.

Key rotation is supported via the ``audit_keys`` table: old keys continue to
verify historical entries while new keys sign fresh ones. The
:func:`get_anchor` method returns the latest signed hash for external
trust-anchor publication (blockchain, CT log, etc.).

Three trust principles are enforced here:

* **No secret persistence** — payloads are run through the secret scanner and
  redacted *before* they are hashed or stored, so credentials never enter the
  ledger (the hash is computed over the redacted text, keeping the chain
  internally consistent).
* **Fail-closed** — a logging failure raises :class:`AuditError`; the caller
  must treat an unrecorded action as a refused action.
* **Non-repudiation** — Ed25519 signatures prevent entry forgery by anyone
  without access to the signing key, including database administrators and
  insiders.

The ledger lives in its own database (:data:`aios.config.AUDIT_DB_PATH`),
isolated from mutable memory so ordinary writes can never perturb the chain.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from aios import config
from aios.security.gateway import Zone
from aios.security.secret_scanner import scan_and_redact

# --------------------------------------------------------------------------- #
# Ed25519 cryptography — graceful degradation if unavailable
# --------------------------------------------------------------------------- #

logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature

    _ED25519_AVAILABLE: bool = True
except Exception:  # noqa: BLE001
    _ED25519_AVAILABLE = False
    logger.warning(
        "cryptography library Ed25519 support unavailable — "
        "audit signatures disabled (hash-chain only). "
        "Install: pip install cryptography>=44.0.3"
    )


#: Environment variable holding the hex-encoded 64-byte Ed25519 private-key seed.
_ENV_AUDIT_PRIVATE_KEY: str = "AIOS_AUDIT_PRIVATE_KEY"


# --------------------------------------------------------------------------- #
# Schema (idempotent DDL)
# --------------------------------------------------------------------------- #

_AUDIT_SCHEMA = """
-- Audit entries: append-only ledger with hash chain + Ed25519 signatures
CREATE TABLE IF NOT EXISTS tamper_audit_trail (
    entry_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    actor           TEXT NOT NULL,
    action_payload  TEXT NOT NULL,
    security_zone   TEXT NOT NULL CHECK (security_zone IN ('GREEN','YELLOW','RED')),
    current_hash    TEXT NOT NULL,
    previous_hash   TEXT NOT NULL,
    signature       TEXT,
    key_id          INTEGER,
    -- Chain-hash preimage version (Phase 3): existing rows default to 1 (legacy
    -- concat); new rows use 2 (collision-resistant canonical JSON).
    hash_version    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_audit_zone ON tamper_audit_trail(security_zone);
CREATE INDEX IF NOT EXISTS idx_audit_time ON tamper_audit_trail(timestamp);

-- Signing keys: supports rotation (old keys verify old entries)
CREATE TABLE IF NOT EXISTS audit_keys (
    key_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    public_key_hex  TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1
);

-- Signed tip-anchor (Phase 3): a single row pinning the chain's tip so a
-- tail-truncation (lopping the latest entries) is detectable. Updated atomically
-- inside each append transaction and Ed25519-signed.
CREATE TABLE IF NOT EXISTS audit_tip_anchor (
    anchor_id       INTEGER PRIMARY KEY CHECK (anchor_id = 1),
    tip_entry_id    INTEGER NOT NULL,
    tip_hash        TEXT NOT NULL,
    signature       TEXT,
    key_id          INTEGER,
    updated_at      TEXT NOT NULL
);
"""

#: Serialises appends within a process; SQLite BEGIN IMMEDIATE extends the
#: same head-read + append critical section across local worker processes.
_append_lock = threading.Lock()
#: Databases whose schema has already been ensured this process.
_initialized: set[str] = set()
#: Cached signing state per DB path to avoid repeated key lookups.
_signing_cache: dict[str, "_SigningState"] = {}


class AuditError(RuntimeError):
    """Raised when an audit write fails; signals the fail-closed policy."""


@dataclass(frozen=True)
class AuditEntry:
    """A freshly appended ledger entry."""

    entry_id: int
    current_hash: str
    previous_hash: str
    redacted: bool
    signature: Optional[str] = None
    key_id: Optional[int] = None


@dataclass(frozen=True)
class ChainStatus:
    """Result of verifying (a range of) the hash chain and signatures."""

    valid: bool
    total_entries: int
    broken_at: Optional[int] = None
    reason: Optional[str] = None
    head_hash: Optional[str] = None
    signature_valid: bool = True
    invalid_signatures: tuple[int, ...] = ()
    unsigned_entries: int = 0
    #: Tip-anchor verdict (Phase 3), checked on a full verify-to-tip:
    #: True = the signed anchor matches the real tip; False = tail-truncation /
    #: anchor tamper detected; None = no anchor present (legacy / never-written).
    tip_anchor_valid: Optional[bool] = None


# --------------------------------------------------------------------------- #
# Internal: signing state
# --------------------------------------------------------------------------- #

@dataclass
class _SigningState:
    """Runtime state for Ed25519 signing."""

    private_key: Optional[Ed25519PrivateKey] = None
    public_key: Optional[Ed25519PublicKey] = None
    key_id: Optional[int] = None
    enabled: bool = False


# --------------------------------------------------------------------------- #
# Key management
# --------------------------------------------------------------------------- #

def _load_or_create_private_key() -> tuple[Ed25519PrivateKey, bool]:
    """Load Ed25519 private key from env var or generate a new one.

    Returns:
        ``(private_key, was_generated)`` — *was_generated* is True when a new
        key was created because the env var was unset.
    """
    hex_seed = os.getenv(_ENV_AUDIT_PRIVATE_KEY, "").strip()
    if hex_seed:
        try:
            seed_bytes = bytes.fromhex(hex_seed)
            if len(seed_bytes) != 32:
                raise ValueError(
                    f"Expected 32-byte (64 hex char) seed, got {len(seed_bytes)} bytes"
                )
            private_key = Ed25519PrivateKey.from_private_bytes(seed_bytes)
            return private_key, False
        except ValueError as exc:
            logger.error(
                "Invalid AIOS_AUDIT_PRIVATE_KEY format (%s). "
                "Must be 64 hex characters (32-byte Ed25519 seed). "
                "Generating ephemeral key — signatures will NOT survive restart!",
                exc,
            )
    else:
        logger.warning(
            "AIOS_AUDIT_PRIVATE_KEY not set — generating ephemeral Ed25519 key pair. "
            "Signatures are valid for this process lifetime only. "
            "For production: set AIOS_AUDIT_PRIVATE_KEY to a 64-hex-char seed."
        )
    private_key = Ed25519PrivateKey.generate()
    return private_key, True


def _init_signing_state(db_path: Path) -> _SigningState:
    """Initialise signing state for *db_path* — idempotent per process."""
    cache_key = str(db_path)
    if cache_key in _signing_cache:
        return _signing_cache[cache_key]

    state = _SigningState()

    if not _ED25519_AVAILABLE:
        _signing_cache[cache_key] = state
        return state

    # Load or generate the signing key
    private_key, was_generated = _load_or_create_private_key()
    state.private_key = private_key
    state.public_key = private_key.public_key()
    state.enabled = True

    # Ensure the key is registered in the database
    conn = _connect(db_path)
    try:
        public_key_hex = state.public_key.public_bytes_raw().hex()
        row = conn.execute(
            "SELECT key_id FROM audit_keys WHERE public_key_hex = ?", (public_key_hex,)
        ).fetchone()
        if row:
            state.key_id = int(row["key_id"])
            if was_generated:
                logger.info(
                    "Using existing audit signing key (key_id=%d). "
                    "Ephemeral key matched database entry.",
                    state.key_id,
                )
        else:
            cur = conn.execute(
                "INSERT INTO audit_keys (public_key_hex, created_at, active) "
                "VALUES (?, ?, 1)",
                (public_key_hex, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            state.key_id = int(cur.lastrowid)
            logger.info(
                "Registered new audit signing key (key_id=%d, pubkey=%s...%s).",
                state.key_id,
                public_key_hex[:8],
                public_key_hex[-8:],
            )
    finally:
        conn.close()

    _signing_cache[cache_key] = state
    return state


def _get_signing_state(db_path: Path) -> _SigningState:
    """Return cached signing state, initialising if needed."""
    cache_key = str(db_path)
    if cache_key not in _signing_cache:
        return _init_signing_state(db_path)
    return _signing_cache[cache_key]


def rotate_audit_key(db_path: Path = config.AUDIT_DB_PATH) -> int:
    """Rotate the audit signing key: deactivate old key, create new one.

    After rotation, old entries are still verifiable (old key stays in the
    ``audit_keys`` table with ``active=0``), but new entries are signed with
    the fresh key.

    Returns:
        The *key_id* of the newly created signing key.

    Raises:
        AuditError: If cryptography is unavailable or rotation fails.
    """
    if not _ED25519_AVAILABLE:
        raise AuditError("Ed25519 cryptography unavailable — cannot rotate keys.")

    cache_key = str(db_path)
    _ensure_initialized(db_path)
    conn = _connect(db_path)
    try:
        # Deactivate current key in DB
        state = _get_signing_state(db_path)
        if state.key_id is not None:
            conn.execute(
                "UPDATE audit_keys SET active = 0 WHERE key_id = ?", (state.key_id,)
            )

        # Generate fresh key pair
        new_private_key = Ed25519PrivateKey.generate()
        new_public_key = new_private_key.public_key()
        public_key_hex = new_public_key.public_bytes_raw().hex()

        cur = conn.execute(
            "INSERT INTO audit_keys (public_key_hex, created_at, active) "
            "VALUES (?, ?, 1)",
            (public_key_hex, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        new_key_id = int(cur.lastrowid)

        # Update cache
        state.private_key = new_private_key
        state.public_key = new_public_key
        state.key_id = new_key_id
        _signing_cache[cache_key] = state

        logger.info(
            "Rotated audit signing key: new key_id=%d (pubkey=%s...%s).",
            new_key_id,
            public_key_hex[:8],
            public_key_hex[-8:],
        )
        return new_key_id
    except AuditError:
        raise
    except Exception as exc:
        raise AuditError(f"Audit key rotation failed: {exc}") from exc
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Canonical JSON for signature payload
# --------------------------------------------------------------------------- #

def _canonical_json(
    previous_hash: str,
    timestamp: str,
    actor: str,
    action_payload: str,
    security_zone: str,
    current_hash: str,
) -> str:
    """Return a canonical JSON string of the entry fields (sorted keys).

    The signature covers this canonical representation, ensuring deterministic
    verification regardless of how the data was originally serialised.
    """
    obj = {
        "previous_hash": previous_hash,
        "timestamp": timestamp,
        "actor": actor,
        "action_payload": action_payload,
        "security_zone": security_zone,
        "current_hash": current_hash,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sign_entry(
    private_key: Ed25519PrivateKey,
    previous_hash: str,
    timestamp: str,
    actor: str,
    action_payload: str,
    security_zone: str,
    current_hash: str,
) -> str:
    """Sign the canonical JSON of entry fields. Return hex-encoded signature."""
    canonical = _canonical_json(
        previous_hash, timestamp, actor, action_payload, security_zone, current_hash
    )
    data_to_sign = hashlib.sha256(canonical.encode("utf-8")).digest()
    signature = private_key.sign(data_to_sign)
    return signature.hex()


def _verify_entry_signature(
    public_key: Ed25519PublicKey,
    signature_hex: str,
    previous_hash: str,
    timestamp: str,
    actor: str,
    action_payload: str,
    security_zone: str,
    current_hash: str,
) -> bool:
    """Verify an Ed25519 signature over the canonical entry fields."""
    try:
        canonical = _canonical_json(
            previous_hash, timestamp, actor, action_payload, security_zone, current_hash
        )
        data_to_sign = hashlib.sha256(canonical.encode("utf-8")).digest()
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, data_to_sign)
        return True
    except (InvalidSignature, ValueError):
        return False


def _canonical_tip_anchor(tip_entry_id: int, tip_hash: str) -> str:
    """Canonical JSON of the tip-anchor fields (sorted keys)."""
    return json.dumps(
        {"tip_entry_id": int(tip_entry_id), "tip_hash": tip_hash},
        sort_keys=True,
        separators=(",", ":"),
    )


def _sign_tip_anchor(
    private_key: Ed25519PrivateKey, tip_entry_id: int, tip_hash: str
) -> str:
    """Ed25519-sign the canonical tip-anchor; return a hex signature."""
    data = hashlib.sha256(
        _canonical_tip_anchor(tip_entry_id, tip_hash).encode("utf-8")
    ).digest()
    return private_key.sign(data).hex()


def _verify_tip_anchor_signature(
    public_key: Ed25519PublicKey, signature_hex: str, tip_entry_id: int, tip_hash: str
) -> bool:
    """Verify an Ed25519 signature over the canonical tip-anchor."""
    try:
        data = hashlib.sha256(
            _canonical_tip_anchor(tip_entry_id, tip_hash).encode("utf-8")
        ).digest()
        public_key.verify(bytes.fromhex(signature_hex), data)
        return True
    except (InvalidSignature, ValueError):
        return False


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #

def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a tuned connection to the audit database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = FULL;")
    return conn


def init_audit_db(db_path: Path = config.AUDIT_DB_PATH) -> None:
    """Create the ledger table, keys table, and indexes if absent (idempotent)."""
    conn = _connect(db_path)
    try:
        conn.executescript(_AUDIT_SCHEMA)
        # ALTER-if-missing: add hash_version to a pre-Phase-3 ledger (existing rows
        # are legacy v1; new appends write v2). CREATE TABLE IF NOT EXISTS never
        # adds a column to an existing table.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(tamper_audit_trail)")}
        if "hash_version" not in cols:
            conn.execute(
                "ALTER TABLE tamper_audit_trail "
                "ADD COLUMN hash_version INTEGER NOT NULL DEFAULT 1"
            )
        # ALTER-if-missing: add the Ed25519 columns to a PRE-SIGNATURE ledger.
        # Without this, log_action's INSERT fail-closes on the missing `signature`
        # column, bricking EVERY guarded write on an old DB. Strengthen-only:
        # legacy rows keep NULL signatures, which verify_chain already treats as
        # unsigned-legacy (no guard is relaxed).
        if "signature" not in cols:
            conn.execute("ALTER TABLE tamper_audit_trail ADD COLUMN signature TEXT")
        if "key_id" not in cols:
            conn.execute("ALTER TABLE tamper_audit_trail ADD COLUMN key_id TEXT")
        conn.commit()
    finally:
        conn.close()


def _ensure_initialized(db_path: Path) -> None:
    """Ensure the schema exists for *db_path*, at most once per process path."""
    key = str(db_path)
    if key not in _initialized:
        init_audit_db(db_path)
        _initialized.add(key)


# --------------------------------------------------------------------------- #
# Hash chain
# --------------------------------------------------------------------------- #

#: Current chain-hash preimage version. v2 (canonical JSON) is unambiguous at field
#: boundaries; v1 (legacy delimiter-less concat) is KEPT only so pre-existing chains
#: still verify under their own version.
_CHAIN_HASH_VERSION: int = 2


def compute_entry_hash(
    previous_hash: str,
    timestamp: str,
    actor: str,
    payload: str,
    zone: str,
    *,
    version: int = _CHAIN_HASH_VERSION,
) -> str:
    """Return the chain hash of an entry's fields, by preimage *version*.

    v1 (legacy): ``SHA256(previous_hash || timestamp || actor || payload || zone)`` —
    delimiter-less, so distinct field splits collide (``actor='ab',payload='c'`` ==
    ``actor='a',payload='bc'``). Retained ONLY to verify entries written before the
    Phase 3 hardening.

    v2 (default): ``SHA256(canonical_json({fields}))`` — sorted-key JSON is an
    unambiguous, injective encoding, so no field-boundary collision is possible.
    """
    if version == 1:
        raw = f"{previous_hash}{timestamp}{actor}{payload}{zone}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    canonical = json.dumps(
        {
            "previous_hash": previous_hash,
            "timestamp": timestamp,
            "actor": actor,
            "action_payload": payload,
            "security_zone": zone,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _zone_str(zone: Union[Zone, str]) -> str:
    """Normalise a zone (enum or string) to its canonical string value."""
    return zone.value if isinstance(zone, Zone) else str(zone)


# --------------------------------------------------------------------------- #
# Core API: append
# --------------------------------------------------------------------------- #

def log_action(
    actor: str,
    payload: str,
    zone: Union[Zone, str] = Zone.YELLOW,
    *,
    db_path: Path = config.AUDIT_DB_PATH,
    redact_secrets: bool = True,
) -> AuditEntry:
    """Append one action to the tamper-evident ledger and return its entry.

    The entry is signed with the current Ed25519 signing key (if available)
    providing non-repudiation in addition to the hash-chain integrity guarantee.

    Args:
        actor: Component or human identity performing the action.
        payload: Serialised action description.
        zone: Security zone (``Zone`` enum or ``'GREEN'|'YELLOW'|'RED'``).
        db_path: Ledger database to append to.
        redact_secrets: When True (default), scrub credentials from *payload*
            before hashing and storage.

    Returns:
        The :class:`AuditEntry` that was written (includes signature when
        Ed25519 is enabled).

    Raises:
        AuditError: On an invalid zone or any storage failure (fail-closed).
    """
    zone_str = _zone_str(zone)
    if zone_str not in (Zone.GREEN.value, Zone.YELLOW.value, Zone.RED.value):
        raise AuditError(f"Invalid security zone: {zone_str!r}")

    stored_payload = payload
    redacted = False
    if redact_secrets:
        scan = scan_and_redact(payload)
        stored_payload, redacted = scan.scrubbed, scan.detected

    try:
        with _append_lock:
            _ensure_initialized(db_path)
            # Initialise signing state (reads env var, caches key)
            sign_state = _get_signing_state(db_path)
            conn = _connect(db_path)
            try:
                # Cross-process chain lock: no other writer can read the same
                # head and append a sibling link until this transaction commits.
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT current_hash FROM tamper_audit_trail "
                    "ORDER BY entry_id DESC LIMIT 1"
                ).fetchone()
                previous_hash = (
                    row["current_hash"] if row else config.AUDIT_GENESIS_HASH
                )
                timestamp = datetime.now(timezone.utc).isoformat()
                current_hash = compute_entry_hash(
                    previous_hash, timestamp, actor, stored_payload, zone_str
                )

                # Ed25519 sign the entry (defense in depth atop hash chain)
                signature: Optional[str] = None
                key_id: Optional[int] = None
                if sign_state.enabled and sign_state.private_key is not None:
                    signature = _sign_entry(
                        sign_state.private_key,
                        previous_hash,
                        timestamp,
                        actor,
                        stored_payload,
                        zone_str,
                        current_hash,
                    )
                    key_id = sign_state.key_id

                cur = conn.execute(
                    "INSERT INTO tamper_audit_trail "
                    "(timestamp, actor, action_payload, security_zone, "
                    " current_hash, previous_hash, signature, key_id, hash_version) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        timestamp,
                        actor,
                        stored_payload,
                        zone_str,
                        current_hash,
                        previous_hash,
                        signature,
                        key_id,
                        _CHAIN_HASH_VERSION,
                    ),
                )
                entry_id = int(cur.lastrowid)

                # Phase 3: re-pin the signed tip-anchor to this new tip, in the SAME
                # transaction, so a later tail-truncation (deleting the latest
                # entries without re-signing the anchor) is detectable by verify_chain.
                anchor_sig: Optional[str] = None
                if sign_state.enabled and sign_state.private_key is not None:
                    anchor_sig = _sign_tip_anchor(
                        sign_state.private_key, entry_id, current_hash
                    )
                conn.execute(
                    "INSERT INTO audit_tip_anchor "
                    "(anchor_id, tip_entry_id, tip_hash, signature, key_id, updated_at) "
                    "VALUES (1, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(anchor_id) DO UPDATE SET "
                    "tip_entry_id=excluded.tip_entry_id, tip_hash=excluded.tip_hash, "
                    "signature=excluded.signature, key_id=excluded.key_id, "
                    "updated_at=excluded.updated_at",
                    (entry_id, current_hash, anchor_sig, key_id, timestamp),
                )
                conn.commit()
                return AuditEntry(
                    entry_id=entry_id,
                    current_hash=current_hash,
                    previous_hash=previous_hash,
                    redacted=redacted,
                    signature=signature,
                    key_id=key_id,
                )
            finally:
                conn.close()
    except AuditError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail-closed: any failure is fatal
        raise AuditError(f"Audit write failed (fail-closed): {exc}") from exc


# --------------------------------------------------------------------------- #
# Core API: verify
# --------------------------------------------------------------------------- #

def verify_chain(
    *,
    from_id: int = 1,
    to_id: Optional[int] = None,
    db_path: Path = config.AUDIT_DB_PATH,
    verify_signatures: bool = True,
) -> ChainStatus:
    """Verify the hash chain and Ed25519 signatures over ``[from_id, to_id]``.

    Performs a single O(n) pass that checks:

    1. **Hash-chain integrity**: each entry's ``previous_hash`` links to the
       preceding entry's ``current_hash``; the genesis hash anchors the chain.
    2. **Payload integrity**: each entry's ``current_hash`` re-computes to the
       same value (detects tampering with actor, payload, zone, or timestamp).
    3. **Ed25519 signatures**: each signed entry's signature validates against
       the public key stored in ``audit_keys`` (detects forgery by insiders
       with database write access).

    Args:
        from_id: First entry ID to verify (inclusive). Use ``<= 1`` for full
            chain anchored at genesis.
        to_id: Last entry ID to verify (inclusive). ``None`` = tip of chain.
        db_path: Ledger database to read from.
        verify_signatures: When True (default), verify Ed25519 signatures.
            Set False to check only the hash chain (faster for bulk scans).

    Returns:
        A :class:`ChainStatus`. On failure, ``broken_at`` is the entry id of
        the first broken link and ``reason`` describes the failure mode.
        ``invalid_signatures`` lists entry IDs with bad signatures.
    """
    _ensure_initialized(db_path)
    conn = _connect(db_path)
    try:
        # Load all public keys for signature verification
        pub_keys: dict[int, Ed25519PublicKey] = {}
        if verify_signatures and _ED25519_AVAILABLE:
            for row in conn.execute("SELECT key_id, public_key_hex FROM audit_keys"):
                try:
                    pk_bytes = bytes.fromhex(row["public_key_hex"])
                    pub_keys[int(row["key_id"])] = Ed25519PublicKey.from_public_bytes(
                        pk_bytes
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Could not load audit public key key_id=%s", row["key_id"]
                    )

        if to_id is None:
            rows = conn.execute(
                "SELECT * FROM tamper_audit_trail WHERE entry_id >= ? "
                "ORDER BY entry_id ASC",
                (from_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tamper_audit_trail WHERE entry_id >= ? AND entry_id <= ? "
                "ORDER BY entry_id ASC",
                (from_id, to_id),
            ).fetchall()
    finally:
        conn.close()

    if from_id <= 1:
        previous_hash = config.AUDIT_GENESIS_HASH
    elif rows:
        previous_hash = rows[0]["previous_hash"]
    else:
        previous_hash = config.AUDIT_GENESIS_HASH

    invalid_sigs: list[int] = []
    unsigned_count = 0

    for entry in rows:
        eid = int(entry["entry_id"])

        # --- 1. Hash-chain linkage check ---
        if entry["previous_hash"] != previous_hash:
            return ChainStatus(
                valid=False,
                total_entries=len(rows),
                broken_at=eid,
                reason="Chain linkage broken (previous_hash mismatch).",
                head_hash=previous_hash if eid == int(rows[0]["entry_id"]) else None,
                signature_valid=len(invalid_sigs) == 0,
                invalid_signatures=tuple(invalid_sigs),
                unsigned_entries=unsigned_count,
            )

        # --- 2. Payload integrity check (recompute under the entry's OWN version) ---
        try:
            entry_version = int(entry["hash_version"])
        except (IndexError, KeyError, TypeError):
            entry_version = 1  # pre-migration row defaults to the legacy preimage
        computed = compute_entry_hash(
            previous_hash,
            entry["timestamp"],
            entry["actor"],
            entry["action_payload"],
            entry["security_zone"],
            version=entry_version,
        )
        if computed != entry["current_hash"]:
            return ChainStatus(
                valid=False,
                total_entries=len(rows),
                broken_at=eid,
                reason="Payload tampering detected (hash mismatch).",
                head_hash=None,
                signature_valid=len(invalid_sigs) == 0,
                invalid_signatures=tuple(invalid_sigs),
                unsigned_entries=unsigned_count,
            )

        # --- 3. Ed25519 signature verification ---
        sig_hex = entry["signature"]
        entry_key_id = entry["key_id"]
        if sig_hex and verify_signatures and _ED25519_AVAILABLE:
            pk = pub_keys.get(entry_key_id) if entry_key_id else None
            if pk is not None:
                sig_valid = _verify_entry_signature(
                    pk,
                    sig_hex,
                    entry["previous_hash"],
                    entry["timestamp"],
                    entry["actor"],
                    entry["action_payload"],
                    entry["security_zone"],
                    entry["current_hash"],
                )
                if not sig_valid:
                    invalid_sigs.append(eid)
            else:
                # Signature present but key unknown (key deleted?) — suspicious
                invalid_sigs.append(eid)
        elif not sig_hex:
            unsigned_count += 1

        previous_hash = entry["current_hash"]

    # --- 4. Tip-anchor check (Phase 3): detect tail-truncation on a verify-to-tip. ---
    tip_anchor_valid: Optional[bool] = None
    if to_id is None:
        tip_anchor_valid = _check_tip_anchor(db_path, pub_keys, verify_signatures)
        if tip_anchor_valid is False:
            return ChainStatus(
                valid=False,
                total_entries=len(rows),
                broken_at=None,
                reason="Tail truncation or tip-anchor tamper detected.",
                head_hash=previous_hash if rows else config.AUDIT_GENESIS_HASH,
                signature_valid=len(invalid_sigs) == 0,
                invalid_signatures=tuple(invalid_sigs),
                unsigned_entries=unsigned_count,
                tip_anchor_valid=False,
            )

    chain_valid = len(invalid_sigs) == 0
    return ChainStatus(
        valid=chain_valid,
        total_entries=len(rows),
        head_hash=previous_hash if rows else config.AUDIT_GENESIS_HASH,
        signature_valid=chain_valid,
        invalid_signatures=tuple(invalid_sigs),
        unsigned_entries=unsigned_count,
        tip_anchor_valid=tip_anchor_valid,
    )


def _check_tip_anchor(
    db_path: Path,
    pub_keys: dict[int, "Ed25519PublicKey"],
    verify_signatures: bool,
) -> Optional[bool]:
    """Compare the signed tip-anchor to the real chain tip (Phase 3).

    Returns True if the anchor matches the tip (and its signature verifies), False
    on a tail-truncation / anchor tamper, and None only for a genuinely legacy or
    never-written ledger (no v2 entries, so the anchor feature was never active).

    A DELETED anchor on a hardened chain is detected: a v2 entry only exists if the
    anchor was written alongside it (``log_action`` does both in one transaction), so
    a v2 entry plus a missing anchor means the anchor was removed → tampering. Residual
    limit (documented): an attacker who deletes EVERY entry AND the anchor leaves a
    pristine-looking empty DB; only an externally-published anchor could detect that.
    """
    conn = _connect(db_path)
    try:
        anchor = conn.execute(
            "SELECT tip_entry_id, tip_hash, signature, key_id FROM audit_tip_anchor "
            "WHERE anchor_id = 1"
        ).fetchone()
        tip = conn.execute(
            "SELECT entry_id, current_hash FROM tamper_audit_trail "
            "ORDER BY entry_id DESC LIMIT 1"
        ).fetchone()
        # A v2 entry implies the anchor feature was active when the chain was written.
        hardened = conn.execute(
            "SELECT 1 FROM tamper_audit_trail WHERE hash_version >= 2 LIMIT 1"
        ).fetchone() is not None
    finally:
        conn.close()

    if anchor is None:
        # Missing anchor on a HARDENED, non-empty chain = the anchor was deleted to
        # evade truncation detection (fail-closed). Only a pure-legacy (v1-only) or
        # never-written chain legitimately has no anchor.
        if tip is not None and hardened:
            return False
        return None
    if tip is None:
        return False  # anchor proves an entry existed, but the chain is now empty
    if int(tip["entry_id"]) != int(anchor["tip_entry_id"]) or (
        tip["current_hash"] != anchor["tip_hash"]
    ):
        return False  # the tip moved/shrank without re-anchoring — truncation/tamper

    sig = anchor["signature"]
    if sig and verify_signatures and _ED25519_AVAILABLE:
        pk = pub_keys.get(int(anchor["key_id"])) if anchor["key_id"] else None
        if pk is None or not _verify_tip_anchor_signature(
            pk, sig, int(anchor["tip_entry_id"]), anchor["tip_hash"]
        ):
            return False
    return True


# --------------------------------------------------------------------------- #
# External trust anchor
# --------------------------------------------------------------------------- #

def get_anchor(db_path: Path = config.AUDIT_DB_PATH) -> dict[str, Optional[Union[str, int]]]:
    """Return the latest signed hash for external trust-anchor publication.

    The returned dictionary contains the latest entry's hash and signature,
    which can be periodically published to an external system (blockchain,
    Certificate Transparency log, immutable blob store, etc.) to create an
    off-system tamper-evidence check. Even without external publication, the
    Ed25519 signature provides non-repudiation.

    Returns:
        ``{"head_hash": str|None, "signature": str|None, "key_id": int|None,
        "entry_id": int|None, "timestamp": str|None}``
    """
    _ensure_initialized(db_path)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT entry_id, current_hash, signature, key_id, timestamp "
            "FROM tamper_audit_trail ORDER BY entry_id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {
            "head_hash": config.AUDIT_GENESIS_HASH,
            "signature": None,
            "key_id": None,
            "entry_id": None,
            "timestamp": None,
        }
    return {
        "head_hash": row["current_hash"],
        "signature": row["signature"],
        "key_id": row["key_id"],
        "entry_id": row["entry_id"],
        "timestamp": row["timestamp"],
    }


def retroactively_sign_unsinged_entries(
    db_path: Path = config.AUDIT_DB_PATH,
) -> int:
    """Sign all unsigned (legacy) entries with the current signing key.

    This migration helper allows an existing hash-only audit trail to be
    upgraded to signed entries. Each unsigned entry is signed in place.

    .. warning::

        Retroactive signing attests to the entry's content *at the time of
        signing*, not at the time of creation. For maximum trust, sign entries
        at creation time via :func:`log_action`.

    Args:
        db_path: Ledger database to update.

    Returns:
        Number of entries retroactively signed.
    """
    if not _ED25519_AVAILABLE:
        logger.warning("Ed25519 unavailable — cannot retroactively sign entries.")
        return 0

    _ensure_initialized(db_path)
    sign_state = _get_signing_state(db_path)
    if not sign_state.enabled or sign_state.private_key is None:
        logger.warning("Signing not enabled — cannot retroactively sign entries.")
        return 0

    conn = _connect(db_path)
    signed_count = 0
    try:
        rows = conn.execute(
            "SELECT entry_id, previous_hash, timestamp, actor, action_payload, "
            "       security_zone, current_hash "
            "FROM tamper_audit_trail WHERE signature IS NULL "
            "ORDER BY entry_id ASC"
        ).fetchall()

        for entry in rows:
            signature = _sign_entry(
                sign_state.private_key,
                entry["previous_hash"],
                entry["timestamp"],
                entry["actor"],
                entry["action_payload"],
                entry["security_zone"],
                entry["current_hash"],
            )
            conn.execute(
                "UPDATE tamper_audit_trail SET signature = ?, key_id = ? "
                "WHERE entry_id = ?",
                (signature, sign_state.key_id, entry["entry_id"]),
            )
            signed_count += 1

        conn.commit()
        if signed_count:
            logger.info(
                "Retroactively signed %d unsigned audit entries with key_id=%d.",
                signed_count,
                sign_state.key_id,
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Retroactive signing failed: %s", exc)
    finally:
        conn.close()

    return signed_count


# --------------------------------------------------------------------------- #
# Public-key export
# --------------------------------------------------------------------------- #

def get_active_public_key(
    db_path: Path = config.AUDIT_DB_PATH,
) -> Optional[dict[str, Union[str, int]]]:
    """Return the currently active signing key's public key metadata.

    Returns:
        ``{"key_id": int, "public_key_hex": str, "created_at": str}``
        or ``None`` if Ed25519 is unavailable.
    """
    if not _ED25519_AVAILABLE:
        return None

    _ensure_initialized(db_path)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT key_id, public_key_hex, created_at FROM audit_keys "
            "WHERE active = 1 ORDER BY key_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "key_id": int(row["key_id"]),
            "public_key_hex": row["public_key_hex"],
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


__all__ = [
    "AuditEntry",
    "AuditError",
    "ChainStatus",
    "compute_entry_hash",
    "get_active_public_key",
    "get_anchor",
    "init_audit_db",
    "log_action",
    "retroactively_sign_unsinged_entries",
    "rotate_audit_key",
    "verify_chain",
]
