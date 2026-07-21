"""Tests for skill reuse directives and confidence."""

import pytest

from aios.domain.learning.applicability import SkillApplicabilityEngine
from aios.domain.learning.confidence import ConfidenceUpdater
from aios.domain.learning.reuse_orchestrator import (
    EscalateToFrontierDirective,
    LocalExecutionDirective,
    SkillReuseOrchestrator,
)
from aios.domain.learning.skill_contracts import SkillContract, SkillVerifierSpec


@pytest.fixture
def base_skill() -> SkillContract:
    return SkillContract(
        skill_id="skill-456",
        version=1,
        problem_signature="parse-json-logs",
        applicability_conditions={"log_format": "json"},
        known_exclusions=[],
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


def _kwargs(skill: SkillContract) -> dict[str, object]:
    return {
        "current_scope": "data/logs/app.json",
        "mission_allowed_tools": skill.allowed_tools,
        "validated_version": "1.0.0",
        "verification_plan_executable": True,
        "policy_allows": True,
    }


def test_confidence_updater_punishes_heavily(base_skill: SkillContract) -> None:
    updater = ConfidenceUpdater()
    success_skill = updater.record_success(base_skill)
    assert success_skill.confidence == 0.95
    assert success_skill.success_count == 6
    fail_skill = updater.record_failure(base_skill, "verification")
    assert fail_skill.confidence == 0.70
    assert fail_skill.failure_count == 1


def test_orchestrator_returns_local_directive_on_success(
    base_skill: SkillContract,
) -> None:
    orchestrator = SkillReuseOrchestrator(
        SkillApplicabilityEngine(minimum_confidence=0.8)
    )
    directive = orchestrator.attempt_reuse(
        [base_skill],
        {"log_path": "data/logs/app.json", "log_format": "json"},
        {"has_json_parser": "true"},
        **_kwargs(base_skill),
    )
    assert isinstance(directive, LocalExecutionDirective)
    assert directive.skill.skill_id == "skill-456"


def test_orchestrator_escalates_on_applicability_failure(
    base_skill: SkillContract,
) -> None:
    orchestrator = SkillReuseOrchestrator(
        SkillApplicabilityEngine(minimum_confidence=0.8)
    )
    directive = orchestrator.attempt_reuse(
        [base_skill],
        {"log_format": "json"},
        {"has_json_parser": "true"},
        **_kwargs(base_skill),
    )
    assert isinstance(directive, EscalateToFrontierDirective)
    assert "No candidate skill met applicability conditions" in directive.reason


def test_orchestrator_escalates_when_no_candidates() -> None:
    directive = SkillReuseOrchestrator(SkillApplicabilityEngine()).attempt_reuse(
        [], {}, {}
    )
    assert isinstance(directive, EscalateToFrontierDirective)
    assert "No candidate skills provided" in directive.reason
