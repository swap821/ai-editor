"""Red-first tests exposing the remaining verified R15 blockers."""

import inspect
import pytest
from unittest.mock import MagicMock

from aios import executor_service
from aios.api.deps import get_learning_service
from aios.api.routes import maintenance as maintenance_route
from aios.application.executor.service import (
    ExecutorService,
    IsolationUnavailable,
    execute_registered_repair_operation,
)
from aios.application.learning.service import LearningService
from aios.domain.executor import ExecutorCapability, ExecutorJob, ResourceLimits
from aios.domain.learning.repository import SkillRecord
from aios.domain.learning.reuse_orchestrator import LocalExecutionDirective
from aios.domain.local_workforce.contracts import LocalJobProfile, LocalWorkerModel


def test_red_1_executor_service_cannot_run_registered_repair(tmp_path, monkeypatch):
    """Red Test 1: The standalone private Executor service cannot run REMOVE_MAINTENANCE_MARKER_V1."""
    monkeypatch.setenv("AIOS_EXECUTOR_TOKEN", "test-token")
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(tmp_path))
    
    stage_dir = tmp_path / "stage-1"
    stage_dir.mkdir()
    target_file = stage_dir / "src" / "fix.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("# DEFECT_MARKER: fix_required\nprint('hello')\n")
    
    job = ExecutorJob(
        job_id="job-repair-red-1",
        mission_contract_digest="contract-digest-1",
        capability=ExecutorCapability(
            capability_id="executor-capability:job-repair-red-1",
            action_digest="act-1",
            mission_contract_digest="contract-digest-1",
            expires_at="2026-12-31T23:59:59Z",
        ),
        image="test-image",
        argv=("repair", "REMOVE_MAINTENANCE_MARKER_V1", "src/fix.py"),
        workspace_snapshot=str(stage_dir),
        resource_limits=ResourceLimits(
            timeout_seconds=30,
            max_output_bytes=1000,
            memory_budget_mb=512,
            cpu_budget=1.0,
            pids_limit=100,
        ),
        verification_expectation={"executor_policy": "private_service"},
    )
    result = executor_service.execute_job(job, authorization="Bearer test-token")
    assert result.status == "completed"
    assert result.isolation_verified is True


def test_red_2_in_process_fallback_falsely_claims_isolation(tmp_path):
    """Red Test 2: Production profile refuses non-private_service backend fallback."""
    executor_service = ExecutorService(
        profile="production",
        backend_name="in_process_fixture",
        client=None,
    )
    job = ExecutorJob(
        job_id="job-repair-red-2",
        mission_contract_digest="contract-digest-2",
        capability=ExecutorCapability(
            capability_id="executor-capability:job-repair-red-2",
            action_digest="act-2",
            mission_contract_digest="contract-digest-2",
            expires_at="2026-12-31T23:59:59Z",
        ),
        image="test-image",
        argv=("repair", "REMOVE_MAINTENANCE_MARKER_V1", "src/fix.py"),
        workspace_snapshot=str(tmp_path),
        resource_limits=ResourceLimits(
            timeout_seconds=30,
            max_output_bytes=1000,
            memory_budget_mb=512,
            cpu_budget=1.0,
            pids_limit=100,
        ),
    )
    with pytest.raises(IsolationUnavailable) as exc_info:
        executor_service.execute(job)
    assert "private executor service is required in production" in str(exc_info.value)


def test_red_3_mounted_maintenance_route_uses_fake_adapters():
    """Red Test 3: Maintenance run_approved_repair route contains fake inline closures."""
    source = inspect.getsource(maintenance_route.run_approved_repair)
    # Route must NOT define inline dummy closures like 'def create_checkpoint' or 'return True'
    assert "def create_checkpoint" not in source
    assert "def restore_checkpoint" not in source
    assert "def smoke_test" not in source


def test_red_4_canonical_learning_service_lacks_dependencies():
    """Red Test 4: get_learning_service() in deps.py lacks activation_authorizer and LocalWorkforceService."""
    service = get_learning_service()
    assert getattr(service, "activation_authorizer", None) is not None, (
        "activation_authorizer must be injected into canonical LearningService"
    )
    assert getattr(service, "local_workforce_service", None) is not None, (
        "local_workforce_service must be injected into canonical LearningService"
    )


def test_red_5_granite_selection_checks_wrong_health_field():
    """Red Test 5: Granite selection in LearningService checks health_status instead of health."""
    mock_local_workforce = MagicMock()
    model = LocalWorkerModel(
        model_id="granite3.2:2b",
        provider="ollama",
        family="granite",
        parameter_size="2B",
        quantization="q4_K_M",
        installed=True,
        operator_approved=True,
        health="healthy",
        admission_status="approved",
        admission_reason="Passed qualification",
        max_context=131072,
        max_output=4096,
        max_parallelism=1,
        allowed_job_profiles=frozenset({LocalJobProfile.SELECT_SKILL}),
        metadata_confidence="verified",
        qualification_version="r15-v2",
    )
    mock_local_workforce.registry.list_models.return_value = [model]
    
    mock_mission_service = MagicMock()
    mock_traj_repo = MagicMock()
    mock_skill_repo = MagicMock()
    
    from aios.domain.verification import SkillVerifierSpec
    spec = SkillVerifierSpec(
        verifier_id="skill.reuse",
        version="1",
        target_pattern="*",
        required_observations=("obs1",),
        minimum_strength=1,
    )
    skill = SkillRecord(
        skill_id="test-skill",
        version=1,
        state="active",
        confidence=0.9,
        problem_signature="sig",
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
        source_trajectory_ids=("traj-1",),
        success_count=1,
        failure_count=0,
        last_validated_versions=("1.0",),
        created_at="2026-07-20T00:00:00Z",
        updated_at="2026-07-20T00:00:00Z",
    )
    mock_skill_repo.get.return_value = skill
    
    from aios.domain.learning.reuse_orchestrator import EscalateToFrontierDirective
    from aios.domain.local_workforce.contracts import LocalJobResult
    mock_local_workforce.run_advisory_job.return_value = LocalJobResult(
        job_id="job-1",
        model_id="granite3.2:2b",
        structured_output={"applicable": True, "confidence": 0.9, "reason": "ok"},
        schema_valid=True,
        evidence_references_preserved=True,
        unsupported_claims=(),
        latency=0.1,
        status="completed",
    )
    
    service = LearningService(
        mission_service=mock_mission_service,
        trajectory_repository=mock_traj_repo,
        skill_repository=mock_skill_repo,
        local_workforce_service=mock_local_workforce,
        reuse_policy=lambda s, c: True,
        verification_plan_validator=lambda s: True,
    )
    
    directive = service.attempt_local_reuse(
        skill_id="test-skill",
        version=1,
        mission_id="m-1",
        operator_id="op-1",
        goal="goal",
        project_id="proj-1",
        current_inputs={},
        current_state={},
        current_scope="*",
        mission_allowed_tools=(),
        validated_version="1.0",
    )
    
    assert not isinstance(directive, EscalateToFrontierDirective)
