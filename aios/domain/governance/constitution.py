"""Canonical, versioned, digest-bearing constitution snapshot (Slice 26).

`aios.policy.constitution.Constitution` remains the live, config-derived
policy view every enforcement call site already uses -- this module does not
replace or duplicate its logic. It wraps that same view in a durable,
versioned, ratifiable envelope that separates immutable foundation laws from
mutable adaptive policy, and gives every authoritative record something
stable to carry: a `constitution_digest`.

Foundation laws are a fixed module constant, not sourced from `aios.config`
or any other mutable input -- there is no configuration knob or model output
that can alter them. `ConstitutionSnapshotV1` enforces this by rejecting
construction with any other set of laws.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from aios.policy.constitution import Constitution

#: The six non-negotiable foundation laws. Fixed order, fixed wording.
#: Nothing in this module reads these from config, the database, or a model
#: response -- they are a Python source constant.
FOUNDATION_LAWS: tuple[str, ...] = (
    "intelligence is not authority",
    "no model self-approval",
    "no secret transmission without policy permission",
    "no promotion without authoritative verification",
    "human can stop, revoke and correct",
    "unverified memory is not truth",
)


class PolicyReference(BaseModel):
    """A named pointer into the mutable adaptive-policy surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    digest: str = Field(min_length=64, max_length=64)


