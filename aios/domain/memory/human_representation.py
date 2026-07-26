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
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    status: Literal["proposed", "active", "superseded", "rejected", "withdrawn"] = (
        "proposed"
    )

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
    anything by itself. `operator_id` is honestly nullable -- a correction
    is reachable from a session that was never bound to a fully
    authenticated Human Sovereign principal, and this organ must record
    "unknown" rather than fabricate an identity when that is the case.
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
    operator_id: str | None = None
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



def _authenticated_correction_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class CorrectionProjectionV1(BaseModel):
    """One bounded, already-redacted correction value safe for model context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=1000)


class AuthenticatedCorrectionEventV1(BaseModel):
    """Immutable, session-bound correction lineage for representative chat.

    This sidecar deliberately leaves ``CorrectionRecordV1`` untouched: legacy
    correction metadata retains its original digest shape, while this event
    carries the authenticated, bounded projection that may reach a model.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1, max_length=200)
    correction_id: str = Field(min_length=1, max_length=200)
    base_revision: int = Field(ge=0)
    correction_revision: int = Field(ge=1)
    correction_record_digest: str = Field(min_length=64, max_length=64)
    prior_interpretation_digest: str = Field(min_length=64, max_length=64)
    conversation_session_digest: str = Field(min_length=64, max_length=64)
    operator_id: str = Field(min_length=1, max_length=256)
    operator_identity_digest: str = Field(min_length=64, max_length=64)
    authentication_event_id: str = Field(min_length=1, max_length=256)
    authentication_verifier: Literal["identity_service_session"] = (
        "identity_service_session"
    )
    event_kind: Literal["applied", "cleared"] = "applied"
    corrected_values: tuple[CorrectionProjectionV1, ...] = ()
    reason: str = Field(min_length=1, max_length=500)
    previous_correction_digest: str | None = Field(default=None, min_length=64, max_length=64)
    recorded_at: str = Field(default_factory=_utc_now)
    grants_authority: Literal[False] = False
    event_digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def _valid_event_shape(self) -> "AuthenticatedCorrectionEventV1":
        if self.event_kind == "applied" and not self.corrected_values:
            raise ValueError("applied authenticated correction requires values")
        if self.event_kind == "cleared" and self.corrected_values:
            raise ValueError("cleared authenticated correction cannot carry values")
        return self

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        correction_id: str,
        base_revision: int,
        correction_revision: int,
        correction_record_digest: str,
        prior_interpretation_digest: str,
        conversation_session_digest: str,
        operator_id: str,
        operator_identity_digest: str,
        authentication_event_id: str,
        corrected_values: tuple[CorrectionProjectionV1, ...],
        reason: str,
        previous_correction_digest: str | None,
        event_kind: Literal["applied", "cleared"] = "applied",
        recorded_at: str | None = None,
    ) -> "AuthenticatedCorrectionEventV1":
        payload: dict[str, Any] = {
            "event_id": event_id,
            "correction_id": correction_id,
            "base_revision": base_revision,
            "correction_revision": correction_revision,
            "correction_record_digest": correction_record_digest,
            "prior_interpretation_digest": prior_interpretation_digest,
            "conversation_session_digest": conversation_session_digest,
            "operator_id": operator_id,
            "operator_identity_digest": operator_identity_digest,
            "authentication_event_id": authentication_event_id,
            "authentication_verifier": "identity_service_session",
            "event_kind": event_kind,
            "corrected_values": [value.model_dump(mode="json") for value in corrected_values],
            "reason": reason,
            "previous_correction_digest": previous_correction_digest,
            "recorded_at": recorded_at or _utc_now(),
            "grants_authority": False,
        }
        return cls(
            **payload,
            event_digest=_authenticated_correction_digest(payload),
        )

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def authenticated_correction_event_digest_from_record(
    event: AuthenticatedCorrectionEventV1,
) -> str:
    return _authenticated_correction_digest(
        event.model_dump(mode="json", exclude={"event_digest"})
    )
__all__ = [
    "OperatorPreferenceV1",
    "ProjectPassportV1",
    "CorrectionRecordV1",
    "CorrectionProjectionV1",
    "AuthenticatedCorrectionEventV1",
    "authenticated_correction_event_digest_from_record",
    "HumanStateHypothesis",
]
