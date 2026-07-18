from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aios.application.learning.service import (
    LearningService,
    SkillActivationDenied,
    SkillCandidateSpec,
)
from aios.api.deps import get_learning_service
from aios.api.main import app
from aios.domain.evidence import VerificationPlanV1, VerificationResult
from aios.domain.learning.contracts import ToolObservation
from aios.domain.learning.repository import SkillRecord
from aios.domain.verification import SkillVerifierSpec
from aios.domain.learning.trajectory_repository import TrajectoryRepository
from aios.domain.missions.mission_contract import MissionContract
from aios.domain.missions.mission_state import MissionState
from aios.domain.promotion import PromotionResult, PromotionStatus
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.application.missions.mission_service import MissionService


def _mission() -> MissionContract:
    return MissionContract(
        mission_id="frontier-mission-1",
        project_id="project-1",
        operator_id="operator-1",
        goal="repair the JSON log parser",
        worker_type="frontier-worker",
        created_by="council",
        allowed_files=["src/parser.py"],
        allowed_tools=["read_file", "edit_file", "run_tests"],
        metadata={"problem_signature": "repair-json-parser"},
    )


def _verification() -> VerificationResult:
    return VerificationResult(
        verification_id="verification-1",
        mission_id="frontier-mission-1",
        action_id="action-1",
        target="unit-tests",
        passed=True,
        strength=4,
        required_strength=3,
        evidence_ids=("evidence-1",),
        workspace_digest="workspace-1",
        diff_digest="diff-1",
        environment_digest="environment-1",
        command="pytest tests/test_parser.py",
        output_digest="output-1",
        tool_version="pytest-8",
    )


def _promotion() -> PromotionResult:
    return PromotionResult(
        mission_id="frontier-mission-1",
        action_id="action-1",
        status=PromotionStatus.PROMOTED,
        evidence_ids=("evidence-1",),
    )


def _candidate() -> SkillCandidateSpec:
    return SkillCandidateSpec(
        skill_id="skill-parser-repair",
        version=1,
        problem_signature="repair-json-parser",
        applicability_conditions={"format": "json"},
        known_exclusions=("legacy-parser",),
        required_inputs=("log_path",),
        required_project_state={"parser_version": "v2"},
        procedure="Read the bounded parser diff and run the declared tests.",
        allowed_tools=("read_file", "edit_file", "run_tests"),
        allowed_scope_pattern="src/*.py",
        expected_observations=("tests pass",),
        verification_plan=SkillVerifierSpec(
            target_pattern="src/*.py",
            required_observations=("schema_valid",),
            minimum_strength=3,
        ),
        escalation_conditions=("schema mismatch",),
        validated_versions=("project-v2",),
    )


def test_capture_is_structured_durable_and_derived_from_authoritative_mission(
    tmp_path: Path,
) -> None:
    mission_repo = SqliteMissionRepository(tmp_path / "missions.db")
    mission = mission_repo.create(_mission(), state=MissionState.COMPLETED)
    trajectories = TrajectoryRepository(tmp_path / "learning.db")
    service = LearningService(
        mission_service=MissionService(mission_repo),
        trajectory_repository=trajectories,
    )

    record = service.capture_trajectory(
        mission=mission,
        project_digest="project-digest-1",
        expert_provider="gemini",
        expert_model="gemini-2.5-pro",
        context_digest="context-1",
        proposal_digest="proposal-1",
        tool_observations=(
            ToolObservation(
                observation_id="tool-1",
                tool="run_tests",
                result_digest="tool-result-1",
                status="completed",
            ),
        ),
        verification_plan=VerificationPlanV1(
            intended_behavior="parser repair passes",
            targets=("unit-tests",),
            required_tests=("pytest tests/test_parser.py",),
            minimum_strength=3,
        ),
        verification_results=(_verification(),),
        promotion=_promotion(),
        human_intervention_ids=("approval-1",),
    )

    assert record.mission_id == mission.mission_id
    assert record.contract_digest == mission.contract_digest
    assert record.verification_ids == ("verification-1",)
    assert trajectories.get(record.trajectory_id) == record
    assert (
        TrajectoryRepository(tmp_path / "learning.db").get(record.trajectory_id)
        == record
    )


