"""Slice 39: Truthful Read Models and Sovereign Interface (backend projectors).

Covers the invariants the brief cares about most: offline/missing state must
render as `UNAVAILABLE`, never a fabricated default; the emergency-stop
projection must always be renderable; and the approval projection can never
smuggle in an actual authority-granting field.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aios.application.capabilities.authority import CapabilityAuthority
from aios.application.models.health import ProviderHealthTracker
from aios.application.read_models.governance_projections import (
    KNOWN_PROVIDER_NAMES,
    project_approval,
    project_capability_approval,
    project_constitution,
    project_emergency_stop,
    project_pending_approvals,
    project_provider_health,
    project_provider_health_list,
)
from aios.core.approvals import ApprovedAction
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest
from aios.domain.governance.constitution import build_constitution_snapshot
from aios.domain.governance.contracts import EmergencyStopState
from aios.domain.models.contracts import ProviderHealthSnapshot
from aios.domain.read_models.contracts import ApprovalProjection, MetricStatus


# --------------------------------------------------------------------------- #
# project_constitution
# --------------------------------------------------------------------------- #


def test_constitution_projection_measured_from_real_snapshot():
    snapshot = build_constitution_snapshot(ratified_by_operator_id="operator-1")
    projection = project_constitution(snapshot)

    assert projection.version.status == MetricStatus.MEASURED
    assert projection.version.value == 1
    assert projection.constitution_id.value == snapshot.constitution_id
    assert projection.snapshot_digest.value == snapshot.snapshot_digest
    assert projection.foundation_laws_count.value == len(snapshot.foundation_laws)


def test_constitution_projection_missing_snapshot_is_unavailable_not_default():
    projection = project_constitution(None)

    for envelope in (
        projection.constitution_id,
        projection.version,
        projection.ratified_by_operator_id,
        projection.snapshot_digest,
        projection.foundation_laws_count,
    ):
        assert envelope.status == MetricStatus.UNAVAILABLE
        assert envelope.value is None

    # Must not silently render as version 0 / an empty digest.
    assert projection.version.value != 0
    assert projection.snapshot_digest.value != ""


def test_constitution_projection_two_operators_differ():
    a = project_constitution(build_constitution_snapshot(ratified_by_operator_id="op-a"))
    b = project_constitution(build_constitution_snapshot(ratified_by_operator_id="op-b"))
    assert a.snapshot_digest.value != b.snapshot_digest.value


# --------------------------------------------------------------------------- #
# project_emergency_stop
# --------------------------------------------------------------------------- #


def test_emergency_stop_projection_always_renderable_when_idle():
    state = EmergencyStopState()
    projection = project_emergency_stop(state)

    assert projection.engaged.status == MetricStatus.MEASURED
    assert projection.engaged.value is False
    assert projection.generation.value == 0
    # Never-set optional fields are honestly unavailable, not empty strings
    # or fabricated timestamps.
    assert projection.reason.status == MetricStatus.UNAVAILABLE
    assert projection.engaged_at.status == MetricStatus.UNAVAILABLE


def test_emergency_stop_projection_engaged_state_is_measured():
    state = EmergencyStopState(
        engaged=True,
        generation=3,
        reason="operator halt",
        engaged_at="2026-01-01T00:00:00+00:00",
    )
    projection = project_emergency_stop(state)

    assert projection.engaged.value is True
    assert projection.generation.value == 3
    assert projection.reason.status == MetricStatus.MEASURED
    assert projection.reason.value == "operator halt"
    assert projection.engaged_at.status == MetricStatus.MEASURED


# --------------------------------------------------------------------------- #
# project_provider_health
# --------------------------------------------------------------------------- #


def test_provider_health_projection_measured():
    snapshot = ProviderHealthSnapshot(
        provider="ollama",
        reachable=True,
        credential_valid=True,
        recent_failure_count=2,
        circuit_state="open",
        budget_remaining=12.5,
    )
    projection = project_provider_health(snapshot)

    assert projection.provider == "ollama"
    assert projection.reachable.value is True
    assert projection.circuit_state.value == "open"
    assert projection.recent_failure_count.value == 2
    assert projection.budget_remaining.status == MetricStatus.MEASURED
    assert projection.budget_remaining.value == 12.5


def test_provider_health_projection_unknown_budget_is_unavailable_not_zero():
    snapshot = ProviderHealthSnapshot(
        provider="anthropic",
        reachable=True,
        credential_valid=True,
        circuit_state="closed",
        budget_remaining=None,
    )
    projection = project_provider_health(snapshot)

    assert projection.budget_remaining.status == MetricStatus.UNAVAILABLE
    assert projection.budget_remaining.value is None
    assert projection.budget_remaining.value != 0


# --------------------------------------------------------------------------- #
# project_approval
# --------------------------------------------------------------------------- #


def test_approval_projection_measured_fields_from_real_approved_action():
    action = ApprovedAction(
        action_type="command",
        payload={"mission_id": "mission-123", "cmd": "pytest"},
        session_id="session-1",
    )
    projection = project_approval(
        action,
        requesting_model="claude-sonnet-5",
        risk="YELLOW",
        scope="repo:aios/**",
        reversibility="git revert",
        verification_plan="run focused tests then full suite",
        constitution_version=4,
    )

    assert projection.requested_action.value == "command"
    assert projection.mission_id.value == "mission-123"
    assert projection.requesting_model.value == "claude-sonnet-5"
    assert projection.risk.value == "YELLOW"
    assert projection.scope.value == "repo:aios/**"
    assert projection.reversibility.value == "git revert"
    assert projection.verification_plan.value == "run focused tests then full suite"
    assert projection.constitution_version.value == 4
    for envelope in (
        projection.requested_action,
        projection.mission_id,
        projection.requesting_model,
        projection.risk,
        projection.scope,
        projection.reversibility,
        projection.verification_plan,
        projection.constitution_version,
    ):
        assert envelope.status == MetricStatus.MEASURED


def test_approval_projection_unsupplied_fields_are_unavailable_not_guessed():
    action = ApprovedAction(
        action_type="edit",
        payload={},
        session_id="session-1",
    )
    projection = project_approval(action)

    assert projection.requested_action.status == MetricStatus.MEASURED
    assert projection.requested_action.value == "edit"
    for envelope in (
        projection.mission_id,
        projection.requesting_model,
        projection.risk,
        projection.scope,
        projection.reversibility,
        projection.verification_plan,
        projection.constitution_version,
    ):
        assert envelope.status == MetricStatus.UNAVAILABLE
        assert envelope.value is None


def test_approval_projection_has_no_authority_granting_field():
    """The pinned decision surface must never carry its own approve/deny bit.

    The real approve/reject action happens through the ActionBroker /
    CapabilityAuthority path, never through a field on this read-only
    projection -- otherwise a compromised or buggy frontend could grant
    authority just by rendering a value.
    """
    forbidden_names = {"approved", "decision", "grants_authority", "authorized"}
    assert forbidden_names.isdisjoint(ApprovalProjection.model_fields.keys())


def test_approval_projection_rejects_unknown_fields():
    action = ApprovedAction(action_type="command", payload={}, session_id="s-1")
    projection = project_approval(action)
    data = projection.model_dump()
    data["approved"] = True
    with pytest.raises(ValidationError):
        ApprovalProjection(**data)


# --------------------------------------------------------------------------- #
# project_provider_health_list
# --------------------------------------------------------------------------- #


def test_provider_health_list_omits_providers_with_zero_observations():
    """A never-called provider's snapshot() default (closed/reachable) must
    never be presented as a real measurement."""
    tracker = ProviderHealthTracker()
    tracker.record_success("gemini")

    projections = project_provider_health_list(tracker)

    assert [p.provider for p in projections] == ["gemini"]
    assert set(KNOWN_PROVIDER_NAMES) - {"gemini"}  # sanity: others exist and were skipped


def test_provider_health_list_reflects_a_real_recorded_failure():
    tracker = ProviderHealthTracker()
    tracker.record_failure("bedrock")

    projections = project_provider_health_list(tracker)

    assert len(projections) == 1
    assert projections[0].provider == "bedrock"
    assert projections[0].recent_failure_count.value == 1


# --------------------------------------------------------------------------- #
# project_capability_approval / project_pending_approvals
# --------------------------------------------------------------------------- #


def _binding(**overrides) -> CapabilityBinding:
    values = {
        "operator_id": "operator:one",
        "device_id": "device:one",
        "authentication_event_id": "event:strong",
        "session_id": "session:one",
        "action_type": "command",
        "route": "/api/v1/execute",
        "http_method": "POST",
        "payload_digest": payload_digest({"command": "echo safe"}),
        "resource_digest": payload_digest({"workspace": "training_ground"}),
        "mission_id": "mission-abc123",
        "contract_digest": None,
        "policy_version": "policy:v1",
        "scope": "training_ground/",
        "verification_requirement": "command_exit_zero",
    }
    values.update(overrides)
    return CapabilityBinding(**values)


def test_capability_approval_projection_measures_real_binding_fields(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "capabilities.db")
    binding = _binding()
    authority.issue(binding)
    capability = authority.list_pending()[0]

    projection = project_capability_approval(capability)

    assert projection.requested_action.value == "command"
    assert projection.mission_id.value == "mission-abc123"
    assert projection.scope.value == "training_ground/"
    assert projection.verification_plan.value == "command_exit_zero"
    for envelope in (
        projection.requesting_model,
        projection.risk,
        projection.reversibility,
        projection.constitution_version,
    ):
        assert envelope.status == MetricStatus.UNAVAILABLE


def test_capability_approval_projection_mission_id_unavailable_when_none(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "capabilities.db")
    authority.issue(_binding(mission_id=None))
    capability = authority.list_pending()[0]

    projection = project_capability_approval(capability)

    assert projection.mission_id.status == MetricStatus.UNAVAILABLE


def test_pending_approvals_projects_every_real_pending_capability(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "capabilities.db")
    authority.issue(_binding(action_type="command", route="/api/v1/execute"))
    authority.issue(
        _binding(
            action_type="edit",
            route="/api/edit",
            payload_digest=payload_digest({"filepath": "a.py"}),
            resource_digest=payload_digest({"workspace": "training_ground/a.py"}),
        )
    )

    projections = project_pending_approvals(authority)

    assert {p.requested_action.value for p in projections} == {"command", "edit"}


def test_pending_approvals_empty_when_nothing_pending(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "capabilities.db")
    assert project_pending_approvals(authority) == ()
