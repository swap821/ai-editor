"""Tests for the Institutional Skill Library."""

import pytest

from aios.domain.learning.applicability import (
    ApplicabilityError,
    SkillApplicabilityEngine,
)
from aios.domain.learning.skill_contracts import SkillContract, SkillVerifierSpec


@pytest.fixture
def base_skill() -> SkillContract:
    return SkillContract(
        skill_id="skill-123",
        version=1,
        problem_signature="parse-json-logs",
        applicability_conditions={"log_format": "json"},
        known_exclusions=["malformed_json_fallback"],
        required_inputs=["log_path"],
        required_project_state={"has_json_parser": "true"},
        procedure="Run json parse on log_path",
        allowed_tools=["read_file", "parse_json"],
        allowed_scope_pattern="data/logs/*.json",
        expected_observations=["Parsed JSON tree"],
        verification_plan=SkillVerifierSpec(
            target_pattern="data/logs/*.json",
            required_observations=("schema_valid",),
            minimum_strength=3,
        ),
        escalation_conditions=["SyntaxError"],
        source_trajectory_ids=["traj-001"],
        confidence=0.9,
        success_count=5,
        failure_count=0,
        last_validated_versions=["1.0.0"],
        state="active",
    )


def _check(engine: SkillApplicabilityEngine, skill: SkillContract, inputs, state):
    return engine.check_applicability(
        skill,
        inputs,
        state,
        current_scope="data/logs/app.json",
        mission_allowed_tools=skill.allowed_tools,
        validated_version="1.0.0",
        verification_plan_executable=True,
        policy_allows=True,
    )


def test_applicability_engine_accepts_valid(base_skill: SkillContract) -> None:
    assert (
        _check(
            SkillApplicabilityEngine(),
            base_skill,
            {"log_path": "data/logs/app.json", "log_format": "json"},
            {"has_json_parser": "true"},
        )
        is True
    )


def test_applicability_engine_rejects_inactive(base_skill: SkillContract) -> None:
    skill = base_skill.model_copy(update={"state": "deprecated"})
    with pytest.raises(ApplicabilityError, match="not active"):
        _check(
            SkillApplicabilityEngine(),
            skill,
            {"log_format": "json", "log_path": "x"},
            {"has_json_parser": "true"},
        )


def test_applicability_engine_rejects_low_confidence(base_skill: SkillContract) -> None:
    skill = base_skill.model_copy(update={"confidence": 0.5})
    with pytest.raises(ApplicabilityError, match="below minimum"):
        _check(
            SkillApplicabilityEngine(minimum_confidence=0.8),
            skill,
            {"log_format": "json", "log_path": "x"},
            {"has_json_parser": "true"},
        )


def test_applicability_engine_rejects_missing_inputs(base_skill: SkillContract) -> None:
    with pytest.raises(ApplicabilityError, match="Missing required inputs"):
        _check(
            SkillApplicabilityEngine(),
            base_skill,
            {"log_format": "json"},
            {"has_json_parser": "true"},
        )


def test_applicability_engine_rejects_state_mismatch(base_skill: SkillContract) -> None:
    with pytest.raises(ApplicabilityError, match="Project state mismatch"):
        _check(
            SkillApplicabilityEngine(),
            base_skill,
            {"log_format": "json", "log_path": "x"},
            {"has_json_parser": "false"},
        )


def test_applicability_engine_rejects_exclusion(base_skill: SkillContract) -> None:
    with pytest.raises(ApplicabilityError, match="hits known exclusion"):
        _check(
            SkillApplicabilityEngine(),
            base_skill,
            {"log_format": "json", "log_path": "x", "malformed_json_fallback": "true"},
            {"has_json_parser": "true"},
        )


def test_applicability_engine_rejects_no_source_trajectories(
    base_skill: SkillContract,
) -> None:
    skill = base_skill.model_copy(update={"source_trajectory_ids": []})
    with pytest.raises(ApplicabilityError, match="lacks verified source trajectories"):
        _check(
            SkillApplicabilityEngine(),
            skill,
            {"log_format": "json", "log_path": "x"},
            {"has_json_parser": "true"},
        )


def test_applicability_engine_rejects_tool_scope_version_and_policy_gates(
    base_skill: SkillContract,
) -> None:
    engine = SkillApplicabilityEngine()
    inputs = {"log_format": "json", "log_path": "x"}
    state = {"has_json_parser": "true"}
    with pytest.raises(ApplicabilityError, match="scope"):
        engine.check_applicability(
            base_skill,
            inputs,
            state,
            current_scope="src/app.py",
            mission_allowed_tools=base_skill.allowed_tools,
            validated_version="1.0.0",
            verification_plan_executable=True,
            policy_allows=True,
        )
    with pytest.raises(ApplicabilityError, match="tools"):
        engine.check_applicability(
            base_skill,
            inputs,
            state,
            current_scope="data/logs/app.json",
            mission_allowed_tools=("read_file",),
            validated_version="1.0.0",
            verification_plan_executable=True,
            policy_allows=True,
        )
    with pytest.raises(ApplicabilityError, match="version"):
        engine.check_applicability(
            base_skill,
            inputs,
            state,
            current_scope="data/logs/app.json",
            mission_allowed_tools=base_skill.allowed_tools,
            validated_version="project-v9",
            verification_plan_executable=True,
            policy_allows=True,
        )
    with pytest.raises(ApplicabilityError, match="Policy"):
        engine.check_applicability(
            base_skill,
            inputs,
            state,
            current_scope="data/logs/app.json",
            mission_allowed_tools=base_skill.allowed_tools,
            validated_version="1.0.0",
            verification_plan_executable=True,
            policy_allows=False,
        )
