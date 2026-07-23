"""API bearer-token rotation with a grace-period overlap.

The single shared ``AIOS_API_TOKEN`` gates the entire API surface for every
already-running client at once (the frontend, CLI tools, any external
integration). Rotating it the instant a new one is issued would break every
one of them simultaneously. Instead: the old token keeps working for a
bounded grace period after a new one is issued, so already-running
processes have a real window to pick up the new value before the old one
stops working -- operator-confirmed design (grace-period overlap, not an
immediate hard cutover).

``config.API_TOKEN`` itself stays valid unconditionally (unchanged from
before this organ existed) -- the operator retires it the normal way, by
restarting with a different env var. This authority only owns tokens
issued through an explicit ``rotate()`` call, layered on top. It never
caches ``config.API_TOKEN``'s value: every method takes the current value
as an explicit argument, so a process that legitimately reassigns it (or a
test that monkeypatches it) is always reflected immediately, with no stale
state baked into a long-lived singleton.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from pathlib import Path
from typing import Callable

from aios.domain.security.api_token import ApiTokenRotationState
from aios.infrastructure.security.api_token_store import ApiTokenStore


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ApiTokenAuthority:
    """Owns the durable, digest-only rotation state for the API bearer token."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = ApiTokenStore(db_path)
        self.clock = clock

    def is_configured(self, *, current_env_token: str = "") -> bool:
        return bool(current_env_token) or self.store.current() is not None

    def is_valid(self, candidate: str) -> bool:
        if not candidate:
            return False
        state = self.store.current()
        if state is None:
            return False
        candidate_digest = token_digest(candidate)
        if hmac.compare_digest(candidate_digest, state.current_token_digest):
            return True
        if (
            state.previous_token_digest is not None
            and state.previous_expires_at is not None
            and self.clock() < state.previous_expires_at
        ):
            return hmac.compare_digest(
                candidate_digest, state.previous_token_digest
            )
        return False

    def rotate(
        self, *, grace_period_seconds: float = 3600.0, current_env_token: str = ""
    ) -> str:
        """Issue a fresh token; the old one stays valid for the grace period.

        The very first rotation retires ``current_env_token`` (the live
        ``config.API_TOKEN`` at the moment of this call, if any) after the
        grace period; every rotation after that retires whatever the
        previous rotation issued. Returns the new RAW token -- shown exactly
        once, never persisted or logged in plaintext, matching
        IdentityService.enroll_operator()'s convention for one-time-visible
        credentials.
        """
        if grace_period_seconds < 0:
            raise ValueError("grace_period_seconds must be non-negative")
        current = self.store.current()
        previous_digest = (
            current.current_token_digest
            if current is not None
            else (token_digest(current_env_token) if current_env_token else None)
        )
        new_token = secrets.token_urlsafe(32)
        now = self.clock()
        self.store.save(
            ApiTokenRotationState(
                current_token_digest=token_digest(new_token),
                current_issued_at=now,
                previous_token_digest=previous_digest,
                previous_expires_at=(
                    now + grace_period_seconds if previous_digest is not None else None
                ),
            )
        )
        return new_token

    def current_state(self) -> ApiTokenRotationState | None:
        return self.store.current()


__all__ = ["ApiTokenAuthority", "token_digest"]
