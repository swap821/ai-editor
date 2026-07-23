"""Durable rotation state for the shared API bearer token.

Digest-only: the raw token is never stored, only its SHA-256 hash. The
previous token stays valid until ``previous_expires_at`` so an
already-running process holding the old value is not broken the instant a
new one is issued -- it has a bounded grace period to pick up the new value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ApiTokenRotationState:
    current_token_digest: str
    current_issued_at: float
    previous_token_digest: Optional[str] = None
    previous_expires_at: Optional[float] = None


__all__ = ["ApiTokenRotationState"]
