"""Slice 39: truthful projectors for the sovereignty/control read-model surface.

Each function assembles a `read_models` projection from a real object already
built in this plan -- `ConstitutionSnapshotV1` (Slice 26), `EmergencyStopState`
(Slice 27), `ProviderHealthSnapshot` (Slice 31), and `ApprovedAction` (the
existing production `ApprovalStore`, `aios/core/approvals.py`). Nothing here
invents a value: a field with no real source becomes `MetricStatus.UNAVAILABLE`,
never a guessed default, matching the same convention `aios/api/routes/mirror.py`
already uses for `development_tracker` metrics.
"""

from __future__ import annotations

from typing import Any

from aios.core.approvals import ApprovedAction
from aios.domain.governance.constitution import ConstitutionSnapshotV1
from aios.domain.governance.contracts import EmergencyStopState
from aios.domain.models.contracts import ProviderHealthSnapshot
from aios.domain.read_models.contracts import (
    ApprovalProjection,
    ConstitutionProjection,
    EmergencyStopProjection,
    MetricEnvelope,
    MetricStatus,
    ProviderHealthProjection,
)


def _measured(value: Any, source: str) -> MetricEnvelope:
    return MetricEnvelope(value=value, status=MetricStatus.MEASURED, source=source, freshness=0)


def _unavailable(source: str) -> MetricEnvelope:
    return MetricEnvelope(value=None, status=MetricStatus.UNAVAILABLE, source=source, freshness=None)


def project_constitution(snapshot: ConstitutionSnapshotV1 | None) -> ConstitutionProjection:
    """Project the active constitution, or all-`UNAVAILABLE` when none is loaded.

    A missing snapshot must never render as version 0 or an empty-but-present
    digest -- that would look like a ratified constitution with no laws.
    """
    source = "constitution_snapshot"
    if snapshot is None:
        return ConstitutionProjection(
            constitution_id=_unavailable(source),
            version=_unavailable(source),
            ratified_by_operator_id=_unavailable(source),
            snapshot_digest=_unavailable(source),
            foundation_laws_count=_unavailable(source),
        )
    return ConstitutionProjection(
        constitution_id=_measured(snapshot.constitution_id, source),
        version=_measured(snapshot.version, source),
        ratified_by_operator_id=_measured(snapshot.ratified_by_operator_id, source),
        snapshot_digest=_measured(snapshot.snapshot_digest, source),
        foundation_laws_count=_measured(len(snapshot.foundation_laws), source),
    )


def project_emergency_stop(state: EmergencyStopState) -> EmergencyStopProjection:
    """Project the emergency-stop latch. Always renderable -- a controller
    that has never been engaged still has a real, non-`None` `EmergencyStopState`
    (the dataclass default is `engaged=False`), so this path never needs an
    `UNAVAILABLE` fallback for the state itself. Only the optional per-field
    values (`reason`, `engaged_at`) go `UNAVAILABLE` when genuinely unset.
    """
    source = "emergency_stop_state"
    return EmergencyStopProjection(
        engaged=_measured(state.engaged, source),
        generation=_measured(state.generation, source),
        reason=_measured(state.reason, source) if state.reason else _unavailable(source),
        engaged_at=(
            _measured(state.engaged_at, source)
            if state.engaged_at is not None
            else _unavailable(source)
        ),
    )


def project_provider_health(snapshot: ProviderHealthSnapshot) -> ProviderHealthProjection:
    """Project one provider's circuit-breaker health from a real, reported snapshot.

    `budget_remaining=None` on the source snapshot means unknown cost (the
    domain contract's own documented convention) and must stay `UNAVAILABLE`
    here too -- never coerced to zero.
    """
    source = "provider_health_tracker"
    return ProviderHealthProjection(
        provider=snapshot.provider,
        reachable=_measured(snapshot.reachable, source),
        circuit_state=_measured(snapshot.circuit_state, source),
        recent_failure_count=_measured(snapshot.recent_failure_count, source),
        budget_remaining=(
            _measured(snapshot.budget_remaining, source)
            if snapshot.budget_remaining is not None
            else _unavailable(source)
        ),
    )


def project_approval(
    action: ApprovedAction,
    *,
    requesting_model: str | None = None,
    risk: str | None = None,
    scope: str | None = None,
    reversibility: str | None = None,
    verification_plan: str | None = None,
    constitution_version: int | None = None,
) -> ApprovalProjection:
    """Build the pinned decision surface for one pending approval.

    `action` is the real `ApprovedAction` the server already persisted via
    `ApprovalStore.issue` -- the one production authority path for a
    YELLOW-risk action awaiting a human decision (`aios/api/routes/actions.py`).
    That object does not carry model attribution, risk classification, blast
    radius, reversibility, or a verification plan today, so every one of
    those fields is `UNAVAILABLE` unless a caller supplies an already-computed
    real value -- this function never guesses one on its own.
    """
    source = "approval_store"
    mission_id = (
        action.payload.get("mission_id") if isinstance(action.payload, dict) else None
    )
    return ApprovalProjection(
        requested_action=_measured(action.action_type, source),
        requesting_model=(
            _measured(requesting_model, source) if requesting_model else _unavailable(source)
        ),
        mission_id=_measured(mission_id, source) if mission_id else _unavailable(source),
        risk=_measured(risk, source) if risk else _unavailable(source),
        scope=_measured(scope, source) if scope else _unavailable(source),
        reversibility=(
            _measured(reversibility, source) if reversibility else _unavailable(source)
        ),
        verification_plan=(
            _measured(verification_plan, source) if verification_plan else _unavailable(source)
        ),
        constitution_version=(
            _measured(constitution_version, source)
            if constitution_version is not None
            else _unavailable(source)
        ),
    )


__all__ = [
    "project_approval",
    "project_constitution",
    "project_emergency_stop",
    "project_provider_health",
]
