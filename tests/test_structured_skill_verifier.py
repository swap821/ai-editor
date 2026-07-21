from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from aios.application.learning.service import LearningService
from aios.domain.learning.applicability import (
    ApplicabilityError,
    SkillApplicabilityEngine,
)
from aios.domain.learning.repository import SkillRecord
from aios.domain.learning.skill_contracts import SkillContract, SkillVerifierSpec
from aios.domain.missions.mission_contract import MissionContract
from aios.domain.missions.mission_state import MissionState
from aios.application.missions.mission_service import MissionService
from aios.domain.learning.trajectory_repository import TrajectoryRepository
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)


def _verifier() -> SkillVerifierSpec:
    return SkillVerifierSpec(
        target_pattern="src/*.py",
        required_observations=("schema_valid", "target_preserved"),
        minimum_strength=3,
    )


def _skill(*, plan: SkillVerifierSpec | None) -> SkillContract:
    return SkillContract(
        skill_id="skill-structured",
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
        verification_plan=plan,
        escalation_conditions=("schema mismatch",),
        source_trajectory_ids=("trajectory-1",),
        confidence=0.9,
        success_count=2,
        failure_count=0,
        last_validated_versions=("project-v2",),
        state="active",
    )


def test_structured_skill_verifier_is_typed_and_shell_free() -> None:
    plan = _verifier()
    assert plan.verifier_id == "skill.reuse"
    assert plan.version == "1"
    assert plan.required_observations == ("schema_valid", "target_preserved")


def test_legacy_free_text_skill_is_quarantined_and_not_applicable() -> None:
    legacy = _skill(plan=None)
    with pytest.raises(ApplicabilityError, match="structured verifier"):
        SkillApplicabilityEngine().check_applicability(
            legacy,
            {"format": "json", "log_path": "src/app.py"},
            {"parser_version": "v2"},
            current_scope="src/app.py",
            mission_allowed_tools=legacy.allowed_tools,
            validated_version="project-v2",
            verification_plan_executable=True,
            policy_allows=True,
        )


def test_legacy_persisted_string_is_quarantined_on_load() -> None:
    payload = _skill(plan=_verifier()).model_dump(mode="python")
    payload["verification_plan"] = "pytest tests/test_parser.py"
    restored = SkillContract.model_validate(payload)
    assert restored.verification_plan is None


@pytest.mark.parametrize("field", ["command", "image"])
def test_skill_verifier_rejects_learned_execution_fields(field: str) -> None:
    payload = _verifier().model_dump(mode="json")
    payload[field] = "learned unsafe value"
    with pytest.raises(ValidationError):
        SkillVerifierSpec.model_validate(payload)


def test_skill_reuse_mission_contains_structured_verifier_not_command(
    tmp_path: Path,
) -> None:
    mission_repo = SqliteMissionRepository(tmp_path / "missions.db")
    source = MissionContract(
        mission_id="source-1",
        project_id="project-1",
        operator_id="operator-1",
        goal="source mission",
        worker_type="frontier-worker",
        created_by="council",
    )
    mission_repo.create(source, state=MissionState.COMPLETED)
    learning = LearningService(
        mission_service=MissionService(mission_repo),
        trajectory_repository=TrajectoryRepository(tmp_path / "learning.db"),
        verification_plan_validator=lambda _skill: True,
        reuse_policy=lambda _skill, _context: True,
    )
    skill = SkillRecord(
        **_skill(plan=_verifier()).model_dump(mode="python"),
        created_at="2026-07-19T00:00:00Z",
        updated_at="2026-07-19T00:00:00Z",
    )
    learning.skill_repository.save(skill)

    directive = learning.attempt_local_reuse(
        skill_id=skill.skill_id,
        version=skill.version,
        mission_id="reuse-1",
        operator_id="operator-1",
        goal="reuse the verified repair",
        project_id="project-1",
        current_inputs={"format": "json", "log_path": "src/app.py"},
        current_state={"parser_version": "v2"},
        current_scope="src/app.py",
        mission_allowed_tools=skill.allowed_tools,
        validated_version="project-v2",
    )

    assert directive.directive_type == "local_execute"
    created = mission_repo.get("reuse-1")
    assert created is not None
    assert created.contract.verification_plan.commands == []
    assert created.contract.verification_plan.verifiers[0].verifier_id == "skill.reuse"
