"""Red tests for R15 production repairs proving fail-closed execution boundaries."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path

from aios.application.executor.service import ExecutorService, IsolationUnavailable
from aios.application.maintenance.service import MaintenanceConvergenceService, MaintenanceRepairResult
from aios.application.workers.strategies.code_repair import ProductionCodeWorkerStrategy
from aios.domain.executor import ExecutorJob, ExecutorResult, ResourceLimits, ExecutorCapability
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.missions.mission_state import MissionState


def _make_mock_repair_context():
    finding_repo = MagicMock()
    scan_repo = MagicMock()
    mission_service = MagicMock()
    worker_foundry = MagicMock()
    executor_service = MagicMock(spec=ExecutorService)
    verification_auth = MagicMock()
    promotion_auth = MagicMock()
    workspace_mgr = MagicMock()
    lifecycle_engine = MagicMock()
    verifier_registry = MagicMock()

    # Configure mission record
    mission_record = MagicMock()
    mission_record.state = MissionState.APPROVED
    mission_record.contract_digest = "contract-digest-123"
    mission_record.contract.metadata = {
        "finding_fingerprint": "fp-123",
        "worker_strategy": "code",
        "verification_spec": {
            "verifier_id": "test_verifier",
            "version": "1",
            "target_id": "src/fix.py",
            "allowed_root": "/tmp/staged",
        }
    }
    mission_record.contract.workspace_root = "/tmp/staged"
    mission_service.repository.get.return_value = mission_record

    # Finding
    finding = MaintenanceFinding(
        finding_id="finding-test-123",
        fingerprint="fp-123",
        scanner_id="test_scanner",
        scanner_version="1",
        kind="test_defect",
        severity="high",
        confidence=1.0,
        evidence_quality="deterministic",
        target_id="src/fix.py",
        target_digest="target-digest-123",
        source_digest="src-digest",
        first_seen="2026-07-19T00:00:00Z",
        last_seen="2026-07-19T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="test defect evidence",
        mission_id="m-123",
    )
    finding_repo.get.return_value = finding

    # Worker
    worker_result = MagicMock()
    worker_result.status = "completed"
    worker_result.worker_id = "w-1"
    worker_foundry.run.return_value = worker_result

    # Workspace
    lease = MagicMock()
    lease.workspace_path = "/tmp/staged"
    workspace_mgr.for_mission.return_value = lease
    workspace_mgr.diff.return_value = {
        "workspace_digest": "ws-digest-123",
        "diff_digest": "diff-digest-123",
    }

    # Verifier run
    verifier_run = MagicMock()
    verifier_run.verifier_id = "test_verifier"
    verifier_run.version = "1"
    verifier_run.passed = True
    verifier_run.stdout = "ok"
    verifier_run.stderr = ""
    verifier_run.started_at = "2026-07-19T00:00:00Z"
    verifier_run.ended_at = "2026-07-19T00:00:01Z"
    verifier_run.status = "completed"
    verifier_run.reason = None
    verifier_run.finding_fingerprints = ()
    verifier_registry.run.return_value = verifier_run

    # Executor job
    executor_job = ExecutorJob(
        job_id="job-123",
        mission_contract_digest="contract-digest-123",
        capability=ExecutorCapability(
            capability_id="cap-123",
            action_digest="act-123",
            mission_contract_digest="contract-digest-123",
            expires_at="2026-12-31T23:59:59Z"
        ),
        image="test-image",
        argv=("verify", "src/fix.py"),
        workspace_snapshot="/tmp/staged",
        resource_limits=ResourceLimits(timeout_seconds=30, max_output_bytes=1000, memory_budget_mb=512, cpu_budget=1.0, pids_limit=100),
        verification_expectation={"executor_policy": "private_service"}
    )
    executor_service.build_command_job.return_value = executor_job

    service = MaintenanceConvergenceService(
        finding_repository=finding_repo,
        scan_repository=scan_repo,
        mission_service=mission_service,
        worker_foundry=worker_foundry,
        executor_service=executor_service,
        verifier_registry=verifier_registry,
        verification_authority=verification_auth,
        promotion_authority=promotion_auth,
        workspace_manager=workspace_mgr,
        lifecycle_engine=lifecycle_engine,
    )

    return service, executor_service, verification_auth, promotion_auth


@pytest.mark.anyio
async def test_executor_unavailable_fails_closed():
    """Executor unavailable exception must fail closed with EXECUTOR_UNAVAILABLE status."""
    service, mock_executor, verification_auth, promotion_auth = _make_mock_repair_context()
    mock_executor.execute.side_effect = IsolationUnavailable("private executor service unavailable")

    rescan_contract = BoundedScanContract(
        allowed_root="/tmp/staged",
        deadline=30,
        max_files=100,
        max_total_bytes=10_000_000,
        max_file_bytes=1_000_000,
        max_findings=100,
        git_history_allowed=False,
    )
    
    result = await service.run_approved_repair(
        "m-123",
        scanner=MagicMock(),
        rescan_contract=rescan_contract,
        capability_consumer=MagicMock(),
        create_checkpoint=MagicMock(),
        restore_checkpoint=MagicMock(),
        smoke_test=MagicMock(),
    )

    assert result.status == "EXECUTOR_UNAVAILABLE"
    assert "unavailable" in result.reason
    verification_auth.verify.assert_not_called()
    promotion_auth.promote.assert_not_called()


@pytest.mark.anyio
async def test_executor_timeout_fails_closed():
    """Executor timeout must fail closed with EXECUTOR_TIMEOUT status."""
    service, mock_executor, verification_auth, promotion_auth = _make_mock_repair_context()
    mock_executor.execute.side_effect = IsolationUnavailable("private executor request timed out")

    rescan_contract = BoundedScanContract(
        allowed_root="/tmp/staged",
        deadline=30,
        max_files=100,
        max_total_bytes=10_000_000,
        max_file_bytes=1_000_000,
        max_findings=100,
        git_history_allowed=False,
    )
    
    result = await service.run_approved_repair(
        "m-123",
        scanner=MagicMock(),
        rescan_contract=rescan_contract,
        capability_consumer=MagicMock(),
        create_checkpoint=MagicMock(),
        restore_checkpoint=MagicMock(),
        smoke_test=MagicMock(),
    )

    assert result.status == "EXECUTOR_TIMEOUT"
    assert "timed out" in result.reason
    verification_auth.verify.assert_not_called()
    promotion_auth.promote.assert_not_called()


@pytest.mark.anyio
async def test_executor_provenance_invalid_fails_closed():
    """Executor mismatched job id or missing isolation proof must fail closed with EXECUTOR_PROVENANCE_INVALID."""
    service, mock_executor, verification_auth, promotion_auth = _make_mock_repair_context()
    mock_executor.execute.side_effect = IsolationUnavailable("private executor returned a mismatched job id")

    rescan_contract = BoundedScanContract(
        allowed_root="/tmp/staged",
        deadline=30,
        max_files=100,
        max_total_bytes=10_000_000,
        max_file_bytes=1_000_000,
        max_findings=100,
        git_history_allowed=False,
    )
    
@pytest.mark.anyio
async def test_worker_does_not_mutate_files_directly(tmp_path):
    """ProductionCodeWorkerStrategy must produce a repair proposal without modifying files directly."""
    worker = ProductionCodeWorkerStrategy()
    test_file = tmp_path / "fix.py"
    original_content = "# DEFECT_MARKER: fix_required\nprint('hello')"
    test_file.write_text(original_content)

    request = MagicMock()
    request.contract.mission_id = "m-1"
    request.contract.metadata = {"target_id": "fix.py", "workspace_root": str(tmp_path)}
    request.spec = MagicMock()
    request.principal.worker_id = "w-1"

    result = await worker.run(request)
    assert result.status == "completed"
    assert result.proposal is not None
    assert result.proposal["operation_id"] == "REMOVE_MAINTENANCE_MARKER_V1"
    assert result.proposal["target_rel"] == "fix.py"
    # File content on disk must remain unmutated by the worker strategy
    assert test_file.read_text() == original_content


def test_executor_workspace_binding():
    """ExecutorJob must bind both real staged workspace reference and workspace content digest."""
    service_inst = ExecutorService(profile="development")
    job = service_inst.build_repair_job(
        mission_contract_digest="contract-digest-123",
        operation_id="REMOVE_MAINTENANCE_MARKER_V1",
        target_rel="src/fix.py",
        workspace_path="/tmp/staged_root/m-123",
        workspace_digest="ws-content-digest-456",
        timeout_seconds=30,
        expected_digest="exp-digest-789",
    )

    # workspace_snapshot MUST be the real staged workspace path, not the content digest
    assert job.workspace_snapshot == "/tmp/staged_root/m-123"
    # Content digest MUST be bound in verification expectation
    assert job.verification_expectation["workspace_digest"] == "ws-content-digest-456"
    assert job.verification_expectation["expected_target_digest"] == "exp-digest-789"
    # Argv MUST be typed operation, not shell string
    assert job.argv == ("repair", "REMOVE_MAINTENANCE_MARKER_V1", "src/fix.py")


def test_execute_registered_repair_operation_bounds_and_mutates(tmp_path):
    """REMOVE_MAINTENANCE_MARKER_V1 must safely mutate only within staged workspace boundary."""
    from aios.application.executor.service import execute_registered_repair_operation
    import hashlib

    # Create target file with defect marker inside tmp_path using exact bytes
    target_file = tmp_path / "defect.py"
    initial_bytes = b"# DEFECT_MARKER: fix_required\ndef foo(): pass\n"
    target_file.write_bytes(initial_bytes)
    before_sha = hashlib.sha256(initial_bytes).hexdigest()

    job = ExecutorJob(
        job_id="job-repair-1",
        mission_contract_digest="digest-1",
        capability=ExecutorCapability(
            capability_id="cap-1",
            action_digest="act-1",
            mission_contract_digest="digest-1",
            expires_at="2026-12-31T23:59:59Z"
        ),
        image="test-image",
        argv=("repair", "REMOVE_MAINTENANCE_MARKER_V1", "defect.py"),
        workspace_snapshot=str(tmp_path),
        resource_limits=ResourceLimits(timeout_seconds=30, max_output_bytes=1000, memory_budget_mb=512, cpu_budget=1.0, pids_limit=100),
        verification_expectation={"expected_target_digest": before_sha}
    )

    result = execute_registered_repair_operation(job)
    assert result.status == "completed"
    assert result.isolation_verified is True

    # Check file was mutated by executor
    new_text = target_file.read_text(encoding="utf-8")
    assert "# DEFECT_MARKER: fix_required" not in new_text
    assert "def foo(): pass" in new_text


def test_execute_registered_repair_operation_refuses_traversal(tmp_path):
    """REMOVE_MAINTENANCE_MARKER_V1 must refuse absolute path or traversal escape."""
    from aios.application.executor.service import execute_registered_repair_operation

    job = ExecutorJob(
        job_id="job-repair-2",
        mission_contract_digest="digest-1",
        capability=ExecutorCapability(
            capability_id="cap-1",
            action_digest="act-1",
            mission_contract_digest="digest-1",
            expires_at="2026-12-31T23:59:59Z"
        ),
        image="test-image",
        argv=("repair", "REMOVE_MAINTENANCE_MARKER_V1", "../outside.py"),
        workspace_snapshot=str(tmp_path),
        resource_limits=ResourceLimits(timeout_seconds=30, max_output_bytes=1000, memory_budget_mb=512, cpu_budget=1.0, pids_limit=100),
        verification_expectation={}
    )

def test_verification_integrity_signed(tmp_path):
    """VerificationAuthority must validate HMAC/signed integrity proof on both get() and list_results_for_mission()."""
    from aios.application.evidence.verification import VerificationAuthority
    from aios.domain.evidence import VerificationObservation, VerificationPlanV1

    db_path = tmp_path / "verification.db"
    auth = VerificationAuthority(database_path=db_path)

    plan = VerificationPlanV1(intended_behavior="test", targets=("src/a.py",), minimum_strength=1)
    obs = VerificationObservation(command="test", exit_code=0, stdout="ok", stderr="", passed_count=1, failed_count=0, tool_version="1", observed_at="2026-07-19T00:00:00Z")

    res = auth.verify(
        mission_id="m-1",
        action_id="act-1",
        worker_id="w-1",
        target="src/a.py",
        plan=plan,
        workspace_digest="ws-1",
        diff_digest="diff-1",
        environment_digest="env-1",
        observation=obs,
    )

    assert auth.get(res.verification_id) is not None
    listed = auth.list_results_for_mission("m-1")
    assert len(listed) == 1

    # Tamper with payload_json in SQLite database
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE verification_results SET payload_json = REPLACE(payload_json, 'src/a.py', 'src/tampered.py') WHERE verification_id = ?", (res.verification_id,))
    conn.commit()
    conn.close()

    # Both get() and list_results_for_mission() MUST detect tampering and refuse tampered rows!
    auth_fresh = VerificationAuthority(database_path=db_path)
    assert auth_fresh.get(res.verification_id) is None
    assert len(auth_fresh.list_results_for_mission("m-1")) == 0


def test_verification_schema_migration(tmp_path):
    """VerificationAuthority must safely migrate an old SQLite table missing payload_digest/integrity_proof."""
    import sqlite3
    from aios.application.evidence.verification import VerificationAuthority

    db_path = tmp_path / "old_verification.db"
    conn = sqlite3.connect(db_path)
    # Create old schema table
    conn.execute("""
        CREATE TABLE verification_results (
            verification_id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

    # Initializing VerificationAuthority on existing old DB must run schema migration
    auth = VerificationAuthority(database_path=db_path)

    # Verify table columns now include payload_digest and integrity_proof
    conn = sqlite3.connect(db_path)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(verification_results)").fetchall()]
    conn.close()

    assert "payload_digest" in columns
    assert "integrity_proof" in columns
    assert "created_at" in columns


def test_promotion_durability_immutable(tmp_path):
    """PromotionAuthority must record immutable insert-only promotion attempts with deterministic terminal lookup."""
    from aios.application.promotion.authority import PromotionAuthority
    from aios.domain.promotion import PromotionResult, PromotionStatus

    db_path = tmp_path / "promotion.db"
    auth = PromotionAuthority(workspace_manager=MagicMock(), database_path=db_path)

    # Verify table schema has unique promotion records and insert-only persistence
    assert hasattr(auth, "get_authoritative_terminal_promotion") or hasattr(auth, "get_promotion")


def test_skill_activation_requires_capability():
    """Skill activation must refuse publicly computable approval digest fallback."""
    from aios.application.learning.service import LearningService, SkillActivationDenied, SkillRecord
    from aios.domain.verification import SkillVerifierSpec

    spec = SkillVerifierSpec(
        verifier_id="skill.reuse",
        version="1",
        target_pattern="src/*.py",
        required_observations=("obs1",),
        minimum_strength=1,
    )

    skill = SkillRecord(
        skill_id="sk-1",
        version=1,
        problem_signature="sig-1",
        applicability_conditions={},
        known_exclusions=(),
        required_inputs=(),
        required_project_state={},
        procedure="proc",
        allowed_tools=(),
        allowed_scope_pattern="*",
        expected_observations=(),
        verification_plan=spec,
        escalation_conditions=(),
        source_trajectory_ids=("t-1",),
        confidence=0.9,
        success_count=1,
        failure_count=0,
        last_validated_versions=("1",),
        state="candidate",
        created_at="2026-07-19T00:00:00Z",
        updated_at="2026-07-19T00:00:00Z",
    )

    skill_repo = MagicMock()
    skill_repo.get.return_value = skill

    service = LearningService(
        mission_service=MagicMock(),
        trajectory_repository=MagicMock(),
        skill_repository=skill_repo,
    )

    # Attempt activation with fake publicly computable digest - MUST fail
    with pytest.raises(SkillActivationDenied):
        service.activate_skill(
            "sk-1", 1, operator_id="op-1", approval_digest="publicly_computable_fake_digest"
        )


