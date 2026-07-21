"""Slice 36: Skill Confidence, Demotion and Endurance.

The brief's "golden release cohort" (12 governed frontier missions across 2
real cloud providers, 4 candidate skills, 3 verified local reuses each,
etc.) requires hours of real governed mission execution against live
frontier providers -- not something achievable or appropriate to run
autonomously in this environment/pass. That gap is recorded honestly in the
organ ledger rather than faked. What this file proves is the real,
previously-missing piece: confidence-driven demotion actually firing
through the existing, already-validated `SkillRepository` transition graph.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.application.learning import (
    apply_reuse_outcome,
    evaluate_demotion,
    human_revoke,
)
from aios.domain.learning.repository import SkillRecord, SkillRepository


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
        source_trajectory_ids=[],
        confidence=0.9,
        success_count=3,
        failure_count=0,
        last_validated_versions=[],
        state="active",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    fields.update(overrides)
    return SkillRecord(**fields)


def _repo(tmp_path: Path) -> SkillRepository:
    return SkillRepository(tmp_path / "skills.db")


# --- evaluate_demotion (pure) -----------------------------------------


def test_no_demotion_before_minimum_attempts() -> None:
    skill = _record(confidence=0.1, success_count=1, failure_count=1)
    assert evaluate_demotion(skill) is None


def test_no_demotion_above_confidence_floor() -> None:
    skill = _record(confidence=0.8, success_count=5, failure_count=3)
    assert evaluate_demotion(skill) is None


def test_active_below_floor_demotes_to_degraded() -> None:
    skill = _record(state="active", confidence=0.3, success_count=2, failure_count=3)
    assert evaluate_demotion(skill) == "degraded"


def test_degraded_below_floor_demotes_to_suspended() -> None:
    skill = _record(state="degraded", confidence=0.2, success_count=2, failure_count=3)
    assert evaluate_demotion(skill) == "suspended"


def test_applicability_failure_forces_suspension_regardless_of_confidence() -> None:
    """Scope no longer matches: this is a precondition failure, not a
    statistical reliability question -- demote immediately."""
    skill = _record(confidence=0.99, success_count=20, failure_count=0)
    assert evaluate_demotion(skill, reason="applicability") == "suspended"


def test_version_drift_forces_suspension_regardless_of_confidence() -> None:
    """Dependency version changed materially: same immediate-demotion logic."""
    skill = _record(confidence=0.99, success_count=20, failure_count=0)
    assert evaluate_demotion(skill, reason="version_drift") == "suspended"


def test_already_terminal_or_inactive_skill_is_never_auto_demoted() -> None:
    for state in ("revoked", "superseded", "deprecated", "blocked", "candidate"):
        skill = _record(state=state, confidence=0.0, success_count=0, failure_count=10)
        assert evaluate_demotion(skill) is None


# --- apply_reuse_outcome (real repository) -----------------------------


def test_repeated_verification_failures_demote_active_to_degraded_then_suspended(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    repo.save(_record())  # confidence=0.9; 0.2 penalty per failure
    for _ in range(3):
        # 0.9 -> 0.7 (active) -> 0.5 (active, boundary: not < floor) -> 0.3 (< floor)
        record = apply_reuse_outcome(repo, "skill-1", 1, success=False, reason="verification")
    assert record.state == "degraded"
    record = apply_reuse_outcome(repo, "skill-1", 1, success=False, reason="verification")
    assert record.state == "suspended"


def test_successful_reuse_increases_confidence_and_persists(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save(_record(confidence=0.5))
    updated = apply_reuse_outcome(repo, "skill-1", 1, success=True)
    assert updated.confidence == pytest.approx(0.55)
    assert updated.success_count == 4
    reloaded = repo.get("skill-1", 1)
    assert reloaded.confidence == pytest.approx(0.55)


def test_applicability_failure_immediately_suspends_a_highly_confident_skill(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    repo.save(_record(confidence=0.95, success_count=20, failure_count=0))
    updated = apply_reuse_outcome(repo, "skill-1", 1, success=False, reason="applicability")
    assert updated.state == "suspended"


def test_failure_outcome_requires_a_reason(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save(_record())
    with pytest.raises(ValueError, match="reason"):
        apply_reuse_outcome(repo, "skill-1", 1, success=False)


def test_unknown_skill_raises_key_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(KeyError):
        apply_reuse_outcome(repo, "does-not-exist", 1, success=True)


# --- human revocation ---------------------------------------------------


def test_human_revocation_is_reachable_from_every_non_terminal_state(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    for state in ("candidate", "human_reviewed", "probation", "active", "degraded", "suspended", "blocked"):
        skill_id = f"skill-{state}"
        repo.save(_record(skill_id=skill_id, state=state))
        revoked = human_revoke(repo, skill_id, 1)
        assert revoked.state == "revoked"


def test_double_revocation_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.save(_record())
    human_revoke(repo, "skill-1", 1)
    with pytest.raises(ValueError, match="terminal state"):
        human_revoke(repo, "skill-1", 1)


def test_revoking_an_unknown_skill_raises_key_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(KeyError):
        human_revoke(repo, "does-not-exist", 1)
