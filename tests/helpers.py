from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios.application.workspaces.staged import tree_digest
from aios.domain.executor import ExecutorRepairReceipt, ExecutorResult
from aios.domain.learning.contracts import ReuseOutcomeReference
from aios.domain.learning.trajectory_repository import (
    TrajectoryRecord,
    TrajectoryRepository,
)
from aios.domain.evidence import VerificationPlanV1


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def consume_real_capability_proof(
    db_path: Path,
    *,
    mission_id: str,
    contract_digest: str = "contract-digest-test",
    policy_version: str = "policy-v1",
    operator_id: str = "operator-1",
    action_type: str = "MAINTENANCE_REPAIR_RUN",
    route: str = "/api/v1/maintenance/repairs/run",
) -> Any:
    """Issue and consume a real capability through CapabilityAuthority.

    Returns the authority-produced ConsumedCapabilityProof; never hand-builds
    proof objects in tests that exercise the promotion path.
    """
    from aios.application.capabilities.authority import CapabilityAuthority
    from aios.domain.capabilities.contracts import CapabilityBinding

    authority = CapabilityAuthority(db_path=db_path)
    binding = CapabilityBinding(
        operator_id=operator_id,
        device_id="device-1",
        authentication_event_id="auth-event-1",
        session_id="session-1",
        action_type=action_type,
        route=route,
        http_method="POST",
        payload_digest=hashlib.sha256(mission_id.encode()).hexdigest(),
        resource_digest=hashlib.sha256(contract_digest.encode()).hexdigest(),
        mission_id=mission_id,
        contract_digest=contract_digest,
        policy_version=policy_version,
        scope=route,
        verification_requirement="promotion_authority_v1",
    )
    token = authority.issue(binding)
    return authority.consume(token, binding)


def executor_repair_result(
    job: Any,
    *,
    status: str = "completed",
    exit_code: int = 0,
    receipt_updates: dict[str, Any] | None = None,
    stdout: str | None = None,
) -> ExecutorResult:
    if stdout is not None:
        return ExecutorResult(
            job_id=job.job_id,
            status=status,
            exit_code=exit_code,
            stdout=stdout,
            isolation_verified=True,
            environment_digest="env-test-executor",
        )
    workspace = Path(job.workspace_snapshot)
    target_rel = job.argv[2]
    target = workspace / target_rel
    before_ws = tree_digest(workspace)
    before_bytes = target.read_bytes()
    before_digest = hashlib.sha256(before_bytes).hexdigest()
    content = before_bytes.decode("utf-8")
    repaired = content
    for marker in (
        "# DEFECT_MARKER: fix_required\n",
        "# DEFECT_MARKER: fix_required",
        "TODO_MAINTENANCE_DEFECT\n",
        "TODO_MAINTENANCE_DEFECT",
        "# AIOS_MAINTENANCE_REQUIRED: fix_required\n",
        "# AIOS_MAINTENANCE_REQUIRED: fix_required",
        "CONTROLLED_DEFECT\n",
        "CONTROLLED_DEFECT",
        "ORDERING_DEFECT\n",
        "ORDERING_DEFECT",
        "API_DEFECT\n",
        "API_DEFECT",
    ):
        repaired = repaired.replace(marker, "")
    if repaired != content:
        target.write_text(repaired, encoding="utf-8")
    after_bytes = target.read_bytes()
    after_digest = hashlib.sha256(after_bytes).hexdigest()
    after_ws = tree_digest(workspace)
    started = _utc_now()
    env = hashlib.sha256(
        json.dumps({"op_id": job.argv[1]}, sort_keys=True).encode()
    ).hexdigest()
    payload = {
        "job_id": job.job_id,
        "mission_contract_digest": job.mission_contract_digest,
        "operation_id": job.argv[1],
        "target": target_rel,
        "changed": True,
        "before_target_digest": before_digest,
        "after_target_digest": after_digest,
        "workspace_digest_before": before_ws,
        "workspace_digest_after": after_ws,
        "isolation_backend": "private_executor_service",
        "environment_digest": env,
        "started_timestamp": started,
        "ended_timestamp": _utc_now(),
        "executor_service_identity_version": "gagos-executor-service/1",
        "exit_code": exit_code,
        "receipt_version": "1.0",
    }
    if receipt_updates:
        payload.update(receipt_updates)
    receipt = ExecutorRepairReceipt.model_validate(payload)
    return ExecutorResult(
        job_id=job.job_id,
        status=status,
        exit_code=exit_code,
        stdout=receipt.model_dump_json(),
        isolation_verified=True,
        environment_digest=env,
    )


def reuse_outcome_reference(
    *,
    reuse_outcome_id: str,
    skill: Any,
    trajectory_id: str,
    mission: Any,
    verification: Any,
    worker_id: str,
    workspace_digest: str,
    diff_digest: str,
    executor_job_id: str = "exec-1",
    promotion_id: str = "promotion-1",
    local_job_id: str = "local-job-1",
    local_model_call_id: str = "local-call-1",
    project_digest: str = "project-digest-1",
    policy_version: str = "1.0",
) -> ReuseOutcomeReference:
    return ReuseOutcomeReference(
        reuse_outcome_id=reuse_outcome_id,
        skill_id=skill.skill_id,
        skill_version=skill.version,
        source_trajectory_id=trajectory_id,
        mission_id=mission.mission_id,
        worker_id=worker_id,
        executor_job_id=executor_job_id,
        promotion_id=promotion_id,
        local_job_id=local_job_id,
        local_model_call_id=local_model_call_id,
        verification_ids=(verification.verification_id,),
        workspace_digest=workspace_digest,
        diff_digest=diff_digest,
        project_digest=project_digest,
        contract_digest=mission.contract_digest,
        policy_version=policy_version,
    )


def save_minimal_trajectory(
    repository: TrajectoryRepository,
    trajectory_id: str,
    *,
    mission_id: str = "source-mission",
    contract_digest: str = "source-contract",
    problem_signature: str = "repair-json-parser",
) -> TrajectoryRecord:
    now = _utc_now()
    record = TrajectoryRecord(
        trajectory_id=trajectory_id,
        mission_id=mission_id,
        contract_digest=contract_digest,
        problem_signature=problem_signature,
        project_digest="project-digest-1",
        expert_provider="test-frontier",
        expert_model="test-model",
        context_digest="context-digest",
        proposal_digest="proposal-digest",
        actions_attempted=1,
        failed_attempts=0,
        successful_actions=1,
        tool_observations=(
            {
                "observation_id": "tool-1",
                "tool": "run_tests",
                "result_digest": "tool-digest",
                "status": "completed",
            },
        ),
        verification_plan=VerificationPlanV1(
            intended_behavior="test",
            targets=("unit-tests",),
            minimum_strength=1,
        ),
        verification_results=(
            {
                "verification_id": "verification-source",
                "mission_id": mission_id,
                "action_id": "action-source",
                "passed": True,
                "strength": 1,
                "required_strength": 1,
                "evidence_ids": ("evidence-source",),
            },
        ),
        verification_strength=1,
        promotion_status="promoted",
        promotion_evidence_ids=("evidence-source",),
        rollback_result=None,
        human_intervention_ids=(),
        final_mission_status="completed",
        final_outcome="success",
        created_at=now,
        updated_at=now,
    )
    repository.save(record)
    return record
