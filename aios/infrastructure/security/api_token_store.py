"""SQLite persistence for API bearer-token rotation state.

Single durable row: this token gates the whole API surface for every
already-running client at once, so there is exactly one current/previous
pair, not a per-caller history.

Why the row is keyed (organ 53, 2026-09-02)
-------------------------------------------
This row is not bookkeeping -- it IS the credential-verification material for
the entire API surface. Until now it was a bare ``INSERT ... ON CONFLICT DO
UPDATE`` with no integrity of any kind, so anyone able to write the SQLite file
could set ``current_token_digest`` to the digest of a token they hold and
authenticate as the operator, **with nothing anywhere able to detect it**. The
route that performs a rotation does write an audit entry, but that records only
that a rotation happened; it does not bind the resulting digest, and it is
bypassed entirely by editing the file directly.

Every row is therefore stamped with an HMAC-SHA256 over its own contents, keyed
from a secret that lives only in the environment (AGENTS.md SS VII.4 -- never on
disk, never in ``.aios/``, never logged). A tampered row fails verification
because the attacker cannot recompute the tag without the key.

Failure posture, chosen deliberately
------------------------------------
An unverifiable row (tampered, unstamped, or no key configured) raises
``ApiTokenRotationTampered`` and the authority above treats it as *no rotation
state at all*: rotated tokens stop authenticating, while ``config.API_TOKEN``
keeps working exactly as it did before this organ existed.

That direction matters. Refusing everything on a tampered row would let an
attacker lock the operator out of their own API by corrupting one file; the
chosen posture means tampering can only ever REMOVE access to rotated tokens,
never grant it. Legacy rows written before this column existed carry a NULL tag
and are treated the same way -- unverifiable, therefore not trusted -- the same
posture organ 42 takes for pre-chain journal rows.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from aios.domain.security.api_token import ApiTokenRotationState

#: The environment variable holding the row-signing secret. Volatile by design.
ROTATION_KEY_ENV = "AIOS_API_TOKEN_ROTATION_KEY"

#: Mirrors VerificationAuthority._INSECURE_DEFAULT_KEYS: a key that is really a
#: placeholder is worse than an obvious absence, because it looks configured.
_INSECURE_DEFAULT_KEYS = frozenset(
    {
        "aios-api-token-rotation-key",
        "aios-authority-key",
        "changeme",
        "secret",
        "default",
    }
)

_MIN_KEY_LENGTH = 32


class ApiTokenRotationTampered(RuntimeError):
    """The stored rotation row could not be verified against its HMAC."""


def _resolve_rotation_key() -> str | None:
    """Return the row-signing secret, or None when it cannot be used.

    Returns None rather than raising so a deployment with no key configured
    degrades to "rotated tokens do not authenticate" instead of failing the
    whole API closed. The same test-environment escape the verification
    authority uses is honoured, so suites need no real secret.
    """
    key = os.environ.get(ROTATION_KEY_ENV, "")
    is_test = os.environ.get("AIOS_ENV", "").lower() in ("test", "testing", "ci")
    allow_insecure = bool(os.environ.get("AIOS_TEST_SIGNING_KEYS_ALLOWED", ""))
    if not key:
        if is_test or allow_insecure:
            return "test-api-token-rotation-key-placeholder-safe"
        return None
    if key in _INSECURE_DEFAULT_KEYS:
        return None
    if len(key) < _MIN_KEY_LENGTH and not (is_test or allow_insecure):
        return None
    return key


def _row_tag(state: ApiTokenRotationState, key: str) -> str:
    """HMAC-SHA256 over a canonical serialization of the row's own fields.

    JSON with sorted keys and fixed separators, so the material cannot drift
    with dict ordering or float formatting between writer and verifier.
    """
    material = json.dumps(
        {
            "current_token_digest": state.current_token_digest,
            "current_issued_at": state.current_issued_at,
            "previous_token_digest": state.previous_token_digest,
            "previous_expires_at": state.previous_expires_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(
        key.encode("utf-8"), material.encode("utf-8"), hashlib.sha256
    ).hexdigest()


class ApiTokenStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_token_rotation (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    current_token_digest TEXT NOT NULL,
                    current_issued_at REAL NOT NULL,
                    previous_token_digest TEXT,
                    previous_expires_at REAL,
                    row_hmac TEXT
                )
                """
            )
            # Idempotent migration for databases created before the column
            # existed. Their rows keep a NULL tag and are refused as
            # unverifiable rather than silently trusted.
            existing = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(api_token_rotation)")
            }
            if "row_hmac" not in existing:
                conn.execute("ALTER TABLE api_token_rotation ADD COLUMN row_hmac TEXT")
            conn.commit()

    def current(self) -> ApiTokenRotationState | None:
        """Return the verified rotation state, or None when none is stored.

        Raises:
            ApiTokenRotationTampered: the row exists but does not verify --
                tampered, unstamped, or no usable signing key configured.
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT current_token_digest, current_issued_at, "
                "previous_token_digest, previous_expires_at, row_hmac "
                "FROM api_token_rotation WHERE singleton_id = 1"
            ).fetchone()
        if row is None:
            return None

        state = ApiTokenRotationState(
            current_token_digest=str(row["current_token_digest"]),
            current_issued_at=float(row["current_issued_at"]),
            previous_token_digest=(
                str(row["previous_token_digest"])
                if row["previous_token_digest"] is not None
                else None
            ),
            previous_expires_at=(
                float(row["previous_expires_at"])
                if row["previous_expires_at"] is not None
                else None
            ),
        )

        stored_tag = row["row_hmac"]
        if stored_tag is None:
            raise ApiTokenRotationTampered(
                "api token rotation row carries no integrity tag; it predates "
                "row signing or was written by something that bypassed the store"
            )
        key = _resolve_rotation_key()
        if key is None:
            raise ApiTokenRotationTampered(
                f"api token rotation row cannot be verified: {ROTATION_KEY_ENV} is "
                "unset, too short, or a known placeholder"
            )
        if not hmac.compare_digest(str(stored_tag), _row_tag(state, key)):
            raise ApiTokenRotationTampered(
                "api token rotation row failed HMAC verification -- the stored "
                "credential material does not match its signature"
            )
        return state

    def save(self, state: ApiTokenRotationState) -> None:
        key = _resolve_rotation_key()
        if key is None:
            raise ApiTokenRotationTampered(
                f"refusing to persist API token rotation state: {ROTATION_KEY_ENV} "
                "is unset, too short, or a known placeholder, so the row could not "
                "be protected against direct modification"
            )
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO api_token_rotation (
                    singleton_id, current_token_digest, current_issued_at,
                    previous_token_digest, previous_expires_at, row_hmac
                ) VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    current_token_digest = excluded.current_token_digest,
                    current_issued_at = excluded.current_issued_at,
                    previous_token_digest = excluded.previous_token_digest,
                    previous_expires_at = excluded.previous_expires_at,
                    row_hmac = excluded.row_hmac
                """,
                (
                    state.current_token_digest,
                    state.current_issued_at,
                    state.previous_token_digest,
                    state.previous_expires_at,
                    _row_tag(state, key),
                ),
            )
            conn.commit()


__all__ = ["ApiTokenStore", "ApiTokenRotationTampered", "ROTATION_KEY_ENV"]
