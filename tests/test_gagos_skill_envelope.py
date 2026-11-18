"""GAGOS's standing skill envelope (the operator, 2026-11-18: "only once, not
again and again"; he chose a standing skill envelope).

He signs once for a period; inside it a review-ready candidate skill is
activated by GAGOS without his click, and the activation names the envelope.
Pinned: only a privileged operator signs; the requester is never the signer;
the count, the expiry, revocation, a newer envelope and the emergency stop all
end or bound it; a suspended or not-ready skill is never reached; the mission
envelope's stop rule is the same code (one derivation).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from aios.application.capabilities import envelope as mission_envelope
from aios.application.capabilities.skill_envelope import (
    SkillEnvelopeAuthority,
    SkillEnvelopeRefused,
)
from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopHooks,
)
from aios.application.learning.service import LearningService, SkillActivationDenied
from aios.domain.capabilities.skill_envelope import (
    SkillEnvelopeError,
    SkillEnvelopeTerms,
)
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.domain.learning.repository import SkillRecord, SkillRepository


@dataclass
class Who:
    principal_id: str = "operator-1"
    principal_type: str = "operator"
    authentication_level: str = "privileged"
    authentication_event_id: str = "auth-1"
    session_id: str = "session-1"
    metadata: dict = field(default_factory=dict)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def _stop(tmp_path) -> EmergencyStopController:
    return EmergencyStopController(
        tmp_path / "stop.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda: None,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda reason: None,
        ),
    )


def _authority(tmp_path, clock=None, stop=None) -> SkillEnvelopeAuthority:
    return SkillEnvelopeAuthority(
        db_path=tmp_path / "caps.db",
        emergency_stop=stop if stop is not None else _stop(tmp_path),
        clock=clock or Clock(),
    )


def _terms(days=30, max_activations=2) -> SkillEnvelopeTerms:
    return SkillEnvelopeTerms.build(days=days, max_activations=max_activations)


# -- the terms ---------------------------------------------------------------


@pytest.mark.parametrize(
    "days,count", [(0, 1), (31, 1), (1, 0), (1, 101), (True, 1), (1, "2")]
)
def test_terms_outside_their_bounds_are_refused(days, count) -> None:
    with pytest.raises(SkillEnvelopeError):
        SkillEnvelopeTerms.build(days=days, max_activations=count)


# -- the operator's signature ---------------------------------------------------


@pytest.mark.parametrize(
    "who,why",
    [
        (Who(principal_type="agent"), "only the operator"),
        (Who(authentication_level="authenticated"), "strong re-authentication"),
        (Who(authentication_event_id=""), "recorded authentication"),
    ],
)
def test_only_a_privileged_operator_signs(tmp_path, who, why) -> None:
    with pytest.raises(SkillEnvelopeRefused, match=why):
        _authority(tmp_path).sign(_terms(), principal=who)


def test_unsigned_there_is_no_envelope_and_it_says_so(tmp_path) -> None:
    authority = _authority(tmp_path)
    assert authority.status() == {
        "live": False,
        "reason": "the operator has not signed a skill envelope",
    }
    with pytest.raises(SkillEnvelopeRefused, match="has not signed"):
        authority.admit(skill_id="arc-1", version=1, originator="gagos")


# -- GAGOS's activations ----------------------------------------------------------


def test_an_activation_takes_one_place_and_names_the_envelope(tmp_path) -> None:
    authority = _authority(tmp_path)
    signed = authority.sign(_terms(max_activations=2), principal=Who())
    admission = authority.admit(skill_id="arc-1", version=1, originator="gagos")
    assert (admission.activation, admission.of) == (1, 2)
    assert admission.envelope_id == signed.envelope_id
    assert admission.operator_id == "operator-1"
    assert admission.authentication_event_id == "auth-1"
    assert signed.envelope_id in admission.reason()
    assert authority.status()["activationsLeft"] == 1


def test_the_signer_never_originates_inside_his_own_envelope(tmp_path) -> None:
    authority = _authority(tmp_path)
    authority.sign(_terms(), principal=Who())
    with pytest.raises(SkillEnvelopeRefused, match="cannot originate"):
        authority.admit(skill_id="arc-1", version=1, originator="operator-1")


def test_a_skill_version_is_activated_once_and_the_count_holds(tmp_path) -> None:
    authority = _authority(tmp_path)
    authority.sign(_terms(max_activations=2), principal=Who())
    authority.admit(skill_id="arc-1", version=1, originator="gagos")
    with pytest.raises(SkillEnvelopeRefused, match="already activated"):
        authority.admit(skill_id="arc-1", version=1, originator="gagos")
    authority.admit(skill_id="arc-2", version=1, originator="gagos")
    with pytest.raises(SkillEnvelopeRefused, match="2 activations are used"):
        authority.admit(skill_id="arc-3", version=1, originator="gagos")


def test_expiry_revocation_and_a_newer_envelope_each_end_it(tmp_path) -> None:
    clock = Clock()
    authority = _authority(tmp_path, clock=clock)
    authority.sign(_terms(days=1), principal=Who())
    clock.now += 86_400
    with pytest.raises(SkillEnvelopeRefused, match="expired"):
        authority.admit(skill_id="arc-1", version=1, originator="gagos")
    first = authority.sign(_terms(), principal=Who())
    second = authority.sign(_terms(), principal=Who())
    assert authority.live().envelope_id == second.envelope_id != first.envelope_id
    assert authority.revoke(principal=Who()) is True
    with pytest.raises(SkillEnvelopeRefused, match="revoked by the operator"):
        authority.admit(skill_id="arc-1", version=1, originator="gagos")
    with pytest.raises(SkillEnvelopeRefused, match="only the operator ends"):
        authority.revoke(principal=Who(principal_type="agent"))


def test_a_stop_ends_the_envelope_even_after_it_is_cleared(tmp_path) -> None:
    stop = _stop(tmp_path)
    authority = _authority(tmp_path, stop=stop)
    authority.sign(_terms(), principal=Who())
    stop.engage(
        EmergencyStopRequest(
            operator_id="operator-1", authentication_event_id="auth-2", reason="test"
        )
    )
    with pytest.raises(SkillEnvelopeRefused, match="emergency stop"):
        authority.admit(skill_id="arc-1", version=1, originator="gagos")
    token = stop.issue_clear_capability(
        operator_id="operator-1",
        authentication_event_id="auth-3",
        session_id="session-1",
    )
    stop.clear(
        operator_id="operator-1",
        authentication_event_id="auth-3",
        session_id="session-1",
        clear_capability=token,
    )
    with pytest.raises(SkillEnvelopeRefused, match="engaged after the skill envelope"):
        authority.admit(skill_id="arc-1", version=1, originator="gagos")


def test_with_no_stop_wired_no_skill_envelope_can_be_signed(tmp_path) -> None:
    with pytest.raises(SkillEnvelopeRefused, match="no emergency stop"):
        SkillEnvelopeAuthority(db_path=tmp_path / "c.db", emergency_stop=None).sign(
            _terms(), principal=Who()
        )


def test_both_envelopes_judge_the_stop_by_one_derivation() -> None:
    """The stop's rule lives once (2026-11-18): both envelopes call it."""
    import inspect

    from aios.application.capabilities import skill_envelope

    assert "stop_generation(" in inspect.getsource(
        mission_envelope.EnvelopeAuthority._stop_generation
    )
    assert skill_envelope.stop_generation is mission_envelope.stop_generation


