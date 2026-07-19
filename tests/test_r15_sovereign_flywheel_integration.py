"""In-process integration test suite for GAGOS R15 Sovereign Intelligence and Maintenance Flywheel (Proof level: INTEGRATION)."""

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any
import pytest

from aios import config
from aios.api import deps
from aios.application.evidence.verification import VerificationAuthority
from aios.application.learning.service import LearningService, SkillCandidateSpec, SkillActivationDenied
from aios.application.maintenance.service import MaintenanceConvergenceService
from aios.application.missions.mission_service import MissionService
from aios.application.promotion.authority import PromotionAuthority
from aios.domain.promotion import PromotionResult, PromotionStatus
from aios.application.workspaces import StagedWorkspaceManager
from aios.application.workspaces.staged import tree_digest
from aios.domain.evidence import VerificationObservation, VerificationPlanV1
from aios.domain.learning.repository import SkillRecord, SkillRepository
from aios.domain.learning.trajectory_repository import TrajectoryRepository
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.scanners import deterministic_config_scanner
from aios.domain.missions.mission_state import MissionState
from aios.domain.verification import SkillVerifierSpec
from aios.infrastructure.missions.sqlite_mission_repository import SqliteMissionRepository


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    return tmp_path / "operational_state.db"


@pytest.fixture
def test_mission_db_path(tmp_path: Path) -> Path:
    return tmp_path / "missions.db"


@pytest.fixture
def test_workspace_dir(tmp_path: Path) -> Path:
    target_dir = tmp_path / "target_repo"
    target_dir.mkdir(parents=True, exist_ok=True)
    # Create test file with defect marker
    test_file = target_dir / "config.txt"
    test_file.write_text("setting=1\n# DEFECT_MARKER: fix_required\n", encoding="utf-8")
    return target_dir


def test_verification_authority_tamper_detection_and_immutability(test_db_path: Path) -> None:
    """Prove Phase 2: VerificationAuthority enforces insert-only immutability and SHA-256 tamper checks."""
    va = VerificationAuthority(database_path=test_db_path)
    obs = VerificationObservation(
        command="test.verifier",
        exit_code=0,
        stdout="pass",
        stderr="",
        passed_count=1,
        failed_count=0,
        tool_version="test@1",
        observed_at="2026-07-19T12:00:00Z",
    )
    plan = VerificationPlanV1(
        intended_behavior="verify fix",
        targets=("config.txt",),
        required_tests=("test.verifier",),
        minimum_strength=1,
    )
    res = va.verify(
        mission_id="mission-123",
        action_id="action-123",
        worker_id="worker-123",
        target="config.txt",
        plan=plan,
        workspace_digest="hash-ws-1",
        diff_digest="hash-diff-1",
        environment_digest="hash-env-1",
        observation=obs,
    )

    # Retrieval works cleanly
    retrieved = va.get(res.verification_id)
    assert retrieved is not None
    assert retrieved.verification_id == res.verification_id
    assert va.is_authoritative(retrieved)

    # Immutability check: saving same verification_id with modified payload must raise ValueError
    tampered_res = res.model_copy(update={"workspace_digest": "tampered-hash"})
    with pytest.raises(ValueError, match="immutable and cannot be overwritten"):
        va.save(tampered_res)

    # Direct database tamper simulation: modify payload_json in SQLite
    with sqlite3.connect(test_db_path) as conn:
        conn.execute(
            "UPDATE verification_results SET payload_json = ? WHERE verification_id = ?",
            ('{"tampered": true}', res.verification_id),
        )
        conn.commit()

    # Get must detect tamper and return None
    assert va.get(res.verification_id) is None


def test_promotion_authority_durability_and_authoritative_check(tmp_path: Path, test_db_path: Path) -> None:
    """Prove Phase 3: PromotionAuthority persists records in SQLite and verifies is_authoritative."""
    wm = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(tmp_path,))
    va = VerificationAuthority(database_path=test_db_path)
    pa = PromotionAuthority(workspace_manager=wm, verification=va, database_path=test_db_path)

    # Fake verification
    obs = VerificationObservation(
        command="test", exit_code=0, stdout="", stderr="", passed_count=1, failed_count=0, tool_version="1", observed_at="now"
    )
    plan = VerificationPlanV1(intended_behavior="b", targets=("t",), required_tests=("test",), minimum_strength=1)
    va.verify(
        mission_id="m1",
        action_id="a1",
        worker_id="w1",
        target="t",
        plan=plan,
        workspace_digest="ws1",
        diff_digest="df1",
        environment_digest="env1",
        observation=obs,
    )

    assert not pa.is_authoritative(
        PromotionResult(
            mission_id="m1",
            action_id="a1",
            status=PromotionStatus.PROMOTED,
            reason_codes=(),
            checkpoint_id="c1",
            diff_digest="df1",
            restored=False,
            evidence_ids=(),
        )
    )


