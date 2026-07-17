"""Tests for the Institutional Skill Library."""
import pytest
from aios.domain.learning.skill_contracts import SkillContract
from aios.domain.learning.applicability import SkillApplicabilityEngine, ApplicabilityError

@pytest.fixture
def base_skill():
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
        verification_plan="Assert JSON tree matches schema",
        escalation_conditions=["SyntaxError"],
        source_trajectory_ids=["traj-001"],
        confidence=0.9,
        success_count=5,
        failure_count=0,
        last_validated_versions=["1.0.0"],
        state="active"
    )

def test_applicability_engine_accepts_valid(base_skill):
    engine = SkillApplicabilityEngine()
    current_inputs = {"log_path": "/var/log/app.json"}
    current_state = {"has_json_parser": "true"}
    
    assert engine.check_applicability(base_skill, current_inputs, current_state) is True

def test_applicability_engine_rejects_inactive(base_skill):
    skill = base_skill.model_copy(update={"state": "deprecated"})
    engine = SkillApplicabilityEngine()
    with pytest.raises(ApplicabilityError, match="not active"):
        engine.check_applicability(skill, {"log_path": "/path"}, {"has_json_parser": "true"})

def test_applicability_engine_rejects_low_confidence(base_skill):
    skill = base_skill.model_copy(update={"confidence": 0.5})
    engine = SkillApplicabilityEngine(minimum_confidence=0.8)
    with pytest.raises(ApplicabilityError, match="below minimum"):
        engine.check_applicability(skill, {"log_path": "/path"}, {"has_json_parser": "true"})

def test_applicability_engine_rejects_missing_inputs(base_skill):
    engine = SkillApplicabilityEngine()
    with pytest.raises(ApplicabilityError, match="Missing required inputs"):
        # Missing 'log_path'
        engine.check_applicability(base_skill, {"other_input": "val"}, {"has_json_parser": "true"})

def test_applicability_engine_rejects_state_mismatch(base_skill):
    engine = SkillApplicabilityEngine()
    with pytest.raises(ApplicabilityError, match="Project state mismatch"):
        # State mismatch for 'has_json_parser'
        engine.check_applicability(base_skill, {"log_path": "/path"}, {"has_json_parser": "false"})

def test_applicability_engine_rejects_exclusion(base_skill):
    engine = SkillApplicabilityEngine()
    with pytest.raises(ApplicabilityError, match="hits known exclusion"):
        # Exclusion present in inputs
        engine.check_applicability(base_skill, {"log_path": "/path", "malformed_json_fallback": "true"}, {"has_json_parser": "true"})

def test_applicability_engine_rejects_no_source_trajectories(base_skill):
    skill = base_skill.model_copy(update={"source_trajectory_ids": []})
    engine = SkillApplicabilityEngine()
    with pytest.raises(ApplicabilityError, match="lacks verified source trajectories"):
        engine.check_applicability(skill, {"log_path": "/path"}, {"has_json_parser": "true"})