def test_free_text_or_forged_verification_cannot_qualify() -> None:
    from aios.domain.learning.contracts import ExpertTrajectory
    from aios.domain.learning.trajectory_gate import TrajectoryGate, TrajectoryGateError

    trajectory = ExpertTrajectory(
        trajectory_id="trajectory-1",
        mission_id="mission-1",
        contract_digest="contract-1",
        problem_signature="repair-json-parser",
        project_digest="project-1",
        expert_provider="gemini",
        expert_model="gemini-2.5-pro",
        context_digest="context-1",
        proposal_digest="proposal-1",
        actions_attempted=1,
        failed_attempts=0,
        successful_actions=1,
        tool_observations=(
            ToolObservation(
                observation_id="tool-1",
                tool="run_tests",
                result_digest="tool-result-1",
                status="completed",
            ),
        ),
        verification_plan=VerificationPlanV1(
            intended_behavior="repair",
            targets=("unit-tests",),
            required_tests=("pytest",),
        ),
        verification_results=(),
        verification_strength=0,
        promotion_status="promoted",
        promotion_evidence_ids=("evidence-1",),
        rollback_result=None,
        human_intervention_ids=(),
        final_mission_status="completed",
        final_outcome="success",
    )
    with pytest.raises(TrajectoryGateError, match="structured verification"):
        TrajectoryGate().qualify(trajectory)


def test_activation_requires_external_human_authority_and_reuse_creates_mission(
    tmp_path: Path,
) -> None:
    mission_repo = SqliteMissionRepository(tmp_path / "missions.db")
    source = mission_repo.create(_mission(), state=MissionState.COMPLETED)
    skill_repo = TrajectoryRepository(tmp_path / "learning.db")
    service = LearningService(
        mission_service=MissionService(mission_repo),
        trajectory_repository=skill_repo,
    )
    trajectory = service.capture_trajectory(
        mission=source,
        project_digest="project-digest-1",
        expert_provider="gemini",
        expert_model="gemini-2.5-pro",
        context_digest="context-1",
        proposal_digest="proposal-1",
        tool_observations=(
            ToolObservation(
                observation_id="tool-1",
                tool="run_tests",
                result_digest="tool-result-1",
                status="completed",
            ),
        ),
        verification_plan=VerificationPlanV1(
            intended_behavior="parser repair passes",
            targets=("unit-tests",),
            required_tests=("pytest tests/test_parser.py",),
        ),
        verification_results=(_verification(),),
        promotion=_promotion(),
        human_intervention_ids=(),
    )
    candidate = service.create_skill_candidate(trajectory.trajectory_id, _candidate())
    with pytest.raises(SkillActivationDenied, match="external authority"):
        service.activate_skill(
            candidate.skill_id,
            candidate.version,
            operator_id="operator-1",
            approval_digest="approval-1",
        )

    authorized_service = LearningService(
        mission_service=MissionService(mission_repo),
        trajectory_repository=skill_repo,
        activation_authorizer=lambda *_args: True,
        verification_plan_validator=lambda *_args: True,
        reuse_policy=lambda *_args: True,
    )
    active = authorized_service.activate_skill(
        candidate.skill_id,
        candidate.version,
        operator_id="operator-1",
        approval_digest="approval-1",
    )
    assert active.state == "active"

    reuse = authorized_service.attempt_local_reuse(
        skill_id=active.skill_id,
        version=active.version,
        mission_id="local-reuse-1",
        operator_id="operator-1",
        goal="repair another JSON parser instance",
        project_id="project-1",
        current_inputs={"format": "json", "log_path": "src/app.py"},
        current_state={"parser_version": "v2"},
        current_scope="src/app.py",
        mission_allowed_tools=("read_file", "edit_file", "run_tests"),
        validated_version="project-v2",
    )
    assert reuse.directive_type == "local_execute"
    assert mission_repo.get("local-reuse-1").state is MissionState.DRAFT

    escalated = authorized_service.attempt_local_reuse(
        skill_id=active.skill_id,
        version=active.version,
        mission_id="local-reuse-2",
        operator_id="operator-1",
        goal="repair an excluded legacy parser",
        project_id="project-1",
        current_inputs={
            "format": "json",
            "log_path": "src/app.py",
            "legacy-parser": "true",
        },
        current_state={"parser_version": "v2"},
        current_scope="src/app.py",
        mission_allowed_tools=("read_file", "edit_file", "run_tests"),
        validated_version="project-v2",
    )
    assert escalated.directive_type == "escalate"
    with pytest.raises(Exception):
        mission_repo.get("local-reuse-2")