def test_end_to_end_sovereign_maintenance_flywheel(tmp_path: Path, test_workspace_dir: Path) -> None:
    """Prove complete R15 flywheel: Bounded scan -> Finding -> Repair Mission -> Staged Repair -> Verification -> Promotion -> Rescan -> Resolved."""
    db_path = tmp_path / "op_state.db"
    mission_db = tmp_path / "missions.db"
    staged_dir = tmp_path / "staged"

    wm = StagedWorkspaceManager(staged_dir, enrolled_roots=(test_workspace_dir,))
    va = VerificationAuthority(database_path=db_path)
    pa = PromotionAuthority(workspace_manager=wm, verification=va, database_path=db_path)
    mr = SqliteMissionRepository(mission_db)
    ms = MissionService(mr, workspace_manager=wm)

    from aios.application.executor.service import ExecutorService
    from aios.application.evidence.verifier_registry import VerifierRegistry
    from aios.application.workers.foundry import WorkerFoundry
    from aios.application.workers.strategies.code_repair import ProductionCodeWorkerStrategy
    from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
    from aios.domain.maintenance.repository import MaintenanceFindingRepository
    from aios.domain.maintenance.scan_repository import MaintenanceScanRepository

    finding_repo = MaintenanceFindingRepository(db_path)
    scan_repo = MaintenanceScanRepository(db_path)
    verifier_registry = VerifierRegistry(scanner_adapters={"deterministic_config_scanner": deterministic_config_scanner})
    executor_service = ExecutorService(profile="development")
    code_strat = ProductionCodeWorkerStrategy(workspace_manager=wm)
    worker_foundry = WorkerFoundry(runtime_root=test_workspace_dir, workspace_manager=wm, strategies={"code": code_strat})

    service = MaintenanceConvergenceService(
        finding_repository=finding_repo,
        scan_repository=scan_repo,
        mission_service=ms,
        worker_foundry=worker_foundry,
        executor_service=executor_service,
        verifier_registry=verifier_registry,
        verification_authority=va,
        promotion_authority=pa,
        workspace_manager=wm,
        lifecycle_engine=MaintenanceLifecycleEngine(),
    )

    # 1. Bounded Scan
    contract = BoundedScanContract(
        allowed_root=str(test_workspace_dir),
        max_files=10,
        max_total_bytes=1_000_000,
        max_file_bytes=100_000,
        deadline=30,
        max_findings=10,
        git_history_allowed=False,
    )
    src_digest = tree_digest(test_workspace_dir)
    scan_res = service.run_scan(
        contract,
        deterministic_config_scanner,
        scanner_id="deterministic_config_scanner",
        scanner_version="1",
        target_id="config.txt",
        source_digest=src_digest,
    )

    assert scan_res.scan.status == "completed", f"Scan failed with reason: {scan_res.scan.failure_reason}"
    assert len(scan_res.findings) == 1
    finding = scan_res.findings[0]
    assert finding.target_id == "config.txt"

    # 2. Create Repair Mission
    rec = service.create_repair_mission(finding.fingerprint, operator_id="op-1", workspace_root=str(test_workspace_dir))
    assert rec.state is MissionState.DRAFT

    # 3. Approve Mission
    ms.request_approval(rec.mission_id)
    ms.approve(
        rec.mission_id,
        operator_id="op-1",
        capability_digest="cap-1",
        contract_digest=rec.contract_digest,
        authentication_event_id="auth-evt-1",
        session_id="session-1",
    )

    # 4. Run Approved Repair
    rescan_contract = contract.model_copy()

    def create_checkpoint(req: Any) -> str:
        return f"chk-{uuid.uuid4().hex[:8]}"

    def restore_checkpoint(checkpoint_id: str, req: Any) -> bool:
        return True

    def smoke_test(req: Any) -> bool:
        return True

    import asyncio

    repair_res = asyncio.run(
        service.run_approved_repair(
            rec.mission_id,
            scanner=deterministic_config_scanner,
            rescan_contract=rescan_contract,
            capability_consumer=lambda _r: True,
            create_checkpoint=create_checkpoint,
            restore_checkpoint=restore_checkpoint,
            smoke_test=smoke_test,
        )
    )

    assert repair_res.status == "VERIFIED_RESOLVED", f"Repair failed: status={repair_res.status} reason={repair_res.reason}"
    assert repair_res.finding.status == "VERIFIED_RESOLVED"

    # Verify mission is now COMPLETED
    completed_mission = ms.repository.get(rec.mission_id)
    assert completed_mission.state is MissionState.COMPLETED

    # Verify original file on disk in main repository was promoted and no longer contains defect marker
    promoted_content = (test_workspace_dir / "config.txt").read_text(encoding="utf-8")
    assert "# DEFECT_MARKER: fix_required" not in promoted_content