# -- the learning service: the skill's own rules ----------------------------------


def _skill(
    skill_id: str, *, state: str = "candidate", ready: bool = True
) -> SkillRecord:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return SkillRecord(
        skill_id=skill_id,
        version=1,
        problem_signature=f"goal {skill_id}",
        applicability_conditions={},
        known_exclusions=[],
        required_inputs=[],
        required_project_state={},
        procedure=json.dumps(["edit:a.py"]),
        allowed_tools=["edit"],
        allowed_scope_pattern="",
        expected_observations=[],
        verification_plan=None,
        escalation_conditions=[],
        source_trajectory_ids=[],
        confidence=0.9,
        success_count=4 if ready else 1,
        failure_count=0,
        last_validated_versions=[],
        state=state,
        created_at=now,
        updated_at=now,
        provenance={},
    )


def _service(repository: SkillRepository):
    """The method needs only the repository and the operational check."""
    return SimpleNamespace(
        skill_repository=repository, _assert_operational=lambda: None
    )


def _activate(service, skill_id, authority):
    return LearningService.activate_skill_within_envelope(
        service, skill_id, 1, envelope=authority, originator="gagos"
    )


def test_a_review_ready_candidate_is_activated_inside_the_envelope(tmp_path) -> None:
    repository = SkillRepository(tmp_path / "learn.db")
    repository.save(_skill("arc-ready"))
    authority = _authority(tmp_path)
    authority.sign(_terms(), principal=Who())
    skill, admission = _activate(_service(repository), "arc-ready", authority)
    assert skill.state == "active"
    assert (skill.provenance or {}).get("principal") == "operator-1"
    assert admission.activation == 1
    assert authority.store.activation(admission.envelope_id, "arc-ready", 1) is not None


@pytest.mark.parametrize(
    "state,ready,why",
    [
        ("suspended", True, "re-activation"),
        ("active", True, "only a candidate"),
        ("candidate", False, "not review-ready"),
    ],
)
def test_the_skills_own_rules_hold_before_any_place_is_taken(
    tmp_path, state, ready, why
) -> None:
    repository = SkillRepository(tmp_path / "learn.db")
    # A skill is born a candidate and moves only through its transitions.
    repository.save(_skill("arc-x", ready=ready))
    path = {"candidate": [], "active": ["human_reviewed", "active"]}
    path["suspended"] = [*path["active"], "suspended"]
    for step in path[state]:
        assert repository.transition_state("arc-x", 1, step).state == step
    authority = _authority(tmp_path)
    authority.sign(_terms(), principal=Who())
    with pytest.raises(SkillActivationDenied, match=why):
        _activate(_service(repository), "arc-x", authority)
    assert authority.status()["activationsUsed"] == 0
    assert repository.get("arc-x", 1).state == state


def test_without_a_live_envelope_the_skill_stays_a_candidate(tmp_path) -> None:
    repository = SkillRepository(tmp_path / "learn.db")
    repository.save(_skill("arc-ready"))
    with pytest.raises(SkillActivationDenied, match="has not signed"):
        _activate(_service(repository), "arc-ready", _authority(tmp_path))
    assert repository.get("arc-ready", 1).state == "candidate"
