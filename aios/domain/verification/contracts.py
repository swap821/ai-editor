"""Pure helpers for target-specific, fail-closed verification."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VerifierSpec(BaseModel):
    """Versioned, structured invocation of an admitted deterministic verifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verifier_id: Literal["maintenance.rescan"] = "maintenance.rescan"
    version: Literal["1"] = "1"
    scanner_id: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
    )
    scanner_version: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
    )
    target_id: str = Field(min_length=1, max_length=512)
    rescan_of: str = Field(min_length=1, max_length=256)
    allowed_root: str = Field(min_length=1, max_length=4096)

    @field_validator("target_id", "rescan_of")
    @classmethod
    def _reject_shell_and_absolute_target_values(cls, value: str) -> str:
        if any(char in value for char in ";&|<>`\r\n\x00"):
            raise ValueError("verifier arguments must be shell-free")
        if value.startswith(("/", "\\")) or ":" in value[:3]:
            raise ValueError("verifier target arguments must be relative")
        return value

    @field_validator("allowed_root")
    @classmethod
    def _reject_shell_values(cls, value: str) -> str:
        if any(char in value for char in ";&|<>`\r\n\x00"):
            raise ValueError("verifier root must be shell-free")
        return value


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


__all__ = ["VerifierSpec", "aggregate_strength", "evidence_is_fresh"]
