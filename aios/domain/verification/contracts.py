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
    def _reject_root_shell_values(cls, value: str) -> str:
        if any(char in value for char in ";&|<>`\r\n\x00"):
            raise ValueError("verifier root must be shell-free")
        return value


class SkillVerifierSpec(BaseModel):
    """Allowlisted verifier identity stored by an institutional skill."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verifier_id: Literal["skill.reuse"] = "skill.reuse"
    version: Literal["1"] = "1"
    target_pattern: str = Field(min_length=1, max_length=512)
    required_observations: tuple[str, ...] = Field(min_length=1, max_length=16)
    minimum_strength: int = Field(ge=1, le=4)

    @field_validator("target_pattern", "required_observations")
    @classmethod
    def _reject_skill_shell_values(cls, value):  # noqa: ANN001
        values = (value,) if isinstance(value, str) else value
        if any(any(char in item for char in ";&|<>`\r\n\x00") for item in values):
            raise ValueError("skill verifier values must be shell-free")
        if isinstance(value, str) and (
            value.startswith(("/", "\\")) or ":" in value[:3]
        ):
            raise ValueError("skill verifier target pattern must be relative")
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


__all__ = [
    "SkillVerifierSpec",
    "VerifierSpec",
    "aggregate_strength",
    "evidence_is_fresh",
]
