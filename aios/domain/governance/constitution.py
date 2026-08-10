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
from typing import TYPE_CHECKING, Literal

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


#: The only constitutional fields an amendment may change in v1.
#:
#: Everything else in a snapshot is either derived (`version`, the digests,
#: `created_at`), identity (`constitution_id`, `ratified_by_operator_id`), or
#: unamendable by construction (`foundation_laws`, which
#: `_foundation_laws_are_immutable` rejects outright).
AMENDABLE_FIELDS: tuple[str, ...] = ("scope_roots", "frozen_paths")

#: Change shapes that can only ever make the system MORE constrained.
#:
#: Adding a frozen path freezes more. Removing a scope root shrinks where the
#: system may act at all. Both directions reduce what GAGOS can do to itself
#: and to the machine.
#:
#: The inverses -- unfreezing a path, widening scope -- are refused in v1 and
#: deliberately so. `frozen_paths` currently contains `aios/security/`; an
#: amendment that could remove it would be an amendment that unfreezes the
#: security spine, which is precisely the act the whole frozen-organ apparatus
#: exists to make impossible without ceremony that does not yet exist. A
#: mistaken tightening is recoverable -- `rollback_amendment` reverts to the
#: exact predecessor snapshot -- so the safe direction is also the reversible
#: one.
_PROTECTION_INCREASING: frozenset[tuple[str, str]] = frozenset(
    {("frozen_paths", "add"), ("scope_roots", "remove")}
)


class ConstitutionChangeV1(BaseModel):
    """One typed, applicable change to the constitution.

    This exists because `proposed_diff` is free prose and prose cannot be
    applied. Before this type, a ratified amendment produced a new snapshot
    that was byte-identical to its predecessor apart from the version counter:
    the ceremony was real, the capability check was real, and the change was
    a no-op. Three red-team campaigns hardened the road to a destination that
    did not exist.

    A closed vocabulary also removes the last surface the campaigns kept
    walking. "Who ratifies" stopped being writable as prose when
    `approval_model` became a type; "what changes" stops being writable as
    prose here. There is no paraphrase of an invalid enum member.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    target: Literal["scope_roots", "frozen_paths"]
    operation: Literal["add", "remove"]
    value: str = Field(min_length=1, max_length=4096)

    @field_validator("value")
    @classmethod
    def _value_is_a_plausible_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        if value != value.strip():
            raise ValueError("value must not be padded with whitespace")
        # A constitutional value ends up in a path-prefix comparison. A
        # control character there is either an encoding attack or a
        # copy-paste accident, and neither belongs in the constitution.
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
            raise ValueError("value must not contain control characters")
        return value

    def describes_a_permitted_direction(self) -> bool:
        return (self.target, self.operation) in _PROTECTION_INCREASING


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


def apply_constitution_changes(
    *,
    scope_roots: tuple[str, ...],
    frozen_paths: tuple[str, ...],
    changes: tuple[ConstitutionChangeV1, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Fold *changes* over the two amendable fields, in order.

    Pure and total: no I/O, no config, no clock. The caller owns whether the
    changes were permitted -- `activate_amendment` checks direction and refuses
    before ever reaching here -- so this only has to be a correct fold.

    Idempotent per change: adding a value already present, or removing one that
    is absent, is a no-op rather than an error. An amendment that restates the
    status quo is redundant, not invalid, and refusing it would make the
    ceremony fail on the safest possible input.
    """
    scopes = list(scope_roots)
    frozen = list(frozen_paths)
    buckets = {"scope_roots": scopes, "frozen_paths": frozen}
    for change in changes:
        bucket = buckets[change.target]
        if change.operation == "add":
            if change.value not in bucket:
                bucket.append(change.value)
        else:
            if change.value in bucket:
                bucket.remove(change.value)
    return tuple(scopes), tuple(frozen)


def build_constitution_snapshot(
    *,
    ratified_by_operator_id: str,
    constitution: "Constitution | None" = None,
    previous_snapshot: ConstitutionSnapshotV1 | None = None,
    changes: tuple[ConstitutionChangeV1, ...] = (),
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

    # The amendable fields carry forward from the predecessor when one exists,
    # so a change applied at version N is still present at version N+1. Before
    # this, every snapshot re-derived them from the live config, which is
    # exactly why a ratified amendment changed nothing: its content was
    # recomputed away the moment it was applied.
    base_scope_roots = (
        previous_snapshot.scope_roots
        if previous_snapshot is not None
        else tuple(live.scope_roots)
    )
    base_frozen_paths = (
        previous_snapshot.frozen_paths
        if previous_snapshot is not None
        else tuple(live.frozen_path_prefixes)
    )
    effective_scope_roots, effective_frozen_paths = apply_constitution_changes(
        scope_roots=base_scope_roots,
        frozen_paths=base_frozen_paths,
        changes=changes,
    )
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
        "scope_roots": sorted(effective_scope_roots),
        "frozen_paths": sorted(effective_frozen_paths),
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
        scope_roots=effective_scope_roots,
        frozen_paths=effective_frozen_paths,
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
