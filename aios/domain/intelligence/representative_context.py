"""RepresentativeContextV1 (Slice 29: Human Representative Context Compiler).

One provider-neutral, immutable, digested packet every model call should be
built from -- never a raw, uncompiled user prompt. Provider adapters may
reformat this into whatever wire shape a given API expects, but they may not
add authority, add secrets, widen scope, remove evidence requirements, or
silently alter a human decision recorded here.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PreferenceProjection(BaseModel):
    """A minimal, already-privacy-reviewed projection of one active
    `OperatorPreferenceV1` -- deliberately narrower than the full record
    (no `source_ids`, no `contradicted_by`) so a provider adapter cannot
    reconstruct the operator's full preference history from one context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str = Field(min_length=1, max_length=200)
    key: str = Field(min_length=1, max_length=200)
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)


class RepresentativeContextV1(BaseModel):
    """The complete, compiled context for exactly one model request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1, max_length=200)
    operator_identity_digest: str = Field(min_length=1, max_length=200)
    constitution_digest: str = Field(min_length=64, max_length=64)
    goal: str
    desired_outcome: str
    explicit_constraints: tuple[str, ...] = ()
    current_decisions: tuple[str, ...] = ()
    approved_preferences: tuple[PreferenceProjection, ...] = ()
    project_passport_digest: str | None = None
    relevant_memory_refs: tuple[str, ...] = ()
    privacy_classification: str = Field(min_length=1, max_length=100)
    cloud_allowed_fields: tuple[str, ...] = ()
    forbidden_fields: tuple[str, ...] = ()
    delegated_authority_summary: str
    permitted_tools: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    communication_mode: str = "direct"
    uncertainty: tuple[str, ...] = ()
    context_digest: str = Field(min_length=64, max_length=64)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")




class ContextExclusionV1(BaseModel):
    """A privacy-safe reason a candidate human-representation source was
    deliberately kept out of a request's compiled context.

    The receipt records source identity and a bounded reason code, never the
    excluded value itself. That makes the audit useful without turning the
    receipt into a second copy of sensitive operator data.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, max_length=100)
    field: str = Field(min_length=1, max_length=200)
    source_id: str | None = Field(default=None, max_length=200)
    reason: Literal[
        "expired",
        "withdrawn",
        "superseded",
        "scope_mismatch",
        "below_confidence_threshold",
        "stale",
        "privacy_redacted",
        "unavailable",
    ]


def _receipt_json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"unsupported receipt digest value: {type(value).__name__}")


def _canonical_receipt_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        default=_receipt_json_default,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class RepresentativeContextReceiptV1(BaseModel):
    """Append-only evidence describing how an authenticated context was built.

    This is intentionally a sidecar to RepresentativeContextV1. Older context
    rows have a canonical digest over their exact pre-receipt shape; embedding
    new receipt fields there would make valid historical rows look tampered
    after an upgrade.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1, max_length=200)
    context_digest: str = Field(min_length=64, max_length=64)
    operator_identity_digest: str = Field(min_length=1, max_length=200)
    constitution_digest: str = Field(min_length=64, max_length=64)
    target: Literal["local", "cloud"]
    active_project_revision: int | None = Field(default=None, ge=1)
    included_preference_ids: tuple[str, ...] = ()
    included_correction_ids: tuple[str, ...] = ()
    human_state_hypothesis_id: int | None = Field(default=None, ge=1)
    human_state_disposition: Literal["included", "abstained"]
    exclusions: tuple[ContextExclusionV1, ...] = ()
    consent_status: Literal[
        "not_required_local",
        "explicit_operator_consent",
        "policy_permitted_cloud",
    ]
    consent_scope: tuple[str, ...] = ()
    created_at: str = Field(min_length=1, max_length=64)
    expires_at: str = Field(min_length=1, max_length=64)
    receipt_digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def _valid_expiry_window(self) -> "RepresentativeContextReceiptV1":
        try:
            created = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("receipt timestamps must be ISO-8601") from exc
        if created.tzinfo is None or expires.tzinfo is None:
            raise ValueError("receipt timestamps must include a timezone")
        if expires <= created:
            raise ValueError("receipt expiry must be after creation")
        return self

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        context_digest: str,
        operator_identity_digest: str,
        constitution_digest: str,
        target: Literal["local", "cloud"],
        active_project_revision: int | None,
        included_preference_ids: tuple[str, ...] = (),
        included_correction_ids: tuple[str, ...] = (),
        human_state_hypothesis_id: int | None = None,
        human_state_disposition: Literal["included", "abstained"],
        exclusions: tuple[ContextExclusionV1, ...] = (),
        consent_status: Literal[
            "not_required_local",
            "explicit_operator_consent",
            "policy_permitted_cloud",
        ] = "not_required_local",
        consent_scope: tuple[str, ...] = (),
        created_at: str,
        expires_at: str,
    ) -> "RepresentativeContextReceiptV1":
        payload: dict[str, Any] = {
            "request_id": request_id,
            "context_digest": context_digest,
            "operator_identity_digest": operator_identity_digest,
            "constitution_digest": constitution_digest,
            "target": target,
            "active_project_revision": active_project_revision,
            "included_preference_ids": included_preference_ids,
            "included_correction_ids": included_correction_ids,
            "human_state_hypothesis_id": human_state_hypothesis_id,
            "human_state_disposition": human_state_disposition,
            "exclusions": exclusions,
            "consent_status": consent_status,
            "consent_scope": consent_scope,
            "created_at": created_at,
            "expires_at": expires_at,
        }
        digest_payload = payload

        return cls(
            **payload,
            receipt_digest=_canonical_receipt_digest(digest_payload),
        )

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def receipt_digest_from_record(receipt: RepresentativeContextReceiptV1) -> str:
    """Recompute the receipt's canonical digest for store-side tamper checks."""
    return _canonical_receipt_digest(
        receipt.model_dump(mode="json", exclude={"receipt_digest"})
    )


__all__ = [
    "ContextExclusionV1",
    "PreferenceProjection",
    "RepresentativeContextReceiptV1",
    "RepresentativeContextV1",
    "receipt_digest_from_record",
]