class ConstitutionSnapshotV1(BaseModel):
    """Durable, versioned constitutional authority object.

    Every field except `snapshot_digest` and `created_at` is included in the
    digest computed by `build_constitution_snapshot`; `snapshot_digest` is the
    result, and `created_at` is non-authoritative bookkeeping (mirrors the
    exclusion convention `MissionContract.digest()` already uses).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    constitution_id: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    foundation_laws: tuple[str, ...]
    policy_references: tuple[PolicyReference, ...]
    scope_roots: tuple[str, ...]
    frozen_paths: tuple[str, ...]
    provider_policy_digest: str = Field(min_length=64, max_length=64)
    autonomy_policy_digest: str = Field(min_length=64, max_length=64)
    created_at: str
    ratified_by_operator_id: str = Field(min_length=1, max_length=256)
    previous_snapshot_digest: str | None = None
    snapshot_digest: str = Field(min_length=64, max_length=64)

    @field_validator("foundation_laws")
    @classmethod
    def _foundation_laws_are_immutable(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(value) != FOUNDATION_LAWS:
            raise ValueError(
                "foundation_laws must exactly equal the canonical FOUNDATION_LAWS; "
                "they cannot be changed through config or model output"
            )
        return value

    def as_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


def _canonical_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _provider_policy_digest(constitution: "Constitution") -> str:
    return _canonical_digest(
        {
            "router_cloud_tasks": sorted(constitution.router_cloud_tasks),
            "router_max_cost": constitution.router_max_cost,
            "router_prefer_local": constitution.router_prefer_local,
            "router_llm_pick": constitution.router_llm_pick,
        }
    )


def _autonomy_policy_digest(constitution: "Constitution") -> str:
    return _canonical_digest(
        {
            "earned_autonomy_enabled": constitution.earned_autonomy_enabled,
            "earned_autonomy_min_successes": constitution.earned_autonomy_min_successes,
            "plan_stage_enabled": constitution.plan_stage_enabled,
            "policy_engine_enabled": constitution.policy_engine_enabled,
            "resource_mode": str(constitution.resource_mode),
        }
    )


def build_constitution_snapshot(
    *,
    ratified_by_operator_id: str,
    constitution: "Constitution | None" = None,
    previous_snapshot: ConstitutionSnapshotV1 | None = None,
) -> ConstitutionSnapshotV1:
    """Build a versioned, digested constitution snapshot.

    Ratification here is bootstrap-only: the caller supplies the exact
    operator id this snapshot is attributed to. A durable, human-ratified
    amendment ceremony that can change the *adaptive* policy fields across
    versions (without touching the immutable foundation laws) is Slice 37's
    Constitutional Amendment Authority; this function only builds the
    envelope, it does not persist a chain across process restarts.

    The import of `aios.policy.constitution` is deferred to call time: that
    module transitively imports `aios.policy` -> `aios.policy.kernel` ->
    ... -> `aios.application.governance`, which imports back from this
    package. Importing it at call time (after every package has finished
    its own module-level initialization) avoids that cycle entirely, rather
    than depending on `aios/domain/governance/__init__.py` import order.
    """
    if not ratified_by_operator_id.strip():
        raise ValueError("ratified_by_operator_id is required")

    from aios.policy.constitution import build_constitution

    live = constitution if constitution is not None else build_constitution()
    provider_digest = _provider_policy_digest(live)
    autonomy_digest = _autonomy_policy_digest(live)
    policy_references = (
        PolicyReference(name="provider_and_routing_policy", digest=provider_digest),
        PolicyReference(name="autonomy_policy", digest=autonomy_digest),
    )

    constitution_id = (
        previous_snapshot.constitution_id
        if previous_snapshot is not None
        # Deterministic (not a fresh random uuid) so repeated calls for the
        # same operator with unchanged policy produce an identical digest --
        # without that, constitution_digest could never be compared for
        # equality across two separately-stamped records, defeating its
        # entire purpose. A durable, persisted lineage that survives
        # process restarts is Slice 37's job; this is a stable-per-operator
        # bootstrap identity in the meantime.
        else f"constitution:{ratified_by_operator_id}"
    )
    version = previous_snapshot.version + 1 if previous_snapshot is not None else 1
    previous_digest = (
        previous_snapshot.snapshot_digest if previous_snapshot is not None else None
    )
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    digest_payload = {
        "constitution_id": constitution_id,
        "version": version,
        "foundation_laws": list(FOUNDATION_LAWS),
        "policy_references": [
            {"name": ref.name, "digest": ref.digest} for ref in policy_references
        ],
        "scope_roots": sorted(live.scope_roots),
        "frozen_paths": sorted(live.frozen_path_prefixes),
        "provider_policy_digest": provider_digest,
        "autonomy_policy_digest": autonomy_digest,
        "ratified_by_operator_id": ratified_by_operator_id,
        "previous_snapshot_digest": previous_digest,
    }
    snapshot_digest = _canonical_digest(digest_payload)

    return ConstitutionSnapshotV1(
        constitution_id=constitution_id,
        version=version,
        foundation_laws=FOUNDATION_LAWS,
        policy_references=policy_references,
        scope_roots=tuple(live.scope_roots),
        frozen_paths=tuple(live.frozen_path_prefixes),
        provider_policy_digest=provider_digest,
        autonomy_policy_digest=autonomy_digest,
        created_at=created_at,
        ratified_by_operator_id=ratified_by_operator_id,
        previous_snapshot_digest=previous_digest,
        snapshot_digest=snapshot_digest,
    )


def snapshot_digest_from_record(snapshot: ConstitutionSnapshotV1) -> str:
    """Recompute the canonical digest from an already-built snapshot's own
    fields, reproducing `build_constitution_snapshot()`'s exact
    `digest_payload` shape (same field set, same sorted scope_roots/
    frozen_paths, `created_at` excluded). Used by `ConstitutionSnapshotStore`
    to detect a row tampered with outside the store, the same tamper-
    detection shape `DeliberationStore`/`RepresentativeContextStore` use."""
    payload = {
        "constitution_id": snapshot.constitution_id,
        "version": snapshot.version,
        "foundation_laws": list(snapshot.foundation_laws),
        "policy_references": [
            {"name": ref.name, "digest": ref.digest}
            for ref in snapshot.policy_references
        ],
        "scope_roots": sorted(snapshot.scope_roots),
        "frozen_paths": sorted(snapshot.frozen_paths),
        "provider_policy_digest": snapshot.provider_policy_digest,
        "autonomy_policy_digest": snapshot.autonomy_policy_digest,
        "ratified_by_operator_id": snapshot.ratified_by_operator_id,
        "previous_snapshot_digest": snapshot.previous_snapshot_digest,
    }
    return _canonical_digest(payload)


__all__ = [
    "FOUNDATION_LAWS",
    "PolicyReference",
    "ConstitutionSnapshotV1",
    "build_constitution_snapshot",
    "snapshot_digest_from_record",
]
