"""Typed human-representation contracts (Slice 28: Human Representation Core).

Four organs, four contracts, all advisory unless stated otherwise:

- `OperatorPreferenceV1` wraps the existing confidence/contradiction lifecycle
  already implemented by `aios.memory.facts.SemanticFacts` (this module adds
  the missing typed fields -- `source_type`, `review_after`, `supersedes`,
  `contradicted_by` -- it does not reimplement contradiction detection).
- `ProjectPassportV1` wraps `aios.memory.project_passport.harvest_project_passport`
  with the missing identity/verification fields (`project_id`,
  `verified_at_commit`, `passport_digest`).
- `CorrectionRecordV1` wraps the existing revision lineage already implemented
  by `aios.memory.conversation.ConversationStateStore.record_correction`
  (before/after frame retained, `status` supersession) with a typed,
  digest-bearing record. `grants_authority` is pinned `Literal[False]`: a
  correction changes the recorded interpretation, never what is authorized.
- `HumanStateHypothesis` has no existing analog in this repo -- it is a new,
  deliberately narrow, non-authoritative signal. `grants_authority` and
  `user_correctable` are pinned literals for the same reason.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class OperatorPreferenceV1(BaseModel):
    """One observed or stated operator preference.

    Persisted through `aios.memory.facts.SemanticFacts` (subject
    `operator.<domain>.<key>`); this contract is the typed view `Slice 28`
    adds on top, not a replacement persistence layer.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    preference_id: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=200)
    key: str = Field(min_length=1, max_length=200)
    value: Any
    scope: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: Literal[
        "explicit_user",
        "human_correction",
        "observed_pattern",
        "verified_outcome",
    ]
    source_ids: tuple[str, ...] = ()
    valid_from: str = Field(default_factory=_utc_now)
    review_after: str | None = None
    supersedes: tuple[str, ...] = ()
    contradicted_by: tuple[str, ...] = ()
    status: Literal["proposed", "active", "superseded", "rejected"] = "proposed"

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProjectPassportV1(BaseModel):
    """Durable, digested view of `aios.memory.project_passport.ProjectPassport`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1, max_length=200)
    goal: str
    architecture_summary: str
    invariants: tuple[str, ...] = ()
    important_paths: tuple[str, ...] = ()
    commands: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    environments: tuple[str, ...] = ()
    current_phase: str = ""
    known_risks: tuple[str, ...] = ()
    explicit_human_decisions: tuple[str, ...] = ()
    verified_at_commit: str | None = None
    passport_digest: str = Field(min_length=64, max_length=64)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CorrectionRecordV1(BaseModel):
    """Typed view of one correction revision recorded by
    `aios.memory.conversation.ConversationStateStore`.

    The prior interpretation is retained by digest (never discarded), the
    current interpretation is recorded by digest, and `grants_authority` is
    fixed `False`: correcting how a request was understood never authorizes
    anything by itself.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    correction_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    base_revision: int = Field(ge=0)
    correction_revision: int = Field(ge=1)
    corrected_fields: tuple[str, ...]
    prior_interpretation_digest: str = Field(min_length=64, max_length=64)
    current_interpretation_digest: str = Field(min_length=64, max_length=64)
    source: Literal["user"] = "user"
    created_at: str = Field(default_factory=_utc_now)
    grants_authority: Literal[False] = False

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class HumanStateHypothesis(BaseModel):
    """A visible, correctable, non-authoritative guess at the operator's state.

    `user_correctable` and `grants_authority` are fixed literals -- no caller
    can construct a hypothesis that silently grants authority or hides
    itself from correction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal[
        "neutral",
        "exploratory",
        "decisive",
        "uncertain",
        "frustrated",
        "rushed",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    visible_reason: str = Field(min_length=1, max_length=1000)
    user_correctable: Literal[True] = True
    grants_authority: Literal[False] = False

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "OperatorPreferenceV1",
    "ProjectPassportV1",
    "CorrectionRecordV1",
    "HumanStateHypothesis",
]
