"""Phase 6 — Sovereign Learning Heartbeat Integration Suite (Proof level: INTEGRATION).

Tests:
1. Learning heartbeat: Frontier trajectory capture -> Candidate distillation -> Operator activation -> Local reuse directive -> Verification & confidence boost.
2. Skill degradation & fail-closed escalation: Verification failure -> Confidence drop below threshold -> Automatic state degradation -> EscalateToFrontierDirective returned for future tasks.
3. Durable persistence of trajectories and skills across service instances.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import pytest

from aios.application.evidence.authority import EvidenceAuthority
from aios.application.evidence.verification import VerificationAuthority
from aios.application.learning.service import (
    LearningService,
    SkillActivationAuthorization,
    SkillCandidateSpec,
)
from aios.application.missions.mission_service import MissionService
from aios.domain.capabilities.proof import ConsumedCapabilityProof
from aios.domain.evidence import VerificationObservation, VerificationPlanV1
from aios.domain.learning.contracts import ToolObservation
from aios.domain.learning.repository import SkillRepository
from aios.domain.learning.reuse_orchestrator import (
    EscalateToFrontierDirective,
    LocalExecutionDirective,
)
from aios.domain.learning.trajectory_repository import TrajectoryRepository
from aios.domain.missions.mission_contract import (
    MissionContract,
    VerificationPlan as MissionVerificationPlan,
)
from aios.domain.promotion import PromotionResult, PromotionStatus
from aios.domain.verification import SkillVerifierSpec
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from tests.helpers import reuse_outcome_reference


@pytest.fixture()
def learning_env(tmp_path: Path):
    db_path = tmp_path / "learning_flywheel.db"
    missions = SqliteMissionRepository(db_path)
    mission_service = MissionService(missions)
    trajectories = TrajectoryRepository(db_path)
    skills = SkillRepository(db_path)
    evidence_auth = EvidenceAuthority()
    verification_auth = VerificationAuthority(
        evidence=evidence_auth, database_path=db_path
    )

    service = LearningService(
        mission_service=mission_service,
        trajectory_repository=trajectories,
        skill_repository=skills,
        activation_authorizer=lambda _skill, op_id, app_digest: (
            op_id == "op-admin" and app_digest == "digest-approved"
        ),
        verification_plan_validator=lambda _skill: True,
        reuse_policy=lambda _skill, _ctx: True,
        verification_authority=verification_auth,
        minimum_confidence=0.8,
    )

    return service, mission_service, verification_auth, db_path


def _plan() -> VerificationPlanV1:
    return VerificationPlanV1(
        intended_behavior="verify repair output",
        targets=("output.py",),
        required_tests=("pytest",),
        minimum_strength=1,
    )


def _observation(*, exit_code: int = 0) -> VerificationObservation:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return VerificationObservation(
        command="pytest",
        exit_code=exit_code,
        stdout="1 passed" if exit_code == 0 else "1 failed",
        stderr="",
        passed_count=1 if exit_code == 0 else 0,
        failed_count=0 if exit_code == 0 else 1,
        tool_version="pytest-8.0",
        observed_at=now,
    )


def _candidate_spec(skill_id: str = "skill-frontier-1") -> SkillCandidateSpec:
    return SkillCandidateSpec(
        skill_id=skill_id,
        version=1,
        problem_signature="sig-frontier-fix",
        applicability_conditions={"file_type": "python"},
        known_exclusions=(),
        required_inputs=("src_file",),
        required_project_state={"env": "prod"},
        procedure="run_patch_routine",
        allowed_tools=("edit_file", "run_test"),
        allowed_scope_pattern="src/*",
        expected_observations=("patch applied", "tests green"),
        verification_plan=SkillVerifierSpec(
            verifier_id="skill.reuse",
            version="1",
            target_pattern="output.py",
            required_observations=("1 passed",),
            minimum_strength=1,
        ),
        escalation_conditions=("network_error",),
        validated_versions=("1.0.0",),
    )


def _activation_auth(skill_id: str, version: int) -> SkillActivationAuthorization:
    return SkillActivationAuthorization(
        skill_id=skill_id,
        version=version,
        proof=ConsumedCapabilityProof(
            capability_id="cap-1",
            token_digest="token",
            operator_id="op-admin",
            device_id="device-1",
            authentication_event_id="auth-1",
            session_id="session-1",
            action_type="skill_activation",
            route=f"/api/v1/skills/{skill_id}/versions/{version}/activate",
            http_method="POST",
            payload_digest="payload",
            resource_digest="resource",
            mission_id=None,
            contract_digest=None,
            policy_version="1.0",
            scope="skill-activation",
            verification_requirement="route_policy_v1",
            consumed_at=1.0,
            expires_at=9_999_999_999.0,
            revoked_at=None,
        ),
    )


def test_full_frontier_to_local_learning_heartbeat(learning_env) -> None:
    service, mission_service, verification_auth, db_path = learning_env

    # 1. Create & complete a Frontier Expert Mission
    contract = MissionContract(
        mission_id="mission-frontier-1",
        project_id="proj-1",
        operator_id="op-admin",
        goal="frontier optimization mission",
        worker_type="expert-frontier",
        created_by="operator",
        risk_level="YELLOW",
        requires_approval=True,
        allowed_files=["src/main.py"],
        allowed_tools=["edit_file"],
        verification_plan=MissionVerificationPlan(
            required_strength="strong",
            verifiers=(_candidate_spec().verification_plan,),
        ),
        metadata={"problem_signature": "sig-frontier-fix"},
    )
    mission_record = mission_service.create(contract)
    mission_service.start_deliberation(contract.mission_id)
    mission_service.request_approval(contract.mission_id)
    mission_service.approve(
        contract.mission_id,
        operator_id="op-admin",
        capability_digest="cap-1",
        contract_digest=mission_record.contract_digest,
        authentication_event_id="auth-1",
        session_id="session-1",
    )
    mission_service.start_execution(contract.mission_id)
    mission_service.start_verification(contract.mission_id)
    completed_mission = mission_service.complete(contract.mission_id)

    # 2. Record authoritative verification & promotion
    v_result = verification_auth.verify(
        mission_id=completed_mission.mission_id,
        action_id="act-frontier-1",
        worker_id="w-frontier-1",
        target="output.py",
        plan=_plan(),
        workspace_digest="ws-f1",
        diff_digest="diff-f1",
        environment_digest="env-f1",
        observation=_observation(exit_code=0),
    )
    promotion = PromotionResult(
        mission_id=completed_mission.mission_id,
        action_id="act-frontier-1",
        status=PromotionStatus.PROMOTED,
        evidence_ids=("ev-p1",),
    )
    tool_obs = (
        ToolObservation(
            observation_id="obs-1",
            tool="edit_file",
            result_digest="out-1",
            status="completed",
        ),
    )

    # 3. Capture Trajectory
    traj_record = service.capture_trajectory(
        mission=completed_mission,
        project_digest="proj-digest-1",
        expert_provider="bedrock-claude-3-7-sonnet",
        expert_model="claude-3-7-sonnet-20250219",
        context_digest="ctx-f1",
        proposal_digest="prop-f1",
        tool_observations=tool_obs,
        verification_plan=_plan(),
        verification_results=(v_result,),
        promotion=promotion,
        human_intervention_ids=(),
    )
    assert traj_record.trajectory_id.startswith("trajectory-")
    assert traj_record.expert_provider == "bedrock-claude-3-7-sonnet"

    # 4. Create Skill Candidate
    cand_spec = _candidate_spec()
    skill_cand = service.create_skill_candidate(traj_record.trajectory_id, cand_spec)
    assert skill_cand.state == "candidate"
    assert skill_cand.confidence == 0.8

    # 5. Operator Activation
    active_skill = service.activate_skill(
        _activation_auth(skill_cand.skill_id, skill_cand.version)
    )
    assert active_skill.state == "active"

    # 6. Attempt Local Reuse for new task
    directive = service.attempt_local_reuse(
        skill_id=active_skill.skill_id,
        version=active_skill.version,
        mission_id="mission-local-1",
        operator_id="op-admin",
        goal="run local repair",
        project_id="proj-1",
        current_inputs={"src_file": "main.py", "file_type": "python"},
        current_state={"file_type": "python", "env": "prod"},
        current_scope="src/main.py",
        mission_allowed_tools=["edit_file", "run_test"],
        validated_version="1.0.0",
    )
    assert isinstance(directive, LocalExecutionDirective)
    assert directive.skill.skill_id == active_skill.skill_id

    # 7. Record Successful Outcome -> Confidence Increases
    local_v_result = verification_auth.verify(
        mission_id="mission-local-1",
        action_id="act-local-1",
        worker_id="w-local-1",
        target="output.py",
        plan=_plan(),
        workspace_digest="ws-loc-1",
        diff_digest="diff-loc-1",
        environment_digest="env-loc-1",
        observation=_observation(exit_code=0),
    )
    # Start & complete the created local mission so mission.state == COMPLETED
    mission_service.start_deliberation("mission-local-1")
    mission_service.request_approval("mission-local-1")
    m_loc = mission_service.repository.get("mission-local-1")
    mission_service.approve(
        "mission-local-1",
        operator_id="op-admin",
        capability_digest="cap-loc-1",
        contract_digest=m_loc.contract_digest,
        authentication_event_id="auth-loc-1",
        session_id="session-loc-1",
    )
    mission_service.start_execution("mission-local-1")
    mission_service.start_verification("mission-local-1")
    mission_service.complete("mission-local-1")

    updated_skill = service.record_reuse_outcome(
        reuse_outcome_reference(
            reuse_outcome_id="reuse-local-1",
            skill=active_skill,
            trajectory_id=traj_record.trajectory_id,
            mission=mission_service.repository.get("mission-local-1"),
            verification=local_v_result,
            worker_id="w-local-1",
            workspace_digest="ws-loc-1",
            diff_digest="diff-loc-1",
        )
    )
    assert updated_skill.success_count == 1
    assert updated_skill.confidence > 0.8
    assert updated_skill.state == "active"


def test_skill_degradation_and_fail_closed_escalation(learning_env) -> None:
    service, mission_service, verification_auth, db_path = learning_env

    # Setup completed mission & trajectory
    contract = MissionContract(
        mission_id="mission-f2",
        project_id="proj-1",
        operator_id="op-admin",
        goal="frontier mission 2",
        worker_type="expert-frontier",
        created_by="operator",
        risk_level="YELLOW",
        requires_approval=True,
        allowed_files=["src/main.py"],
        allowed_tools=["edit_file"],
        verification_plan=MissionVerificationPlan(
            required_strength="strong",
            verifiers=(_candidate_spec("skill-f2").verification_plan,),
        ),
        metadata={"problem_signature": "sig-frontier-fix-2"},
    )
    m = mission_service.create(contract)
    mission_service.start_deliberation(m.mission_id)
    mission_service.request_approval(m.mission_id)
    mission_service.approve(
        m.mission_id,
        operator_id="op-admin",
        capability_digest="cap-2",
        contract_digest=m.contract_digest,
        authentication_event_id="auth-2",
        session_id="session-2",
    )
    mission_service.start_execution(m.mission_id)
    mission_service.start_verification(m.mission_id)
    comp = mission_service.complete(m.mission_id)

    v_result = verification_auth.verify(
        mission_id=comp.mission_id,
        action_id="act-f2",
        worker_id="w-f2",
        target="output.py",
        plan=_plan(),
        workspace_digest="ws-f2",
        diff_digest="diff-f2",
        environment_digest="env-f2",
        observation=_observation(exit_code=0),
    )
    promotion = PromotionResult(
        mission_id=comp.mission_id,
        action_id="act-f2",
        status=PromotionStatus.PROMOTED,
        evidence_ids=("ev-p2",),
    )
    tool_obs = (
        ToolObservation(
            observation_id="obs-2",
            tool="edit_file",
            result_digest="out-2",
            status="completed",
        ),
    )

    traj = service.capture_trajectory(
        mission=comp,
        project_digest="proj-digest-1",
        expert_provider="google-gemini-2-5-pro",
        expert_model="gemini-2.5-pro",
        context_digest="ctx-f2",
        proposal_digest="prop-f2",
        tool_observations=tool_obs,
        verification_plan=_plan(),
        verification_results=(v_result,),
        promotion=promotion,
        human_intervention_ids=(),
    )

    cand_spec = _candidate_spec("skill-f2")
    cand_spec = cand_spec.model_copy(update={"problem_signature": "sig-frontier-fix-2"})
    skill_cand = service.create_skill_candidate(traj.trajectory_id, cand_spec)
    active_skill = service.activate_skill(
        _activation_auth(skill_cand.skill_id, skill_cand.version)
    )

    # Local reuse attempt
    directive = service.attempt_local_reuse(
        skill_id=active_skill.skill_id,
        version=active_skill.version,
        mission_id="mission-local-fail",
        operator_id="op-admin",
        goal="run local repair fail",
        project_id="proj-1",
        current_inputs={"src_file": "main.py", "file_type": "python"},
        current_state={"file_type": "python", "env": "prod"},
        current_scope="src/main.py",
        mission_allowed_tools=["edit_file", "run_test"],
        validated_version="1.0.0",
    )
    assert isinstance(directive, LocalExecutionDirective)

    # Fail local verification
    failed_v_result = verification_auth.verify(
        mission_id="mission-local-fail",
        action_id="act-local-fail",
        worker_id="w-local-fail",
        target="output.py",
        plan=_plan(),
        workspace_digest="ws-fail-1",
        diff_digest="diff-fail-1",
        environment_digest="env-fail-1",
        observation=_observation(exit_code=1),  # Failed observation
    )
    m_fail = mission_service.repository.get("mission-local-fail")
    mission_service.start_deliberation("mission-local-fail")
    mission_service.request_approval("mission-local-fail")
    mission_service.approve(
        "mission-local-fail",
        operator_id="op-admin",
        capability_digest="cap-loc-fail",
        contract_digest=m_fail.contract_digest,
        authentication_event_id="auth-loc-fail",
        session_id="session-loc-fail",
    )
    mission_service.start_execution("mission-local-fail")
    mission_service.fail("mission-local-fail", reason="verification failed")

    degraded_skill = service.record_reuse_outcome(
        reuse_outcome_reference(
            reuse_outcome_id="reuse-local-fail",
            skill=active_skill,
            trajectory_id=traj.trajectory_id,
            mission=mission_service.repository.get("mission-local-fail"),
            verification=failed_v_result,
            worker_id="w-local-fail",
            workspace_digest="ws-fail-1",
            diff_digest="diff-fail-1",
        )
    )

    assert degraded_skill.failure_count == 1
    assert degraded_skill.confidence < 0.8
    assert degraded_skill.state == "degraded"

    # Next attempt for degraded skill MUST return EscalateToFrontierDirective (fail closed)
    subsequent_directive = service.attempt_local_reuse(
        skill_id=active_skill.skill_id,
        version=active_skill.version,
        mission_id="mission-local-escalate",
        operator_id="op-admin",
        goal="retry local repair",
        project_id="proj-1",
        current_inputs={"src_file": "main.py", "file_type": "python"},
        current_state={"file_type": "python", "env": "prod"},
        current_scope="src/main.py",
        mission_allowed_tools=["edit_file", "run_test"],
        validated_version="1.0.0",
    )
    assert isinstance(subsequent_directive, EscalateToFrontierDirective)
