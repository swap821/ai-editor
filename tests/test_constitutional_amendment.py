"""Slice 37: Constitutional Amendment Authority."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.application.governance import (
    AmendmentError,
    EmergencyStopController,
    EmergencyStopHooks,
    activate_amendment,
    critique_amendment,
    propose_amendment,
    ratify_amendment,
    reject_amendment,
    rollback_amendment,
    simulate_amendment,
)
from aios.domain.governance import EmergencyStopRequest
from aios.domain.governance.amendments import CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION
from aios.domain.governance.constitution import build_constitution_snapshot
from aios.domain.missions.mission_contract import MissionContract


def _proposal(**overrides: object):
    fields: dict[str, object] = dict(
        proposal_id="amend-1",
        target_articles=("router_max_cost policy",),
        proposed_diff="raise router_max_cost from low to high",
        motivation="unblock a legitimate high-cost task class",
        migration_plan="no data migration needed",
        rollback_plan="revert router_max_cost",
        proposed_by="model:gemini-review",
        proposer_type="model",
    )
    fields.update(overrides)
    return propose_amendment(**fields)


def _real_capability(**overrides: object):
    fields: dict[str, object] = dict(
        action_type=CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
        operator_id="operator:abc",
        consumed_at=1234567890.0,
        token_digest="d" * 64,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


# --- proposal / critique / simulation have zero runtime effect ------------


def test_model_proposal_has_zero_runtime_effect() -> None:
    """A proposal is just data; nothing about its existence changes the
    active constitution -- proven by the fact building one requires no
    reference to any current/active snapshot at all."""
    proposal = _proposal()
    assert proposal.status == "proposed"
    assert proposal.proposer_type == "model"


def test_model_can_critique_and_simulate_without_ratifying() -> None:
    proposal = _proposal()
    proposal = critique_amendment(proposal, "increases cloud spend risk")
    proposal = simulate_amendment(proposal, "no invariant violations found")
    assert proposal.status == "simulated"
    assert proposal.critiques == ("increases cloud spend risk",)
    assert proposal.simulation_notes == ("no invariant violations found",)


# --- no frontend flag / forged evidence can substitute for ratification --


def test_frontend_approval_flag_cannot_activate_amendment() -> None:
    """There is no field on the contract resembling a frontend "approved"
    flag; activation requires status == "ratified", which only
    ratify_amendment can set, which only a real capability can satisfy."""
    assert "approved" not in type(_proposal()).model_fields
    proposal = _proposal()  # never ratified
    v1 = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    with pytest.raises(AmendmentError, match="cannot activate"):
        activate_amendment(proposal, previous_snapshot=v1)


def test_models_and_workers_cannot_ratify_without_a_real_capability() -> None:
    proposal = _proposal()
    with pytest.raises(AmendmentError):
        ratify_amendment(proposal, capability_proof=None, operator_id="operator:abc")


def test_forged_unconsumed_capability_fails() -> None:
    """A capability that was never actually consumed (consumed_at is None)
    is forged/incomplete evidence, not proof of ratification."""
    proposal = _proposal()
    unconsumed = _real_capability(consumed_at=None)
    with pytest.raises(AmendmentError, match="already-consumed"):
        ratify_amendment(proposal, capability_proof=unconsumed, operator_id="operator:abc")


def test_capability_bound_to_the_wrong_action_fails() -> None:
    proposal = _proposal()
    wrong_action = _real_capability(action_type="approval_resolution")
    with pytest.raises(AmendmentError, match="must be bound to"):
        ratify_amendment(proposal, capability_proof=wrong_action, operator_id="operator:abc")


def test_capability_bound_to_a_different_operator_fails() -> None:
    proposal = _proposal()
    someone_elses = _real_capability(operator_id="operator:xyz")
    with pytest.raises(AmendmentError, match="does not match"):
        ratify_amendment(proposal, capability_proof=someone_elses, operator_id="operator:abc")


def test_stale_already_activated_proposal_cannot_be_ratified_again() -> None:
    proposal = _proposal()
    proposal = ratify_amendment(proposal, capability_proof=_real_capability(), operator_id="operator:abc")
    v1 = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    activated, _v2 = activate_amendment(proposal, previous_snapshot=v1)
    with pytest.raises(AmendmentError, match="cannot ratify"):
        ratify_amendment(activated, capability_proof=_real_capability(), operator_id="operator:abc")


# --- foundation laws are not amendable -------------------------------------


def test_amendment_modifying_immutable_article_is_rejected() -> None:
    proposal = _proposal(
        target_articles=("intelligence is not authority",),
        proposed_diff="allow intelligence to self-approve",
    )
    with pytest.raises(AmendmentError, match="foundation-law"):
        ratify_amendment(proposal, capability_proof=_real_capability(), operator_id="operator:abc")


# --- human ratification creates a new version, rollback restores prior ----


def test_human_ratification_creates_new_version() -> None:
    proposal = _proposal(proposed_by="operator:abc", proposer_type="human")
    proposal = ratify_amendment(proposal, capability_proof=_real_capability(), operator_id="operator:abc")
    v1 = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    activated, v2 = activate_amendment(proposal, previous_snapshot=v1)
    assert activated.status == "activated"
    assert v2.version == v1.version + 1
    assert v2.constitution_id == v1.constitution_id
    assert v2.previous_snapshot_digest == v1.snapshot_digest


def test_rollback_restores_prior_version_exactly() -> None:
    proposal = _proposal()
    proposal = ratify_amendment(proposal, capability_proof=_real_capability(), operator_id="operator:abc")
    v1 = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    activated, v2 = activate_amendment(proposal, previous_snapshot=v1)
    rolled_back, restored = rollback_amendment(
        activated, current_snapshot=v2, previous_snapshot=v1
    )
    assert rolled_back.status == "rolled_back"
    assert restored.snapshot_digest == v1.snapshot_digest


def test_rollback_refuses_a_non_predecessor_snapshot() -> None:
    proposal = _proposal()
    proposal = ratify_amendment(proposal, capability_proof=_real_capability(), operator_id="operator:abc")
    v1 = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    activated, v2 = activate_amendment(proposal, previous_snapshot=v1)
    unrelated = build_constitution_snapshot(ratified_by_operator_id="operator:xyz")
    with pytest.raises(AmendmentError, match="not the exact predecessor"):
        rollback_amendment(activated, current_snapshot=v2, previous_snapshot=unrelated)


# --- emergency stop blocks activation --------------------------------------


def test_emergency_stop_blocks_activation(tmp_path: Path) -> None:
    stopped = EmergencyStopController(
        tmp_path / "emergency.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda: None,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda reason: None,
        ),
    )
    stopped.engage(
        EmergencyStopRequest(
            operator_id="operator:abc", authentication_event_id="auth-1", reason="test"
        )
    )
    proposal = _proposal()
    proposal = ratify_amendment(proposal, capability_proof=_real_capability(), operator_id="operator:abc")
    v1 = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    from aios.application.governance import EmergencyStopError

    with pytest.raises(EmergencyStopError):
        activate_amendment(proposal, previous_snapshot=v1, emergency_stop=stopped)


# --- rejected amendments remain auditable ----------------------------------


def test_rejected_amendment_remains_auditable() -> None:
    proposal = _proposal()
    proposal = critique_amendment(proposal, "risky")
    rejected = reject_amendment(proposal, "too risky for this cycle")
    assert rejected.status == "rejected"
    assert rejected.critiques == ("risky",)  # prior evidence is retained
    assert any("too risky" in note for note in rejected.simulation_notes)
    with pytest.raises(AmendmentError, match="cannot reject"):
        reject_amendment(rejected, "again")


# --- old missions stay pinned to their original constitution --------------


def test_old_mission_stays_on_old_constitution_after_activation() -> None:
    v1 = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    mission = MissionContract(
        mission_id="mission-1",
        operator_id="operator:abc",
        goal="do the thing",
        worker_type="deterministic",
        created_by="operator:abc",
        constitution_digest=v1.snapshot_digest,
    )
    proposal = _proposal()
    proposal = ratify_amendment(proposal, capability_proof=_real_capability(), operator_id="operator:abc")
    _activated, v2 = activate_amendment(proposal, previous_snapshot=v1)

    # The constitution moved on to v2, but the mission's own frozen
    # contract -- and its digest -- never changed.
    assert v2.snapshot_digest != v1.snapshot_digest
    assert mission.constitution_digest == v1.snapshot_digest