def test_reuse_outcome_updates_confidence_only_from_current_verification(
    tmp_path: Path,
) -> None:
    mission_repo = SqliteMissionRepository(tmp_path / "missions.db")
    learning_db = tmp_path / "learning.db"
    service = LearningService(
        mission_service=MissionService(mission_repo),
        trajectory_repository=TrajectoryRepository(learning_db),
    )
    skill = SkillRecord(
        skill_id="skill-outcome",
        version=1,
        problem_signature="repair-json-parser",
        applicability_conditions={"format": "json"},
        known_exclusions=(),
        required_inputs=("log_path",),
        required_project_state={"parser_version": "v2"},
        procedure="repair",
        allowed_tools=("run_tests",),
        allowed_scope_pattern="src/*.py",
        expected_observations=("tests pass",),
        verification_plan=SkillVerifierSpec(
            target_pattern="src/*.py",
            required_observations=("schema_valid",),
            minimum_strength=3,
        ),
        escalation_conditions=("mismatch",),
        source_trajectory_ids=("trajectory-1",),
        confidence=0.8,
        success_count=0,
        failure_count=0,
        last_validated_versions=("project-v2",),
        state="active",
        created_at="2026-07-18T00:00:00Z",
        updated_at="2026-07-18T00:00:00Z",
    )
    service.skill_repository.save(skill)

    successful = mission_repo.create(
        _mission().model_copy(update={"mission_id": "reuse-success"}),
        state=MissionState.COMPLETED,
    )
    success_result = _verification().model_copy(
        update={"mission_id": successful.mission_id, "action_id": "reuse-action"}
    )
    updated = service.record_reuse_outcome(
        skill_id=skill.skill_id,
        version=skill.version,
        mission_id=successful.mission_id,
        verification_results=(success_result,),
        workspace_digest=success_result.workspace_digest,
        diff_digest=success_result.diff_digest,
    )
    assert updated.success_count == 1
    assert updated.confidence == 0.85

    failed = mission_repo.create(
        _mission().model_copy(update={"mission_id": "reuse-failure"}),
        state=MissionState.FAILED,
    )
    failed_result = success_result.model_copy(
        update={"mission_id": failed.mission_id, "passed": False, "strength": 0}
    )
    degraded = service.record_reuse_outcome(
        skill_id=skill.skill_id,
        version=skill.version,
        mission_id=failed.mission_id,
        verification_results=(failed_result,),
        workspace_digest=failed_result.workspace_digest,
        diff_digest=failed_result.diff_digest,
    )
    assert degraded.failure_count == 1
    assert degraded.state == "degraded"


def test_mounted_skill_reuse_creates_only_a_governed_mission(
    tmp_path: Path,
) -> None:
    mission_repo = SqliteMissionRepository(tmp_path / "missions.db")
    service = LearningService(
        mission_service=MissionService(mission_repo),
        trajectory_repository=TrajectoryRepository(tmp_path / "learning.db"),
        verification_plan_validator=lambda *_args: True,
        reuse_policy=lambda *_args: True,
    )
    service.skill_repository.save(
        SkillRecord(
            skill_id="skill-http",
            version=1,
            problem_signature="repair-json-parser",
            applicability_conditions={"format": "json"},
            known_exclusions=(),
            required_inputs=("log_path",),
            required_project_state={"parser_version": "v2"},
            procedure="repair",
            allowed_tools=("read_file", "edit_file", "run_tests"),
            allowed_scope_pattern="src/*.py",
            expected_observations=("tests pass",),
            verification_plan=SkillVerifierSpec(
                target_pattern="src/*.py",
                required_observations=("schema_valid",),
                minimum_strength=3,
            ),
            escalation_conditions=("mismatch",),
            source_trajectory_ids=("trajectory-http",),
            confidence=0.9,
            success_count=3,
            failure_count=0,
            last_validated_versions=("project-v2",),
            state="active",
            created_at="2026-07-18T00:00:00Z",
            updated_at="2026-07-18T00:00:00Z",
        )
    )
    app.dependency_overrides[get_learning_service] = lambda: service
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.post(
                "/api/v1/skills/reuse",
                json={
                    "skill_id": "skill-http",
                    "version": 1,
                    "mission_id": "http-reuse-1",
                    "goal": "repair another parser",
                    "project_id": "project-1",
                    "current_inputs": {"format": "json", "log_path": "src/app.py"},
                    "current_state": {"parser_version": "v2"},
                    "current_scope": "src/app.py",
                    "mission_allowed_tools": ["read_file", "edit_file", "run_tests"],
                    "validated_version": "project-v2",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["directive_type"] == "local_execute"
    assert body["mission_id"] == "http-reuse-1"
    assert body["execution"] == "mission_service_draft_only"
    assert mission_repo.get("http-reuse-1").state is MissionState.DRAFT
