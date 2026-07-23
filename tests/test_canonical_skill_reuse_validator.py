"""Phase 1 — Canonical mounted skill-reuse validator tests.

These tests use the REAL production ``get_learning_service()`` dependency from
``aios.api.deps`` — NOT a dependency override that supplies
``verification_plan_validator=lambda *_args: True``.

Required coverage (items 1-15 from the spec):

1.  Valid structured active skill → governed MissionService draft only.
2.  Mission requires Human approval (requires_approval=True).
3.  No worker executes directly from the route (mission stays DRAFT).
4.  No shell command is generated in the mission contract.
5.  Invalid verifier_id → validator returns False (escalate path).
6.  Unsupported verifier version → validator returns False.
7.  Empty required_observations → validator returns False.
8.  Weak minimum_strength (0) → validator returns False.
9.  Legacy string verification_plan → quarantined, validator returns False.
10. None verification_plan → validator returns False (fail closed).
11. Unknown structured fields → validator returns False.
12. Production validator never raises AttributeError on typed objects.
13. Real dependency survives application restart/reconstruction.
14. Client cannot assert policy allows reuse (autonomy gate).
15. Plan with forbidden 'command' field → validator returns False.
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aios.api.deps import get_learning_service
from aios.application.learning.service import LearningService
from aios.domain.learning.repository import SkillRecord
from aios.domain.verification import SkillVerifierSpec
from aios.domain.learning.reuse_orchestrator import (
    EscalateToFrontierDirective,
    LocalExecutionDirective,
)
from aios.domain.learning.skill_contracts import SkillContract
from aios.domain.missions.mission_state import MissionState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_verifier() -> SkillVerifierSpec:
    """Minimal valid SkillVerifierSpec meeting all policy requirements."""
    return SkillVerifierSpec(
        target_pattern="src/*.py",
        required_observations=("tests_pass", "no_regression"),
        minimum_strength=2,
    )


def _valid_skill_record() -> SkillRecord:
    """An active skill record with a valid structured verification plan."""
    return SkillRecord(
        skill_id="skill-canonical-test",
        version=1,
        problem_signature="repair-json-parser",
        applicability_conditions={"format": "json"},
        known_exclusions=(),
        required_inputs=("log_path",),
        required_project_state={"parser_version": "v2"},
        procedure="Apply the reviewed parser repair.",
        allowed_tools=("read_file", "edit_file"),
        allowed_scope_pattern="src/*.py",
        expected_observations=("repair applied",),
        verification_plan=_valid_verifier(),
        escalation_conditions=("schema mismatch",),
        source_trajectory_ids=("trajectory-001",),
        confidence=0.92,
        success_count=3,
        failure_count=0,
        last_validated_versions=("project-v2",),
        state="active",
        created_at="2026-07-19T00:00:00+00:00",
        updated_at="2026-07-19T00:00:00+00:00",
    )


def _build_real_service(tmp_path: Path, *, autonomy_enabled: bool = True) -> LearningService:
    """Build the REAL production LearningService via the canonical dependency.

    Patches:
    - ``aios.api.deps.config`` → redirects DB paths to tmp_path
    - ``aios.policy.kernel.get_policy_kernel`` → the source module that the
      reuse_policy closure imports from at construction time.

    We do NOT override ``verification_plan_validator`` — that is the
    production code we are testing.
    """
    mock_kernel = MagicMock()
    mock_kernel.earned_autonomy_enabled.return_value = autonomy_enabled

    with (
        patch("aios.api.deps.config") as mock_config,
        patch("aios.policy.kernel.get_policy_kernel", return_value=mock_kernel),
    ):
        mock_config.MISSION_STATE_DB = tmp_path / "missions.db"
        mock_config.OPERATIONAL_STATE_DB_PATH = tmp_path / "operational.db"
        mock_config.LOCAL_WORKFORCE_PROVENANCE_DB_PATH = (
            tmp_path / "local_workforce_provenance.db"
        )
        service = get_learning_service()

        if service.local_workforce_service is not None:
            from aios.domain.local_workforce.contracts import LocalJobResult
            service.local_workforce_service.run_advisory_job = MagicMock(
                return_value=LocalJobResult(
                    job_id="test-advisory-job",
                    model_id="granite3.2:2b",
                    structured_output={"applicable": True, "confidence": 0.9, "reason": "ok"},
                    schema_valid=True,
                    evidence_references_preserved=True,
                    unsupported_claims=(),
                    latency=0.01,
                    status="completed",
                )
            )

    return service


def _reuse_attempt(
    service: LearningService,
    skill: SkillRecord,
    *,
    mission_id: str = "reuse-mission-1",
) -> Any:
    """Save the skill and run attempt_local_reuse through the canonical service."""
    service.skill_repository.save(skill)
    return service.attempt_local_reuse(
        skill_id=skill.skill_id,
        version=skill.version,
        mission_id=mission_id,
        operator_id="operator-sovereign",
        goal="Repair the JSON log parser using admitted skill",
        project_id="project-canonical",
        current_inputs={"format": "json", "log_path": "src/app.py"},
        current_state={"parser_version": "v2"},
        current_scope="src/app.py",
        mission_allowed_tools=("read_file", "edit_file"),
        validated_version="project-v2",
    )


class _FakeSkillWithPlan:
    """Minimal skill-like object for directly testing the validator closure."""

    def __init__(
        self,
        plan: Any,
        *,
        state: str = "active",
    ) -> None:
        self.verification_plan = plan
        self.state = state


# ---------------------------------------------------------------------------
# Test 1: Valid structured active skill → governed MissionService draft
# ---------------------------------------------------------------------------


def test_01_valid_active_skill_produces_mission_draft(tmp_path: Path) -> None:
    """Requirement 1 — valid structured active skill → governed mission draft."""
    service = _build_real_service(tmp_path)
    directive = _reuse_attempt(service, _valid_skill_record())

    assert isinstance(
        directive, LocalExecutionDirective
    ), f"expected LocalExecutionDirective, got {type(directive).__name__}: {directive}"
    assert directive.directive_type == "local_execute"
    assert directive.mission_id == "reuse-mission-1"


# ---------------------------------------------------------------------------
# Test 2: Mission requires Human approval
# ---------------------------------------------------------------------------


def test_02_created_mission_requires_human_approval(tmp_path: Path) -> None:
    """Requirement 2 — the drafted mission must require Human approval."""
    service = _build_real_service(tmp_path)
    directive = _reuse_attempt(service, _valid_skill_record())

    assert isinstance(directive, LocalExecutionDirective), (
        f"expected LocalExecutionDirective, got {type(directive).__name__}"
    )
    mission = service.mission_service.repository.get(directive.mission_id)
    assert mission is not None
    assert mission.contract.requires_approval is True, (
        "mission created by skill reuse must require Human approval"
    )


# ---------------------------------------------------------------------------
# Test 3: No worker executes directly (mission stays DRAFT)
# ---------------------------------------------------------------------------


def test_03_reuse_does_not_execute_worker(tmp_path: Path) -> None:
    """Requirement 3 — no worker executes directly; mission stays DRAFT (not RUNNING)."""
    service = _build_real_service(tmp_path)
    directive = _reuse_attempt(service, _valid_skill_record())

    assert isinstance(directive, LocalExecutionDirective)
    mission = service.mission_service.repository.get(directive.mission_id)
    # Mission stays in DRAFT state — execution requires Human approval first
    assert mission.state is MissionState.DRAFT, (
        f"mission must stay DRAFT (awaiting Human approval), got {mission.state.value}"
    )


# ---------------------------------------------------------------------------
# Test 4: No shell command in the generated mission contract
# ---------------------------------------------------------------------------


def test_04_mission_contract_contains_no_shell_command(tmp_path: Path) -> None:
    """Requirement 4 — the mission contract must not embed a shell command."""
    service = _build_real_service(tmp_path)
    directive = _reuse_attempt(service, _valid_skill_record())

    assert isinstance(directive, LocalExecutionDirective)
    mission = service.mission_service.repository.get(directive.mission_id)
    plan = mission.contract.verification_plan

    # No free-text commands in verification plan
    assert plan.commands == [], (
        f"mission verification plan must have no shell commands, got: {plan.commands}"
    )
    # Structured SkillVerifierSpec in verifiers
    assert len(plan.verifiers) == 1
    assert plan.verifiers[0].verifier_id == "skill.reuse"


# ---------------------------------------------------------------------------
# Tests 5-11, 15: Validator logic — directly test the production closure
#
# These tests extract the real ``verification_plan_validator`` closure from the
# canonical service (the one built by ``get_learning_service()``) and call it
# with a _FakeSkillWithPlan.  This exercises the production validator code path
# without requiring a SkillRecord subclass that supports model_copy on the
# escalation path.
# ---------------------------------------------------------------------------


def test_05_invalid_verifier_id_escalates(tmp_path: Path) -> None:
    """Requirement 5 — validator returns False for wrong verifier_id."""
    service = _build_real_service(tmp_path)

    class _BadVerifierPlan:
        verifier_id = "evil.exec"
        version = "1"
        target_pattern = "src/*.py"
        required_observations = ("ok",)
        minimum_strength = 2

    result = service.verification_plan_validator(_FakeSkillWithPlan(_BadVerifierPlan()))
    assert result is False, (
        "validator must return False for verifier_id='evil.exec' (not 'skill.reuse')"
    )


def test_06_unsupported_verifier_version_escalates(tmp_path: Path) -> None:
    """Requirement 6 — validator returns False for unsupported version."""
    service = _build_real_service(tmp_path)

    class _BadVersionPlan:
        verifier_id = "skill.reuse"
        version = "99"  # unsupported
        target_pattern = "src/*.py"
        required_observations = ("ok",)
        minimum_strength = 2

    result = service.verification_plan_validator(_FakeSkillWithPlan(_BadVersionPlan()))
    assert result is False, "validator must return False for unsupported version"


def test_07_empty_observations_escalates(tmp_path: Path) -> None:
    """Requirement 7 — validator returns False for empty required_observations."""
    service = _build_real_service(tmp_path)

    class _EmptyObsPlan:
        verifier_id = "skill.reuse"
        version = "1"
        target_pattern = "src/*.py"
        required_observations = ()  # empty!
        minimum_strength = 2

    result = service.verification_plan_validator(_FakeSkillWithPlan(_EmptyObsPlan()))
    assert result is False, "validator must return False for empty required_observations"


def test_08_weak_minimum_strength_escalates(tmp_path: Path) -> None:
    """Requirement 8 — validator returns False for minimum_strength below policy floor."""
    service = _build_real_service(tmp_path)

    class _WeakStrengthPlan:
        verifier_id = "skill.reuse"
        version = "1"
        target_pattern = "src/*.py"
        required_observations = ("ok",)
        minimum_strength = 0  # below policy floor (1)

    result = service.verification_plan_validator(_FakeSkillWithPlan(_WeakStrengthPlan()))
    assert result is False, "validator must return False for minimum_strength=0"


def test_09_legacy_string_plan_is_quarantined_and_escalates(tmp_path: Path) -> None:
    """Requirement 9 — legacy string verification_plan quarantines to None → escalates.

    The SkillContract model_validator quarantines strings to None.  The
    canonical validator must then refuse None and return False — not call
    .strip() and crash with AttributeError.
    """
    service = _build_real_service(tmp_path)

    # Build a SkillContract (without timestamps) from the skill record payload
    skill = _valid_skill_record()
    contract_payload = {
        k: v
        for k, v in skill.model_dump(mode="python").items()
        if k not in ("created_at", "updated_at")
    }
    contract_payload["verification_plan"] = "pytest tests/test_parser.py"  # legacy string

    quarantined_contract = SkillContract.model_validate(contract_payload)
    assert quarantined_contract.verification_plan is None, (
        "legacy string must be quarantined to None by SkillContract validator"
    )

    quarantined_skill = SkillRecord(
        **quarantined_contract.model_dump(mode="python"),
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )

    # Validator must return False (not crash with AttributeError)
    result = service.verification_plan_validator(quarantined_skill)
    assert result is False, (
        "validator must return False for quarantined (None) legacy string plan"
    )

    # Full integration: reuse with this quarantined skill must escalate
    service.skill_repository.save(quarantined_skill)
    directive = service.attempt_local_reuse(
        skill_id=quarantined_skill.skill_id,
        version=quarantined_skill.version,
        mission_id="reuse-legacy-str",
        operator_id="operator-sovereign",
        goal="test legacy string plan",
        project_id="project-canonical",
        current_inputs={"format": "json", "log_path": "src/app.py"},
        current_state={"parser_version": "v2"},
        current_scope="src/app.py",
        mission_allowed_tools=("read_file", "edit_file"),
        validated_version="project-v2",
    )
    assert isinstance(directive, EscalateToFrontierDirective), (
        "quarantined (None) plan from legacy string must escalate end-to-end"
    )


def test_10_none_verification_plan_fails_closed(tmp_path: Path) -> None:
    """Requirement 10 — validator returns False for None verification plan."""
    service = _build_real_service(tmp_path)

    # Direct validator test
    result = service.verification_plan_validator(_FakeSkillWithPlan(None))
    assert result is False, "validator must fail closed (return False) for None plan"


def test_11_unknown_extra_fields_refused(tmp_path: Path) -> None:
    """Requirement 11 — validator returns False for plan objects with unknown fields.

    Rule 8 checks that ``type(plan).model_fields`` matches the expected set exactly.
    A proxy with extra model_fields is rejected.
    """
    service = _build_real_service(tmp_path)

    class _ExtraFieldPlan:
        verifier_id = "skill.reuse"
        version = "1"
        target_pattern = "src/*.py"
        required_observations = ("ok",)
        minimum_strength = 2
        unknown_extra_field = "injected"  # not in SkillVerifierSpec
        # model_fields has an extra key — this exercises Rule 8
        model_fields = {**SkillVerifierSpec.model_fields, "unknown_extra_field": None}

    result = service.verification_plan_validator(_FakeSkillWithPlan(_ExtraFieldPlan()))
    assert result is False, "validator must return False for plan with unknown extra fields"


# ---------------------------------------------------------------------------
# Test 12: Validator never raises AttributeError on typed objects
# ---------------------------------------------------------------------------


def test_12_malformed_skill_never_raises_500(tmp_path: Path) -> None:
    """Requirement 12 — no AttributeError/crash on malformed plans.

    The OLD bug: `skill.verification_plan.strip()` → AttributeError when plan
    is a SkillVerifierSpec.  The new validator uses getattr() + isinstance()
    and never calls .strip() — therefore never crashes on typed objects.
    """
    service = _build_real_service(tmp_path)
    skill = _valid_skill_record()
    service.skill_repository.save(skill)

    # This must not raise AttributeError (the old .strip() bug)
    try:
        _reuse_attempt(service, skill, mission_id="test-no-500")
    except AttributeError as exc:
        pytest.fail(
            f"Canonical get_learning_service() validator must not crash with "
            f"AttributeError (old .strip() bug regression): {exc}"
        )


# ---------------------------------------------------------------------------
# Test 13: Real dependency survives application restart / reconstruction
# ---------------------------------------------------------------------------


def test_13_dependency_survives_reconstruction(tmp_path: Path) -> None:
    """Requirement 13 — real dependency can be reconstructed and re-used."""
    for attempt in range(2):
        service = _build_real_service(tmp_path)
        skill = _valid_skill_record()
        service.skill_repository.save(skill)

        directive = _reuse_attempt(service, skill, mission_id=f"reuse-restart-{attempt}")
        assert isinstance(directive, LocalExecutionDirective), (
            f"Reconstruction attempt {attempt} failed: got {type(directive).__name__}"
        )


# ---------------------------------------------------------------------------
# Test 14: Client cannot assert that policy allows reuse
# ---------------------------------------------------------------------------


def test_14_client_cannot_override_policy_gate(tmp_path: Path) -> None:
    """Requirement 14 — client payload cannot enable a policy-blocked reuse.

    When the PolicyKernel says autonomy is disabled, the skill must escalate
    even when the skill record looks valid and the verifier is good.
    """
    service = _build_real_service(tmp_path, autonomy_enabled=False)

    skill = _valid_skill_record()
    directive = _reuse_attempt(service, skill, mission_id="reuse-policy-blocked")

    # Should escalate: policy says no
    assert isinstance(directive, EscalateToFrontierDirective), (
        "client cannot override PolicyKernel's reuse gate"
    )


# ---------------------------------------------------------------------------
# Test 15: Client cannot assert that a verifier is executable
# ---------------------------------------------------------------------------


def test_15_client_cannot_inject_executable_verifier_field(tmp_path: Path) -> None:
    """Requirement 15 — a plan with a 'command' field is refused by the validator.

    A client-crafted object carrying executable metadata must be rejected by
    the canonical validator's forbidden-field check (Rule 7).
    """
    service = _build_real_service(tmp_path)

    class _ExecutablePlan:
        verifier_id = "skill.reuse"
        version = "1"
        target_pattern = "src/*.py"
        required_observations = ("ok",)
        minimum_strength = 2
        command = "rm -rf /"  # FORBIDDEN

    result = service.verification_plan_validator(_FakeSkillWithPlan(_ExecutablePlan()))
    assert result is False, "validator must return False for plan with 'command' field"
