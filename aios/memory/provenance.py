"""Signed provenance for learned memory (plan Phase 3, slice 3a).

Every learned row -- a lesson, a chat memory, a fact, a skill, a reflex -- will
carry a record of where it came from: the source kind (``live``, ``harness`` or
``synthetic``), the principal, session, run and model, the evidence, the
approver, and the rows it was derived from. The record is signed with Ed25519,
and a row whose record does not verify is never recalled (slice 3c). See
``docs/learning/PHASE3_DESIGN.md``.

Signing proves ORIGIN, not safety: a fully provenanced lesson can still be
wrong (threat T13).

Keys
----
* **Private seeds come only from volatile environment variables**, one per
  source kind (``KEY_ENV``). A process signs only as the kinds whose seed it
  holds. The backend holds the live seed and a harness tool the harness seed, so
  a harness cannot mint a live row even if it tries: key separation is the
  enforcement, not a flag.
* **No seed, no signature.** Nothing here ever generates a key. The audit
  logger's ephemeral-key fallback is exactly what this must not copy: an
  unsigned row is simply never recalled.
* **Public keys are pinned outside the database** (``PUBLIC_KEYS_FILE``,
  committed by the operator), because a database cannot be its own trust root.
  An unreadable or malformed file pins nothing, so nothing verifies.

Nothing in this module prints, logs or stores a seed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from aios import config
from aios.memory.construction_ledger import record_construction
from aios.memory.learning_freeze import assert_learning_permitted

logger = logging.getLogger(__name__)

#: Where a learned row came from. ``live``: a real turn. ``harness``: a
#: learning harness (organic chain, ladder, red-team, payoff). ``synthetic``:
#: tests and fixtures.
SOURCE_KINDS = ("live", "harness", "synthetic")
#: The environment variable holding each kind's 32-byte Ed25519 seed, as hex.
KEY_ENV = {
    "live": "AIOS_LEARNING_KEY_LIVE",
    "harness": "AIOS_LEARNING_KEY_HARNESS",
    "synthetic": "AIOS_LEARNING_KEY_SYNTHETIC",
}
#: The operator-committed pinned public keys: ``{"keys": {kind: [hex, ...]}}``.
#: A list per kind, so a key can be rotated without orphaning older rows.
PUBLIC_KEYS_FILE = (
    Path(config.PROJECT_ROOT) / ".aios" / "state" / ("LEARNING_PUBLIC_KEYS.json")
)
#: Points the verifier at another pinned file. Read at call time, never at
#: import. For an isolated root -- a test session, a red-team mission child --
#: never for the live store, whose keys are the committed file.
PUBLIC_KEYS_ENV = "AIOS_LEARNING_PUBLIC_KEYS"
#: Which kinds each recall context admits. A live turn admits only live rows.
ADMITTED_KINDS = {
    "live": frozenset({"live"}),
    "harness": frozenset({"live", "harness"}),
    "synthetic": frozenset({"synthetic"}),
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def content_digest(fields: Mapping[str, Any]) -> str:
    """SHA-256 of a row's recall-relevant fields, including its status.

    Every field that changes what recall shows, or whether it shows it, must be
    in *fields*: a status flip the digest does not cover is a status flip no
    signature notices.
    """
    return hashlib.sha256(_canonical(dict(fields))).hexdigest()


def key_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Provenance:
    """Where one state of one learned row came from. Immutable once signed."""

    table: str
    row_id: str
    content_sha256: str
    source_kind: str
    transition: str
    principal: Optional[str] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    model: Optional[str] = None
    evidence_ref: Optional[str] = None
    approver: Optional[str] = None
    parents: tuple[str, ...] = ()
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(f"unknown source kind {self.source_kind!r}")
        # Order-free, so the same derivation always signs the same bytes.
        object.__setattr__(self, "parents", tuple(sorted(self.parents)))

    def signed_bytes(self) -> bytes:
        return hashlib.sha256(_canonical(asdict(self))).digest()

    def to_json(self) -> str:
        return _canonical(asdict(self)).decode("utf-8")

    @classmethod
    def from_json(cls, raw: str) -> "Provenance":
        data = json.loads(raw)
        data["parents"] = tuple(data.get("parents") or ())
        return cls(**data)


@dataclass(frozen=True)
class SignedProvenance:
    provenance: Provenance
    key_id: str
    signature: str


class LearningSigner:
    """Signs as the source kinds whose seed this process holds, and no other."""

    def __init__(self, seeds: Mapping[str, str]) -> None:
        self._keys: dict[str, Ed25519PrivateKey] = {}
        for kind, seed in seeds.items():
            if kind not in SOURCE_KINDS or not seed:
                continue
            try:
                self._keys[kind] = Ed25519PrivateKey.from_private_bytes(
                    bytes.fromhex(seed.strip())
                )
            except ValueError:
                # The seed is never echoed, only the variable's name.
                logger.error(
                    "%s is not a 64-hex-character Ed25519 seed; %s rows stay unsigned",
                    KEY_ENV[kind],
                    kind,
                )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "LearningSigner":
        env = os.environ if environ is None else environ
        return cls({kind: env.get(name, "") for kind, name in KEY_ENV.items()})

    @property
    def kinds(self) -> frozenset[str]:
        return frozenset(self._keys)

    def public_keys(self) -> dict[str, str]:
        """Public keys only, as hex, for pinning. Never a seed."""
        return {
            kind: key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
            for kind, key in self._keys.items()
        }

    def sign(self, provenance: Provenance) -> Optional[SignedProvenance]:
        """The signed record, or ``None`` when this process holds no key for its
        kind. ``None`` is not an error: an unsigned row is simply never recalled.
        """
        key = self._keys.get(provenance.source_kind)
        if key is None:
            return None
        return SignedProvenance(
            provenance=provenance,
            key_id=key_id(key.public_key()),
            signature=key.sign(provenance.signed_bytes()).hex(),
        )

    def __repr__(self) -> str:  # never the seeds
        return f"LearningSigner(kinds={sorted(self._keys)})"


@dataclass(frozen=True)
class Verdict:
    admitted: bool
    reason: str


class LearningVerifier:
    """Admits a row only on a signature under a PINNED key of an allowed kind,
    over the row's current content. Refuses everything else, and says why."""

    def __init__(self, pinned: Mapping[str, Iterable[str]]) -> None:
        self._keys: dict[str, tuple[str, Ed25519PublicKey]] = {}
        for kind, hexes in pinned.items():
            if kind not in SOURCE_KINDS:
                continue
            for raw in hexes:
                try:
                    public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(raw))
                except ValueError:
                    logger.error("a pinned %s public key is malformed; ignored", kind)
                    continue
                self._keys[key_id(public)] = (kind, public)

    @classmethod
    def from_pinned_file(cls, path: Path | None = None) -> "LearningVerifier":
        """Pinned keys from the committed file (or ``PUBLIC_KEYS_ENV``'s).

        Absent or malformed: none, so nothing verifies.
        """
        if path is not None:
            target = path
        else:
            override = os.environ.get(PUBLIC_KEYS_ENV, "").strip()
            target = Path(override) if override else PUBLIC_KEYS_FILE
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            keys = data["keys"]
            if not isinstance(keys, dict):
                raise TypeError("keys is not a mapping")
            return cls({str(k): list(v) for k, v in keys.items()})
        except FileNotFoundError:
            return cls({})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.error("pinned learning keys unreadable (%s); nothing verifies", exc)
            return cls({})

    def verify(
        self,
        signed: Optional[SignedProvenance],
        *,
        content_sha256: str,
        context: str,
    ) -> Verdict:
        if signed is None:
            return Verdict(False, "unsigned")
        pinned = self._keys.get(signed.key_id)
        if pinned is None:
            return Verdict(False, "unknown key")
        kind, public = pinned
        if kind != signed.provenance.source_kind:
            return Verdict(False, "key kind does not match the record's source kind")
        if kind not in ADMITTED_KINDS.get(context, frozenset()):
            return Verdict(
                False, f"{kind} rows are not admitted in a {context} context"
            )
        try:
            public.verify(
                bytes.fromhex(signed.signature), signed.provenance.signed_bytes()
            )
        except (InvalidSignature, ValueError):
            return Verdict(False, "bad signature")
        if signed.provenance.content_sha256 != content_sha256:
            return Verdict(False, "content changed since it was signed")
        return Verdict(True, "verified")


