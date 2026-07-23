"""PrivacyAuditTracker: a bounded, process-local record of PrivacyFilter audits.

Organ 50 (second half): "what was sent / what was removed" for the most
recent real cloud calls. `PrivacyFilter.filter()` (`aios/core/privacy_filter.py`)
already computes a real per-call audit dict (redaction counts); until now that
audit was only ever passed to `logger.info()` and discarded. This tracker gives
each of the 5 real call sites (`FailoverChatClient` plus the 4 direct cloud
clients) somewhere queryable to record it, instead of a second logging sink.

In-memory-only by design, matching `ProviderHealthTracker`'s own
already-documented convention (Slice 31) -- diagnostic data, not authoritative
state; no new durability promise this tracker owes.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PrivacyAuditRecord:
    """One real `PrivacyFilter.filter()` call's outcome."""

    provider: str
    audit: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(default_factory=_utc_now)


class PrivacyAuditTracker:
    """Bounded, process-local ring buffer of the most recent privacy audits."""

    def __init__(self, *, max_records: int = 50) -> None:
        self._records: deque[PrivacyAuditRecord] = deque(maxlen=max(1, int(max_records)))

    def record(self, provider: str, audit: dict[str, Any]) -> None:
        """Append one real audit. Never raises -- a malformed *audit* is still
        recorded as-is (this is an observability sink, not a validator)."""
        self._records.appendleft(
            PrivacyAuditRecord(provider=str(provider), audit=dict(audit or {}))
        )

    def recent(self, *, limit: int = 10) -> list[PrivacyAuditRecord]:
        """The most recent audits, newest first."""
        return list(self._records)[: max(int(limit), 0)]


__all__ = ["PrivacyAuditRecord", "PrivacyAuditTracker"]
