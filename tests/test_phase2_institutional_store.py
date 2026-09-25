"""Phase 2, slice 2: the institutional skill store enforces its own lifecycle.

Ground truth before this slice (docs/learning/PHASE2_DESIGN.md):

* ``qualified`` was a declared state with no row in the transition table, so a
  record in it made ``transition_state`` raise ``KeyError`` instead of refusing.
* ``SkillRepository.save`` wrote whatever state it was handed. The transition
  graph bound only the callers that chose to call ``transition_state``, so
  "activation is a human, capability-backed act" was a convention.
* Three learning-service writes (trajectory capture, candidate creation,
  reuse outcomes) never asked the emergency stop.

Slice 2.4 routes the live turn's skill writes into this store, which is why
these properties have to hold at the store rather than in its callers.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import get_args
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.application.learning.service import LearningService
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.domain.learning.applicability import (
    ApplicabilityError,
    SkillApplicabilityEngine,
)
from aios.domain.learning.repository import (
    _EVIDENCE_FIELDS,
    SkillRecord,
    SkillRepository,
)
from aios.domain.learning.reuse_outcome_repository import ReuseOutcomeRepository
from aios.domain.learning.skill_contracts import (
    BIRTH_STATE,
    SKILL_TRANSITIONS,
    WITHDRAWAL_STATES,
    SkillState,
    check_transition,
)
from aios.domain.learning.trajectory_repository import TrajectoryRepository
from aios.domain.verification import SkillVerifierSpec
from aios.memory import learning_freeze
from tests.helpers import reuse_outcome_reference, save_minimal_trajectory, seed_skill

ALL_STATES: tuple[str, ...] = get_args(SkillState)
TERMINAL = frozenset(state for state, nxt in SKILL_TRANSITIONS.items() if not nxt)
#: The road to use: only `active` passes applicability, and these lead there.
ROAD_TO_USE = frozenset({"candidate", "human_reviewed", "probation", "active"})


def _record(**overrides: object) -> SkillRecord:
    fields: dict[str, object] = dict(
        skill_id="skill-1",
        version=1,
        problem_signature="sig",
        applicability_conditions={},
        known_exclusions=[],
        required_inputs=[],
        required_project_state={},
        procedure="do X",
        allowed_tools=[],
        allowed_scope_pattern="*",
        expected_observations=[],
        verification_plan=None,
        escalation_conditions=[],
        source_trajectory_ids=["trajectory-1"],
        confidence=0.9,
        success_count=3,
        failure_count=0,
        last_validated_versions=[],
        state=BIRTH_STATE,
        created_at="2026-09-26T00:00:00",
        updated_at="2026-09-26T00:00:00",
    )
    fields.update(overrides)
    return SkillRecord(**fields)


def _stored_state(repo: SkillRepository, skill_id: str = "skill-1") -> str | None:
    got = repo.get(skill_id, 1)
    return None if got is None else got.state


class TestTheLifecycleIsTotalPolicy:
    def test_every_declared_state_has_a_row(self) -> None:
        assert set(SKILL_TRANSITIONS) == set(ALL_STATES)
        for targets in SKILL_TRANSITIONS.values():
            assert targets <= set(ALL_STATES)

    def test_qualified_is_gone(self) -> None:
        assert "qualified" not in ALL_STATES

    def test_a_record_in_an_undeclared_state_does_not_load(self) -> None:
        """Fail-closed: a stored `qualified` row is refused at validation, not
        carried around until a transition crashes on it."""
        with pytest.raises(ValidationError):
            _record(state="qualified")

    def test_an_unknown_state_is_refused_not_crashed(self) -> None:
        with pytest.raises(ValueError, match="invalid skill transition"):
            check_transition("qualified", "active")  # type: ignore[arg-type]

    @pytest.mark.parametrize("state", sorted(set(ALL_STATES) - TERMINAL))
    def test_revocation_is_reachable_from_every_non_terminal_state(
        self, state: str
    ) -> None:
        assert "revoked" in SKILL_TRANSITIONS[state]

    def test_nothing_is_reborn(self) -> None:
        """No transition leads back to birth: a skill cannot be laundered
        into a fresh candidate to shed its record."""
        assert all(BIRTH_STATE not in nxt for nxt in SKILL_TRANSITIONS.values())

    def test_active_is_reached_only_through_review(self) -> None:
        into_active = {s for s, nxt in SKILL_TRANSITIONS.items() if "active" in nxt}
        assert into_active == {"human_reviewed", "probation"}
        assert "probation" in SKILL_TRANSITIONS["human_reviewed"]
        assert all(
            "probation" not in nxt
            for state, nxt in SKILL_TRANSITIONS.items()
            if state != "human_reviewed"
        )


class TestSaveNeverWritesAState:
    @pytest.mark.parametrize("state", sorted(set(ALL_STATES) - {BIRTH_STATE}))
    def test_a_skill_cannot_be_born_in_any_other_state(
        self, tmp_path: Path, state: str
    ) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        with pytest.raises(ValueError, match="born 'candidate'"):
            repo.save(_record(state=state))
        assert repo.get("skill-1", 1) is None

    def test_positive_control_a_candidate_is_born(self, tmp_path: Path) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        repo.save(_record())
        assert _stored_state(repo) == BIRTH_STATE

    def test_save_cannot_promote_an_existing_skill(self, tmp_path: Path) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        repo.save(_record())
        with pytest.raises(ValueError, match="transition_state"):
            repo.save(_record(state="active"))
        assert _stored_state(repo) == BIRTH_STATE

    def test_save_cannot_resurrect_a_revoked_skill(self, tmp_path: Path) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        repo.save(_record())
        repo.transition_state("skill-1", 1, "revoked")
        with pytest.raises(ValueError):
            repo.save(_record(state="candidate"))
        assert _stored_state(repo) == "revoked"

    def test_save_still_updates_evidence_in_place(self, tmp_path: Path) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        seed_skill(repo, _record(state="active"))
        current = repo.get("skill-1", 1)
        repo.save(current.model_copy(update={"success_count": 9}))
        got = repo.get("skill-1", 1)
        assert (got.state, got.success_count) == ("active", 9)

    def test_a_refused_transition_writes_nothing(self, tmp_path: Path) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        repo.save(_record())
        before = repo.get("skill-1", 1)
        with pytest.raises(ValueError, match="invalid skill transition"):
            repo.transition_state("skill-1", 1, "active")
        assert repo.get("skill-1", 1) == before

    def test_provenance_round_trips_and_defaults_empty(self, tmp_path: Path) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        repo.save(_record(provenance={"source": "migrated", "legacy_id": "17"}))
        repo.save(_record(skill_id="skill-2"))
        assert repo.get("skill-1", 1).provenance == {
            "source": "migrated",
            "legacy_id": "17",
        }
        assert repo.get("skill-2", 1).provenance == {}


#: A changed value for every field a reviewer approved. Identity (skill_id,
#: version) picks the record; state moves only by transition; evidence is what
#: `save` may still update. A test below fails if a field is added to the record
#: without being classified here or as evidence.
_CONTRACT_CHANGES: dict[str, object] = {
    "problem_signature": "a different problem",
    "applicability_conditions": {"k": "v"},
    "known_exclusions": ["x"],
    "required_inputs": ["y"],
    "required_project_state": {"a": "b"},
    "procedure": "do something else",
    "allowed_tools": ["execute_terminal"],
    "allowed_scope_pattern": "**",
    "expected_observations": ["o"],
    "verification_plan": SkillVerifierSpec(
        target_pattern="*", required_observations=("x",), minimum_strength=1
    ),
    "escalation_conditions": ["e"],
    "source_trajectory_ids": ["another-trajectory"],
    "last_validated_versions": ["9.9"],
    "provenance": {"source": "forged"},
    "created_at": "2000-01-01T00:00:00",
}


class TestAReviewedContractIsNeverRewritten:
    """Legacy `record_attempt` refreshes a skill's steps in place. On this
    store that would run something the operator never approved under an
    approval given for something else."""

    def test_every_field_is_classified(self) -> None:
        classified = (
            set(_CONTRACT_CHANGES) | set(_EVIDENCE_FIELDS) | {"skill_id", "version", "state"}
        )
        assert classified == set(SkillRecord.model_fields)

    def test_evidence_is_only_counts_confidence_and_time(self) -> None:
        assert _EVIDENCE_FIELDS == {
            "confidence",
            "success_count",
            "failure_count",
            "updated_at",
        }

    @pytest.mark.parametrize("field", sorted(_CONTRACT_CHANGES))
    @pytest.mark.parametrize("state", ["human_reviewed", "active", "suspended"])
    def test_a_reviewed_skill_keeps_its_contract(
        self, tmp_path: Path, field: str, state: str
    ) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        stored = seed_skill(repo, _record(state=state))
        with pytest.raises(ValueError, match="rewrite the contract"):
            repo.save(stored.model_copy(update={field: _CONTRACT_CHANGES[field]}))
        assert repo.get("skill-1", 1) == stored

    @pytest.mark.parametrize("field", sorted(_CONTRACT_CHANGES))
    def test_positive_control_a_candidate_may_still_be_refined(
        self, tmp_path: Path, field: str
    ) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        repo.save(_record())
        refined = _record(**{field: _CONTRACT_CHANGES[field]})
        repo.save(refined)
        assert repo.get("skill-1", 1) == refined


class TestWithdrawalStatesTakeASkillOutOfUse:
    def test_they_are_exactly_the_states_off_the_road_to_use(self) -> None:
        assert WITHDRAWAL_STATES == set(ALL_STATES) - ROAD_TO_USE

    @pytest.mark.parametrize("state", sorted(WITHDRAWAL_STATES))
    def test_applicability_refuses_every_withdrawn_skill(self, state: str) -> None:
        with pytest.raises(ApplicabilityError, match="not active"):
            SkillApplicabilityEngine().check_applicability(
                _record(state=state),
                {},
                {},
                current_scope="x",
                mission_allowed_tools=(),
                validated_version="1",
                verification_plan_executable=True,
                policy_allows=True,
            )


def _noop(*_a, **_k):
    return None


@pytest.fixture()
def latch(tmp_path, monkeypatch):
    """The real durable latch, relocated into a throwaway directory."""
    path = tmp_path / "emergency_stop.db"
    monkeypatch.setattr(learning_freeze, "_latch_path", lambda: path)
    monkeypatch.setattr(learning_freeze, "_controllers", {})

    def engage() -> None:
        stop = EmergencyStopController(
            path,
            hooks=EmergencyStopHooks(
                revoke_capabilities=_noop,
                cancel_queued_missions=_noop,
                kill_active_workers=_noop,
                disable_autonomy=_noop,
                preserve_evidence=_noop,
            ),
        )
        stop.engage(
            EmergencyStopRequest(
                operator_id="operator:test",
                authentication_event_id="event:engage",
                reason="institutional store freeze test",
            )
        )
        assert stop.is_engaged()

    return engage


def _rows(db: Path, table: str) -> int:
    with sqlite3.connect(db) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


class TestTheStopFreezesTheInstitutionalStore:
    def test_a_candidate_is_refused(self, tmp_path: Path, latch) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        latch()
        with pytest.raises(EmergencyStopError, match="institutional_skills.save"):
            repo.save(_record())
        assert repo.get("skill-1", 1) is None

    def test_evidence_updates_are_refused(self, tmp_path: Path, latch) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        repo.save(_record())
        latch()
        with pytest.raises(EmergencyStopError):
            repo.save(_record(success_count=99))
        assert repo.get("skill-1", 1).success_count == 3

    @pytest.mark.parametrize("target", ["human_reviewed", "probation", "active"])
    def test_every_step_toward_use_is_refused(
        self, tmp_path: Path, latch, target: str
    ) -> None:
        repo = SkillRepository(tmp_path / "skills.db")
        start = {"human_reviewed": "candidate", "probation": "human_reviewed"}.get(
            target, "human_reviewed"
        )
        seed_skill(repo, _record(state=start))
        latch()
        with pytest.raises(EmergencyStopError, match="transition"):
            repo.transition_state("skill-1", 1, target)
        assert _stored_state(repo) == start

    @pytest.mark.parametrize("target", sorted(WITHDRAWAL_STATES))
    def test_withdrawal_still_works_while_stopped(
        self, tmp_path: Path, latch, target: str
    ) -> None:
        """The operator can always stop, revoke and correct: a stop that
        blocked revocation would protect the skill, not the operator."""
        repo = SkillRepository(tmp_path / "skills.db")
        start = next(
            state
            for state in ("active", "candidate", "human_reviewed", "probation")
            if target in SKILL_TRANSITIONS[state]
        )
        seed_skill(repo, _record(state=start))
        latch()
        assert repo.transition_state("skill-1", 1, target).state == target
        assert _stored_state(repo) == target

    def test_a_trajectory_is_refused(self, tmp_path: Path, latch) -> None:
        db = tmp_path / "learning.db"
        repo = TrajectoryRepository(db)
        save_minimal_trajectory(repo, "trajectory-control")
        latch()
        with pytest.raises(EmergencyStopError, match="expert_trajectories.save"):
            save_minimal_trajectory(repo, "trajectory-frozen")
        assert repo.get("trajectory-frozen") is None
        assert repo.get("trajectory-control") is not None

    def test_a_reuse_outcome_is_refused_before_anything_is_written(
        self, tmp_path: Path, latch
    ) -> None:
        """`record_reuse_outcome` writes the idempotency row first, so the
        refusal must come there: no outcome half-recorded, no skill touched."""
        db = tmp_path / "learning.db"
        skills = SkillRepository(db)
        seed_skill(skills, _record(state="active"))
        outcomes = ReuseOutcomeRepository(db)
        service = LearningService(
            mission_service=MagicMock(),
            trajectory_repository=TrajectoryRepository(db),
            skill_repository=skills,
            reuse_outcome_repository=outcomes,
            emergency_stop=UNGOVERNED_FIXTURE,
        )

        def reference(outcome_id: str, worker_id: str):
            return reuse_outcome_reference(
                reuse_outcome_id=outcome_id,
                skill=skills.get("skill-1", 1),
                trajectory_id="trajectory-1",
                mission=SimpleNamespace(
                    mission_id="mission-1", contract_digest="digest-1"
                ),
                verification=SimpleNamespace(verification_id="verification-1"),
                worker_id=worker_id,
                workspace_digest="workspace-1",
                diff_digest="diff-1",
            )

        # Positive control, and a distinct lineage for the frozen attempt (the
        # lineage key ignores the outcome id), so a refusal cannot be mistaken
        # for the idempotency guard declining a duplicate.
        assert outcomes.record(reference("outcome-control", "worker-control"))
        before = skills.get("skill-1", 1)
        latch()
        with pytest.raises(EmergencyStopError, match="reuse_outcomes.record"):
            service.record_reuse_outcome(reference("outcome-frozen", "worker-frozen"))
        assert _rows(db, "reuse_outcomes") == 1
        assert skills.get("skill-1", 1) == before
