"""Tests for Skill Reuse Orchestrator and Confidence."""
import pytest
from aios.domain.learning.skill_contracts import SkillContract
from aios.domain.learning.applicability import SkillApplicabilityEngine
from aios.domain.learning.confidence import ConfidenceUpdater
from aios.domain.learning.reuse_orchestrator import SkillReuseOrchestrator, LocalExecutionDirective, EscalateToFrontierDirective

@pytest.fixture
def base_skill():
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
        verification_plan="Assert JSON tree matches schema",
        escalation_conditions=["SyntaxError"],
        source_trajectory_ids=["traj-001"],
        confidence=0.9,
        success_count=5,
        failure_count=0,
        last_validated_versions=["1.0.0"],
        state="active"
    )

def test_confidence_updater_punishes_heavily(base_skill):
    updater = ConfidenceUpdater()
    # A success gives a small bump
    success_skill = updater.record_success(base_skill)
    assert success_skill.confidence == 0.95
    assert success_skill.success_count == 6
    
    # A failure gives a massive penalty
    fail_skill = updater.record_failure(base_skill, "verification")
    assert fail_skill.confidence == 0.70  # 0.9 - 0.2
    assert fail_skill.failure_count == 1

def test_orchestrator_returns_local_directive_on_success(base_skill):
    engine = SkillApplicabilityEngine(minimum_confidence=0.8)
    orchestrator = SkillReuseOrchestrator(engine)
    
    current_inputs = {"log_path": "/var/log/app.json"}
    current_state = {"has_json_parser": "true"}
    
    directive = orchestrator.attempt_reuse([base_skill], current_inputs, current_state)
    assert isinstance(directive, LocalExecutionDirective)
    assert directive.skill.skill_id == "skill-456"

def test_orchestrator_escalates_on_applicability_failure(base_skill):
    engine = SkillApplicabilityEngine(minimum_confidence=0.8)
    orchestrator = SkillReuseOrchestrator(engine)
    
    # Missing 'log_path' should fail applicability
    current_inputs = {"other_input": "val"}
    current_state = {"has_json_parser": "true"}
    
    directive = orchestrator.attempt_reuse([base_skill], current_inputs, current_state)
    assert isinstance(directive, EscalateToFrontierDirective)
    assert "No candidate skill met applicability conditions" in directive.reason

def test_orchestrator_escalates_when_no_candidates():
    engine = SkillApplicabilityEngine()
    orchestrator = SkillReuseOrchestrator(engine)
    
    directive = orchestrator.attempt_reuse([], {}, {})
    assert isinstance(directive, EscalateToFrontierDirective)
    assert "No candidate skills provided" in directive.reason
