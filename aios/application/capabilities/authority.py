"""Server-issued exact capability authority."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from aios.domain.capabilities.contracts import Capability, CapabilityBinding
from aios.domain.capabilities.digest import payload_digest
from aios.infrastructure.capabilities.sqlite_store import CapabilityStore
from aios.security.secret_scanner import scan_and_redact


class CapabilityError(RuntimeError):
    """Raised when a capability is missing, altered, expired, or revoked."""


class CapabilityAuthority:
    """Issue and atomically consume opaque capabilities bound to one action."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        ttl_seconds: float = 120.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = CapabilityStore(db_path)
        self.ttl_seconds = max(float(ttl_seconds), 0.001)
        self.clock = clock

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue(
        self,
        binding: CapabilityBinding,
        *,
        action_payload: dict[str, Any] | None = None,
    ) -> str:
        if "*" in binding.scope:
            raise CapabilityError("wildcard capability scope is forbidden")
        if action_payload is not None:
            if payload_digest(action_payload) != binding.payload_digest:
                raise CapabilityError("capability action payload does not match its digest")
            scan = scan_and_redact(
                json.dumps(action_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            )
            if scan.detected:
                raise CapabilityError(
                    "capability action payload contains credential-like data"
                )
        now = self.clock()
        token = secrets.token_urlsafe(32)
        capability = Capability(
            capability_id=f"capability:{uuid.uuid4().hex}",
            binding=binding,
            issued_at=now,
            expires_at=now + self.ttl_seconds,
            nonce=secrets.token_urlsafe(16),
            action_payload=dict(action_payload) if action_payload is not None else None,
        )
        try:
            self.store.insert(capability, self._token_digest(token))
        except Exception as exc:  # noqa: BLE001 - authority fails closed
            raise CapabilityError("capability issuance failed") from exc
        return token

    def inspect(self, token: str) -> Capability:
        capability = self.store.by_token_digest(self._token_digest(token))
        if capability is None:
            raise CapabilityError("capability is unknown")
        return capability

    def consume(self, token: str, binding: CapabilityBinding) -> Capability:
        capability = self.inspect(token)
        now = self.clock()
        if capability.binding != binding:
            raise CapabilityError("capability binding mismatch")
        if capability.revoked_at is not None:
            raise CapabilityError("capability revoked")
        if capability.consumed_at is not None:
            raise CapabilityError("capability already consumed")
        if capability.expires_at <= now:
            raise CapabilityError("capability expired")
        if not self.store.consume_if_available(capability.capability_id, now):
            raise CapabilityError("capability already consumed, revoked, or expired")
        return replace(capability, consumed_at=now)

    def revoke(self, capability_id: str) -> None:
        if not self.store.revoke(capability_id, self.clock()):
            raise CapabilityError("capability is unavailable for revocation")

    def clear_grants(self, session_id: str, *, route: str) -> None:
        """Start a fresh replay chain without deleting the audit records."""
        if not session_id or not route:
            raise CapabilityError("grant cursor requires a session and route")
        self.store.clear_grants(session_id, route, self.clock())

    def grants(self, session_id: str, *, route: str) -> list[Capability]:
        """Return still-live consumed capabilities in the current replay chain."""
        if not session_id or not route:
            raise CapabilityError("grant lookup requires a session and route")
        return self.store.consumed_for_session(session_id, route, self.clock())

    def has_any_grant(self) -> bool:
        """Return whether the operator has ever consumed an exact capability."""
        return self.store.has_consumed()

    def consumed_count(self) -> int:
        """Return the durable number of consumed exact capabilities."""
        return self.store.consumed_count()
