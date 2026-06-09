"""SHA-256 hash-chained, tamper-evident audit logger (Blueprint Section 07).

Every security-relevant action is appended to an append-only ledger in a
dedicated SQLite database. Each entry stores::

    current_hash = SHA256(previous_hash || timestamp || actor || payload || zone)

with the genesis entry chaining from 64 zero characters. Altering any historical
entry changes its hash, which breaks every subsequent link, so tampering is
detectable in O(n) by a single sequential pass (:func:`verify_chain`) — the same
guarantee as a blockchain, without distributed consensus.

Two trust principles are enforced here:

* **No secret persistence** — payloads are run through the secret scanner and
  redacted *before* they are hashed or stored, so credentials never enter the
  ledger (the hash is computed over the redacted text, keeping the chain
  internally consistent).
* **Fail-closed** — a logging failure raises :class:`AuditError`; the caller
  must treat an unrecorded action as a refused action.

The ledger lives in its own database (:data:`aios.config.AUDIT_DB_PATH`),
isolated from mutable memory so ordinary writes can never perturb the chain.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from aios import config
from aios.security.gateway import Zone
from aios.security.secret_scanner import scan_and_redact

#: Idempotent DDL for the ledger. The ``CHECK`` constraint makes an invalid zone
#: a database-level error, not just an application convention.
_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS tamper_audit_trail (
    entry_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    actor           TEXT NOT NULL,
    action_payload  TEXT NOT NULL,
    security_zone   TEXT NOT NULL CHECK (security_zone IN ('GREEN','YELLOW','RED')),
    current_hash    TEXT NOT NULL,
    previous_hash   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_zone ON tamper_audit_trail(security_zone);
CREATE INDEX IF NOT EXISTS idx_audit_time ON tamper_audit_trail(timestamp);
"""

#: Serialises appends within a process; SQLite BEGIN IMMEDIATE below extends the
#: same head-read + append critical section across local worker processes.
_append_lock = threading.Lock()
#: Databases whose schema has already been ensured this process.
_initialized: set[str] = set()


class AuditError(RuntimeError):
    """Raised when an audit write fails; signals the fail-closed policy."""


@dataclass(frozen=True)
class AuditEntry:
    """A freshly appended ledger entry."""

    entry_id: int
    current_hash: str
    previous_hash: str
    redacted: bool


@dataclass(frozen=True)
class ChainStatus:
    """Result of verifying (a range of) the hash chain."""

    valid: bool
    total_entries: int
    broken_at: Optional[int] = None
    reason: Optional[str] = None
    head_hash: Optional[str] = None


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a tuned connection to the audit database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = FULL;")
    return conn


def init_audit_db(db_path: Path = config.AUDIT_DB_PATH) -> None:
    """Create the ledger table and indexes if absent (idempotent)."""
    conn = _connect(db_path)
    try:
        conn.executescript(_AUDIT_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _ensure_initialized(db_path: Path) -> None:
    """Ensure the schema exists for *db_path*, at most once per process path."""
    key = str(db_path)
    if key not in _initialized:
        init_audit_db(db_path)
        _initialized.add(key)


def compute_entry_hash(
    previous_hash: str, timestamp: str, actor: str, payload: str, zone: str
) -> str:
    """Return ``SHA256(previous_hash || timestamp || actor || payload || zone)``."""
    raw = f"{previous_hash}{timestamp}{actor}{payload}{zone}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _zone_str(zone: Union[Zone, str]) -> str:
    """Normalise a zone (enum or string) to its canonical string value."""
    return zone.value if isinstance(zone, Zone) else str(zone)


def log_action(
    actor: str,
    payload: str,
    zone: Union[Zone, str] = Zone.YELLOW,
    *,
    db_path: Path = config.AUDIT_DB_PATH,
    redact_secrets: bool = True,
) -> AuditEntry:
    """Append one action to the tamper-evident ledger and return its entry.

    Args:
        actor: Component or human identity performing the action.
        payload: Serialised action description.
        zone: Security zone (``Zone`` enum or ``'GREEN'|'YELLOW'|'RED'``).
        db_path: Ledger database to append to.
        redact_secrets: When True (default), scrub credentials from *payload*
            before hashing and storage.

    Returns:
        The :class:`AuditEntry` that was written.

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
            conn = _connect(db_path)
            try:
                # Cross-process chain lock: no other writer can read the same
                # head and append a sibling link until this transaction commits.
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT current_hash FROM tamper_audit_trail "
                    "ORDER BY entry_id DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["current_hash"] if row else config.AUDIT_GENESIS_HASH
                timestamp = datetime.now(timezone.utc).isoformat()
                current_hash = compute_entry_hash(
                    previous_hash, timestamp, actor, stored_payload, zone_str
                )
                cur = conn.execute(
                    "INSERT INTO tamper_audit_trail "
                    "(timestamp, actor, action_payload, security_zone, "
                    " current_hash, previous_hash) VALUES (?, ?, ?, ?, ?, ?)",
                    (timestamp, actor, stored_payload, zone_str, current_hash, previous_hash),
                )
                conn.commit()
                return AuditEntry(
                    entry_id=int(cur.lastrowid),
                    current_hash=current_hash,
                    previous_hash=previous_hash,
                    redacted=redacted,
                )
            finally:
                conn.close()
    except AuditError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail-closed: any failure is fatal
        raise AuditError(f"Audit write failed (fail-closed): {exc}") from exc


def verify_chain(
    *,
    from_id: int = 1,
    to_id: Optional[int] = None,
    db_path: Path = config.AUDIT_DB_PATH,
) -> ChainStatus:
    """Verify the hash chain over ``[from_id, to_id]`` in a single O(n) pass.

    For a full verification (``from_id <= 1``) the walk is anchored at the
    genesis hash, so even tampering with the first entry is detected. For a
    partial range the first entry's stored ``previous_hash`` is used as the
    anchor.

    Returns:
        A :class:`ChainStatus`. On failure, ``broken_at`` is the entry id of the
        first broken link and ``reason`` describes the failure mode.
    """
    _ensure_initialized(db_path)
    conn = _connect(db_path)
    try:
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

    for entry in rows:
        if entry["previous_hash"] != previous_hash:
            return ChainStatus(
                valid=False,
                total_entries=len(rows),
                broken_at=int(entry["entry_id"]),
                reason="Chain linkage broken (previous_hash mismatch).",
            )
        computed = compute_entry_hash(
            previous_hash,
            entry["timestamp"],
            entry["actor"],
            entry["action_payload"],
            entry["security_zone"],
        )
        if computed != entry["current_hash"]:
            return ChainStatus(
                valid=False,
                total_entries=len(rows),
                broken_at=int(entry["entry_id"]),
                reason="Payload tampering detected (hash mismatch).",
            )
        previous_hash = entry["current_hash"]

    return ChainStatus(
        valid=True,
        total_entries=len(rows),
        head_hash=previous_hash if rows else config.AUDIT_GENESIS_HASH,
    )