_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS learning_provenance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        row_table TEXT NOT NULL,
        row_id TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        key_id TEXT,
        signature TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_learning_provenance_row "
    "ON learning_provenance(row_table, row_id, id)",
    """
    CREATE TABLE IF NOT EXISTS learning_derivations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_table TEXT NOT NULL,
        child_id TEXT NOT NULL,
        parent_table TEXT NOT NULL,
        parent_id TEXT NOT NULL,
        relation TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
)


class ProvenanceStore:
    """Append-only records of provenance and derivation, beside the rows.

    Never updated and never deleted: a new state of a row appends a new record,
    and the verifier reads the newest. Every append asks the emergency stop
    first, like every learning write.
    """

    def __init__(self, database: Path | str) -> None:
        # R11: a physical store. Production builds exactly one, in bootstrap.py.
        record_construction("ProvenanceStore")
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            for statement in _SCHEMA:
                connection.execute(statement)

    def append(self, provenance: Provenance, signed: Optional[SignedProvenance]) -> int:
        """Record one state of one row, signed or not. Returns the record id."""
        assert_learning_permitted("learning_provenance.append")
        if signed is not None and signed.provenance != provenance:
            raise ValueError("the signature is over a different provenance record")
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO learning_provenance (row_table, row_id, content_sha256, "
                "provenance_json, key_id, signature, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    provenance.table,
                    provenance.row_id,
                    provenance.content_sha256,
                    provenance.to_json(),
                    None if signed is None else signed.key_id,
                    None if signed is None else signed.signature,
                    _utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def latest(self, table: str, row_id: str) -> Optional[SignedProvenance]:
        """The newest SIGNED record for a row, or ``None``.

        An unsigned record is a fact about the write, not a credential: a newer
        unsigned state means the row changed with no key present, so it must not
        inherit an older signature. That case returns ``None`` too.
        """
        with self._connection() as connection:
            row = connection.execute(
                "SELECT provenance_json, key_id, signature FROM learning_provenance "
                "WHERE row_table = ? AND row_id = ? ORDER BY id DESC LIMIT 1",
                (table, str(row_id)),
            ).fetchone()
        if row is None or not row["signature"] or not row["key_id"]:
            return None
        return SignedProvenance(
            provenance=Provenance.from_json(row["provenance_json"]),
            key_id=str(row["key_id"]),
            signature=str(row["signature"]),
        )

    def append_derivation(
        self,
        *,
        child: tuple[str, str],
        parent: tuple[str, str],
        relation: str,
    ) -> int:
        assert_learning_permitted("learning_derivations.append")
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO learning_derivations (child_table, child_id, "
                "parent_table, parent_id, relation, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    child[0],
                    str(child[1]),
                    parent[0],
                    str(parent[1]),
                    relation,
                    _utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def parents_of(self, table: str, row_id: str) -> list[tuple[str, str, str]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT parent_table, parent_id, relation FROM learning_derivations "
                "WHERE child_table = ? AND child_id = ? ORDER BY id",
                (table, str(row_id)),
            ).fetchall()
        return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


__all__ = [
    "ADMITTED_KINDS",
    "KEY_ENV",
    "LearningSigner",
    "LearningVerifier",
    "PUBLIC_KEYS_ENV",
    "PUBLIC_KEYS_FILE",
    "Provenance",
    "ProvenanceStore",
    "SOURCE_KINDS",
    "SignedProvenance",
    "Verdict",
    "content_digest",
    "key_id",
]
