"""Phase 10 — Sovereign Intelligence & Maintenance Flywheel Integration Proof (Proof level: INTEGRATION).

Executes the in-process integration test loop:
1. Human-approved scan -> Real finding
2. Human-approved repair mission -> Worker execution proposal
3. Verification -> Controlled promotion -> Post-promotion rescan proof
4. Signed Audit Trail Verification
5. Frontier expert trajectory capture -> Candidate skill distillation
6. Human capability-backed activation -> Active local skill reuse
7. Automatic fail-closed degradation & frontier escalation on verification failure
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest

from aios.application.evidence.authority import EvidenceAuthority
from aios.application.evidence.verification import VerificationAuthority
from aios.application.evidence.verifier_registry import VerifierRegistry
from aios.application.executor.service import ExecutorService
from aios.application.governance import EmergencyStopController, EmergencyStopHooks
from aios.application.learning.service import (
    LearningService,
    SkillCandidateSpec,
)
from aios.application.maintenance.service import MaintenanceConvergenceService
from aios.application.missions.mission_service import MissionService
from aios.application.promotion.authority import PromotionAuthority
from aios.application.workers.foundry import WorkerFoundry
from aios.application.workspaces import StagedWorkspaceManager
from aios.domain.evidence import VerificationObservation, VerificationPlanV1
from aios.domain.executor import ExecutorResult
from aios.domain.learning.contracts import ToolObservation
from aios.domain.learning.repository import SkillRepository
from aios.domain.learning.reuse_orchestrator import (
    EscalateToFrontierDirective,
    LocalExecutionDirective,
)
from aios.domain.learning.trajectory_repository import TrajectoryRepository
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
from aios.domain.maintenance.repository import MaintenanceFindingRepository
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.scan_repository import MaintenanceScanRepository
from aios.domain.missions.mission_contract import (
    MissionContract,
    VerificationPlan as MissionVerificationPlan,
)
from aios.domain.promotion import PromotionResult, PromotionStatus
from aios.domain.verification import SkillVerifierSpec
from aios.domain.workers.worker_contract import WorkerStrategyName
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.runtime.cortex_bus import CortexBus
from aios.security.audit_logger import init_audit_db, log_action, verify_chain


def _finding(*, target_id: str = "bug.txt", target_digest: str, source_digest: str) -> MaintenanceFinding:
    return MaintenanceFinding(
        finding_id="finding-e2e-flywheel",
        fingerprint="e2e-flywheel-fingerprint",
        scanner_id="admitted-scanner",
        scanner_version="1",
        kind="sovereign_defect",
        severity="high",
        confidence=1.0,
        evidence_quality="deterministic",
        target_id=target_id,
        target_digest=target_digest,
        source_digest=source_digest,
        first_seen="2026-07-19T00:00:00Z",
        last_seen="2026-07-19T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="e2e defect present",
    )


def _scanner(context):  # noqa: ANN001
    payload = context.read_text("bug.txt")
    if "DEFECT_MARKER" not in payload:
        return ()
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return (_finding(target_digest=digest, source_digest=digest),)


def _contract(root: Path) -> BoundedScanContract:
    return BoundedScanContract(
        allowed_root=str(root),
        max_files=4,
        max_total_bytes=4096,
        max_file_bytes=1024,
        deadline=10,
        max_findings=4,
        git_history_allowed=False,
    )


def _verification_plan() -> VerificationPlanV1:
    return VerificationPlanV1(
        intended_behavior="verify e2e repair output",
        targets=("bug.txt",),
        required_tests=("pytest tests/",),
        minimum_strength=1,
    )


def _observation(*, exit_code: int = 0) -> VerificationObservation:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return VerificationObservation(
        command="pytest tests/",
        exit_code=exit_code,
        stdout="1 passed" if exit_code == 0 else "1 failed",
        stderr="",
        passed_count=1 if exit_code == 0 else 0,
        failed_count=0 if exit_code == 0 else 1,
        tool_version="pytest-8.0",
        observed_at=now,
    )


@pytest.mark.anyio
async def test_complete_e2e_sovereign_intelligence_and_maintenance_flywheel(tmp_path: Path) -> None:
    # -----------------------------------------------------------------------
    # Step 1: Environment Setup & Durable Repositories
    # -----------------------------------------------------------------------
    project = tmp_path / "project"
    project.mkdir()
    (project / "bug.txt").write_text("DEFECT_MARKER\n", encoding="utf-8")

    db_path = tmp_path / "sovereign_operational.db"
    audit_db_path = tmp_path / "audit.db"
    init_audit_db(audit_db_path)

    workspace = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    missions = SqliteMissionRepository(db_path)
    mission_service = MissionService(missions, workspace_manager=workspace)
    finding_repository = MaintenanceFindingRepository(db_path)
    scan_repository = MaintenanceScanRepository(db_path)
    bus = CortexBus(db_path=tmp_path / "cortex_bus.db")

    emergency_stop = EmergencyStopController(
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda _reason="": 0,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda _reason="": None,
        )
    )

    class _E2ERepairStrategy:
        name = WorkerStrategyName.DETERMINISTIC

        async def run(self, request) -> Any:  # noqa: ANN001
            staged = request.context.get("staged_workspace", {})
            workspace_path = Path(staged.get("workspace_path", request.spec.scope.get("workspace_root", "")))
            if workspace_path.exists():
                (workspace_path / "bug.txt").write_text("REPAIRED_CLEAN\n", encoding="utf-8")
            return SimpleNamespace(worker_id=request.spec.worker_id, status="completed")

    foundry = WorkerFoundry(
        workspace_manager=workspace,
        bus=bus,
        strategies={WorkerStrategyName.DETERMINISTIC.value: _E2ERepairStrategy()},
        emergency_stop=emergency_stop,
    )

    executor_runner = lambda job: ExecutorResult(  # noqa: E731
        job_id=job.job_id,
        status="completed",
        exit_code=0,
        stdout="clean execution",
        isolation_verified=True,
        environment_digest="env-e2e-1",
    )
    executor_service = ExecutorService(
        profile="test",
        runner=executor_runner,
        backend_name="private_service",
    )

    evidence_auth = EvidenceAuthority()
    verification_auth = VerificationAuthority(evidence=evidence_auth, database_path=db_path)

    maint_service = MaintenanceConvergenceService(
        finding_repository=finding_repository,
        scan_repository=scan_repository,
        mission_service=mission_service,
        worker_foundry=foundry,
        executor_service=executor_service,
        verifier_registry=VerifierRegistry(scanner_adapters={"admitted-scanner": _scanner}),
        verification_authority=verification_auth,
        promotion_authority=PromotionAuthority(workspace, emergency_stop=emergency_stop),
        workspace_manager=workspace,
        lifecycle_engine=MaintenanceLifecycleEngine(),
    )

    learning_trajectories = TrajectoryRepository(db_path)
    learning_skills = SkillRepository(db_path)

    learning_service = LearningService(
        mission_service=mission_service,
        trajectory_repository=learning_trajectories,
        skill_repository=learning_skills,
        activation_authorizer=lambda _skill, op_id, app_digest: op_id == "op-admin" and app_digest == "digest-approved",
        verification_plan_validator=lambda _skill: True,
        reuse_policy=lambda _skill, _ctx: True,
        verification_authority=verification_auth,
        minimum_confidence=0.8,
    )

    # -----------------------------------------------------------------------
    # Step 2: Scan -> Defect Finding Detected
    # -----------------------------------------------------------------------
    scan_res = maint_service.run_scan(
        contract=_contract(project),
        scanner=_scanner,
        scanner_id="admitted-scanner",
        scanner_version="1",
        target_id=str(project),
        source_digest=hashlib.sha256("DEFECT_MARKER\n".encode()).hexdigest(),
    )
    assert len(scan_res.findings) == 1
    finding = scan_res.findings[0]
    assert finding.fingerprint == "e2e-flywheel-fingerprint"
    log_action("maint-scanner", f"scan_completed findings={len(scan_res.findings)}", zone="GREEN", db_path=audit_db_path)

    # -----------------------------------------------------------------------
    # Step 3: Repair Mission -> Approve -> Worker Execution -> Verification -> Promotion -> Post-rescan Proof -> Closed
    # -----------------------------------------------------------------------
    record = maint_service.create_repair_mission(
        finding.fingerprint,
        operator_id="op-admin",
        workspace_root=str(project),
    )
    mission_id = record.mission_id
    mission_service.start_deliberation(mission_id)
    mission_service.request_approval(mission_id)
    mission_service.approve(
        mission_id,
        operator_id="op-admin",
        capability_digest="cap-e2e-1",
        contract_digest=record.contract_digest,
        authentication_event_id="auth-e2e-1",
        session_id="session-e2e-1",
    )
    log_action("op-admin", f"repair_create mission_id={mission_id}", zone="YELLOW", db_path=audit_db_path)

    repair_res = await maint_service.run_approved_repair(
        mission_id,
        scanner=_scanner,
        rescan_contract=_contract(project),
        capability_consumer=lambda _r: True,
        create_checkpoint=lambda _r: "cp-e2e",
        restore_checkpoint=lambda _c, _r: True,
        smoke_test=lambda _r: True,
    )
    assert repair_res.status == "VERIFIED_RESOLVED"
    assert repair_res.scan_id is not None
    log_action("maint-worker", f"repair_completed mission_id={mission_id}", zone="YELLOW", db_path=audit_db_path)

    # Verify bug.txt on disk is promoted and clean
    assert (project / "bug.txt").read_text(encoding="utf-8") == "REPAIRED_CLEAN\n"

    # -----------------------------------------------------------------------
    # Step 4: Audit Trail Hash Chain & Ed25519 Signature Verification
    # -----------------------------------------------------------------------
    audit_status = verify_chain(db_path=audit_db_path)
    assert audit_status.valid is True
    assert audit_status.total_entries == 3
    assert audit_status.signature_valid is True

    # -----------------------------------------------------------------------
    # Step 5: Frontier Expert Trajectory Capture -> Skill Distillation
    # -----------------------------------------------------------------------
    verifier_spec = SkillVerifierSpec(
        verifier_id="skill.reuse",
        version="1",
        target_pattern="bug.txt",
        required_observations=("1 passed",),
        minimum_strength=1,
    )

    candidate_spec = SkillCandidateSpec(
        skill_id="skill-e2e-flywheel",
        version=1,
        problem_signature="e2e-flywheel-fingerprint",
        applicability_conditions={"file_type": "text"},
        known_exclusions=(),
        required_inputs=("bug.txt",),
        required_project_state={"env": "prod"},
        procedure="run_deterministic_repair",
        allowed_tools=("edit_file",),
        allowed_scope_pattern="project/*",
        expected_observations=("REPAIRED_CLEAN",),
        verification_plan=verifier_spec,
        escalation_conditions=("network_error",),
        validated_versions=("1.0.0",),
    )

    frontier_contract = MissionContract(
        mission_id="mission-frontier-flywheel",
        project_id="proj-e2e",
        operator_id="op-admin",
        goal="frontier flywheel expert solution",
        worker_type="expert-frontier",
        created_by="operator",
        risk_level="YELLOW",
        requires_approval=True,
        allowed_files=["bug.txt"],
        allowed_tools=["edit_file"],
        verification_plan=MissionVerificationPlan(
            required_strength="strong",
            verifiers=(verifier_spec,),
        ),
        metadata={"problem_signature": "e2e-flywheel-fingerprint"},
    )
    frontier_rec = mission_service.create(frontier_contract)
    mission_service.start_deliberation(frontier_contract.mission_id)
    mission_service.request_approval(frontier_contract.mission_id)
    mission_service.approve(
        frontier_contract.mission_id,
        operator_id="op-admin",
        capability_digest="cap-flywheel",
        contract_digest=frontier_rec.contract_digest,
        authentication_event_id="auth-flywheel",
        session_id="session-flywheel",
    )
    mission_service.start_execution(frontier_contract.mission_id)
    mission_service.start_verification(frontier_contract.mission_id)
    completed_frontier_mission = mission_service.complete(frontier_contract.mission_id)

    v_result = verification_auth.verify(
        mission_id=completed_frontier_mission.mission_id,
        action_id="act-flywheel-1",
        worker_id="w-flywheel-1",
        target="bug.txt",
        plan=_verification_plan(),
        workspace_digest="ws-fw1",
        diff_digest="diff-fw1",
        environment_digest="env-fw1",
        observation=_observation(exit_code=0),
    )
    promotion = PromotionResult(
        mission_id=completed_frontier_mission.mission_id,
        action_id="act-flywheel-1",
        status=PromotionStatus.PROMOTED,
        evidence_ids=("ev-fw1",),
    )
    tool_obs = (
        ToolObservation(
            observation_id="obs-1",
            tool="edit_file",
            result_digest="out-1",
            status="completed",
        ),
    )

    traj_rec = learning_service.capture_trajectory(
        mission=completed_frontier_mission,
        project_digest="proj-fw-digest",
        expert_provider="gemini-pro",
        expert_model="gemini-2.5-pro",
        context_digest="ctx-fw-1",
        proposal_digest="prop-fw-1",
        tool_observations=tool_obs,
        verification_plan=_verification_plan(),
        verification_results=(v_result,),
        promotion=promotion,
        human_intervention_ids=(),
    )
    assert traj_rec.trajectory_id.startswith("trajectory-")

    skill_candidate = learning_service.create_skill_candidate(traj_rec.trajectory_id, candidate_spec)
    assert skill_candidate.state == "candidate"

    # -----------------------------------------------------------------------
    # Step 6: Human Review & Approval -> Active Local Skill
    # -----------------------------------------------------------------------
    active_skill = learning_service.activate_skill(
        skill_id=skill_candidate.skill_id,
        version=skill_candidate.version,
        operator_id="op-admin",
        approval_digest="digest-approved",
    )
    assert active_skill.state == "active"
    assert active_skill.confidence == 0.8

    # -----------------------------------------------------------------------
    # Step 7: Local Skill Reuse -> Execution Directive
    # -----------------------------------------------------------------------
    directive = learning_service.attempt_local_reuse(
        skill_id=active_skill.skill_id,
        version=active_skill.version,
        mission_id="mission-local-1",
        operator_id="op-admin",
        goal="run local e2e repair",
        project_id="proj-e2e",
        current_inputs={"bug.txt": "DEFECT", "file_type": "text"},
        current_state={"env": "prod"},
        current_scope="project/bug.txt",
        mission_allowed_tools=["edit_file"],
        validated_version="1.0.0",
    )
    assert isinstance(directive, LocalExecutionDirective)
    assert directive.skill.skill_id == "skill-e2e-flywheel"

    # -----------------------------------------------------------------------
    # Step 8: Post-execution verification success -> Confidence Boost
    # -----------------------------------------------------------------------
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

    local_v_result_1 = verification_auth.verify(
        mission_id="mission-local-1",
        action_id="act-loc-1",
        worker_id="w-loc-1",
        target="bug.txt",
        plan=_verification_plan(),
        workspace_digest="ws-loc-1",
        diff_digest="diff-loc-1",
        environment_digest="env-loc-1",
        observation=_observation(exit_code=0),
    )

    boosted = learning_service.record_reuse_outcome(
        skill_id=active_skill.skill_id,
        version=active_skill.version,
        mission_id="mission-local-1",
        verification_results=(local_v_result_1,),
        workspace_digest="ws-loc-1",
        diff_digest="diff-loc-1",
    )
    assert boosted.confidence > 0.8

    # -----------------------------------------------------------------------
    # Step 9: Verification Failures -> Skill Degradation -> Immediate Fail-Closed Escalation
    # -----------------------------------------------------------------------
    # Call attempt_local_reuse to create mission-local-2
    directive_loc_2 = learning_service.attempt_local_reuse(
        skill_id=active_skill.skill_id,
        version=active_skill.version,
        mission_id="mission-local-2",
        operator_id="op-admin",
        goal="run local e2e repair failure test",
        project_id="proj-e2e",
        current_inputs={"bug.txt": "DEFECT", "file_type": "text"},
        current_state={"env": "prod"},
        current_scope="project/bug.txt",
        mission_allowed_tools=["edit_file"],
        validated_version="1.0.0",
    )
    assert isinstance(directive_loc_2, LocalExecutionDirective)

    failed_v_result = verification_auth.verify(
        mission_id="mission-local-2",
        action_id="act-loc-2",
        worker_id="w-loc-2",
        target="bug.txt",
        plan=_verification_plan(),
        workspace_digest="ws-loc-2",
        diff_digest="diff-loc-2",
        environment_digest="env-loc-2",
        observation=_observation(exit_code=1),
    )

    learning_service.record_reuse_outcome(
        skill_id=active_skill.skill_id,
        version=active_skill.version,
        mission_id="mission-local-2",
        verification_results=(failed_v_result,),
        workspace_digest="ws-loc-2",
        diff_digest="diff-loc-2",
    )
    degraded = learning_service.record_reuse_outcome(
        skill_id=active_skill.skill_id,
        version=active_skill.version,
        mission_id="mission-local-2",
        verification_results=(failed_v_result,),
        workspace_digest="ws-loc-2",
        diff_digest="diff-loc-2",
    )
    assert degraded.state == "degraded"
    assert degraded.confidence < 0.8

    escaped_directive = learning_service.attempt_local_reuse(
        skill_id=active_skill.skill_id,
        version=active_skill.version,
        mission_id="mission-local-3",
        operator_id="op-admin",
        goal="run local e2e repair third time",
        project_id="proj-e2e",
        current_inputs={"bug.txt": "DEFECT", "file_type": "text"},
        current_state={"env": "prod"},
        current_scope="project/bug.txt",
        mission_allowed_tools=["edit_file"],
        validated_version="1.0.0",
    )
    assert isinstance(escaped_directive, EscalateToFrontierDirective)