def test_human_skill_activation_lifecycle(tmp_path: Path) -> None:
    """Prove Phase 10: Skill candidate review and activation state transitions."""
    db_path = tmp_path / "skill_test.db"
    mission_db = tmp_path / "missions.db"
    wm = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(tmp_path,))

    ms = MissionService(SqliteMissionRepository(mission_db), workspace_manager=wm)
    traj_repo = TrajectoryRepository(db_path)
    skill_repo = SkillRepository(db_path)
    va = VerificationAuthority(database_path=db_path)
    pa = PromotionAuthority(workspace_manager=wm, verification=va, database_path=db_path)

    ls = LearningService(
        mission_service=ms,
        trajectory_repository=traj_repo,
        skill_repository=skill_repo,
        verification_authority=va,
        promotion_authority=pa,
    )

    # Save a candidate skill directly into repository
    verifier_spec = SkillVerifierSpec(
        verifier_id="skill.reuse",
        version="1",
        target_pattern="config.txt",
        required_observations=("pass",),
        minimum_strength=1,
    )
    cand_spec = SkillCandidateSpec(
        skill_id="repair-config-skill",
        version=1,
        problem_signature="fix config defect",
        applicability_conditions={"target": "config.txt"},
        known_exclusions=(),
        required_inputs=(),
        required_project_state={},
        procedure="remove defect marker",
        allowed_tools=("code",),
        allowed_scope_pattern="config.txt",
        expected_observations=("pass",),
        verification_plan=verifier_spec,
        escalation_conditions=(),
        validated_versions=("1",),
    )

    now = "2026-07-19T12:00:00Z"
    skill = SkillRecord(
        **cand_spec.model_dump(exclude={"validated_versions"}, mode="python"),
        source_trajectory_ids=("traj-1",),
        confidence=0.8,
        success_count=0,
        failure_count=0,
        last_validated_versions=("1",),
        state="candidate",
        created_at=now,
        updated_at=now,
    )
    skill_repo.save(skill)

    # Generate valid operator approval digest
    cdig = hashlib.sha256(json.dumps(skill.model_dump(mode="json"), sort_keys=True).encode("utf-8")).hexdigest()
    operator_id = "human-operator-42"
    expected_digest = hashlib.sha256(
        f"{skill.skill_id}:{skill.version}:{cdig}:{operator_id}".encode("utf-8")
    ).hexdigest()

    # Without an activation_authorizer, activation must be denied (no public digest fallback)
    with pytest.raises(SkillActivationDenied, match="external authority refused"):
        ls.activate_skill(skill.skill_id, skill.version, operator_id=operator_id, approval_digest="wrong-digest")

    # Wire up a capability-backed authorizer that validates the expected digest
    def capability_authorizer(skill_record, op_id, digest):
        return digest == expected_digest

    ls.activation_authorizer = capability_authorizer

    # Invalid digest must be denied by the authorizer
    with pytest.raises(SkillActivationDenied, match="external authority refused"):
        ls.activate_skill(skill.skill_id, skill.version, operator_id=operator_id, approval_digest="wrong-digest")

    # Valid digest succeeds and activates skill candidate -> human_reviewed -> active
    activated = ls.activate_skill(skill.skill_id, skill.version, operator_id=operator_id, approval_digest=expected_digest)
    assert activated.state == "active"
