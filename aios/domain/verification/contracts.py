"""Pure helpers for target-specific, fail-closed verification."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable


def aggregate_strength(strengths: Iterable[int]) -> int:
    values = [int(value) for value in strengths]
    return min(values) if values else 0


def evidence_is_fresh(observed_at: str, *, now: str, freshness_seconds: int) -> bool:
    try:
        observed = datetime.fromisoformat(observed_at)
        current = datetime.fromisoformat(now)
    except ValueError:
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age = (current - observed).total_seconds()
    return 0 <= age <= max(0, freshness_seconds)


__all__ = ["aggregate_strength", "evidence_is_fresh"]
