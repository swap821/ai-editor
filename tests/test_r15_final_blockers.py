"""Executable RED test suite for GAGOS R15 final production convergence.

This test file contains executable RED tests for each requirement phase.
These tests demonstrate the current flaws or test the required production behaviors.
"""

import hashlib
import json
import time
import asyncio

import pytest
from pydantic import ValidationError

from aios.application.capabilities.authority import CapabilityAuthority
from aios.application.evidence.verification import VerificationAuthority
from aios.application.learning.service import (
    LearningService,
    SkillActivationAuthorization,
    SkillActivationDenied,
)
from aios.application.missions.mission_service import MissionService
from aios.domain.capabilities.contracts import (
    CapabilityBinding,
    ConsumedCapabilityProof,
)
from aios.domain.evidence import VerificationObservation, VerificationPlanV1
from aios.domain.executor.receipt import ExecutorRepairReceipt
from aios.domain.learning.contracts import (
    ReuseOutcomeReference,
    SkillApplicabilityAdvisoryV1,
)
from aios.domain.learning.repository import SkillRecord, SkillRepository
from aios.domain.learning.trajectory_repository import (
    TrajectoryRepository,
)
from aios.domain.missions.mission_contract import (
    MissionContract,
)
from aios.domain.missions.mission_state import MissionState
from aios.domain.verification import SkillVerifierSpec
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.domain.learning.reuse_outcome_repository import ReuseOutcomeRepository
from tests.helpers import (
    executor_repair_result,
    reuse_outcome_reference,
    save_minimal_trajectory,
)
from tests.test_maintenance_convergence import (
    _WorkerFoundry as _MaintenanceWorker,
    _contract as _maintenance_contract,
    _scanner as _maintenance_scanner,
    _service as _maintenance_service,
)


def _make_proof(
    skill_id: str = "skill-test",
    version: int = 1,
    operator_id: str = "op-1",
    device_id: str = "dev-1",
    action_type: str = "skill_activation",
    route: str | None = None,
    http_method: str = "POST",
    expired: bool = False,
    revoked: bool = False,
) -> ConsumedCapabilityProof:
    now = time.time()
    route_str = route or f"/api/v1/skills/{skill_id}/versions/{version}/activate"
    return ConsumedCapabilityProof(
        capability_id="cap-proof-1",
        token_digest=hashlib.sha256(b"token-1").hexdigest(),
        operator_id=operator_id,
        device_id=device_id,
        authentication_event_id="auth-event-1",
        session_id="sess-1",
        action_type=action_type,
        route=route_str,
        http_method=http_method,
        payload_digest=hashlib.sha256(b"{}").hexdigest(),
        resource_digest=hashlib.sha256(skill_id.encode()).hexdigest(),
        mission_id=None,
        contract_digest=None,
        policy_version="1.0",
        scope=f"route:{route_str}",
        verification_requirement="route_policy_v1",
        consumed_at=now - 10.0,
        expires_at=now - 5.0 if expired else now + 120.0,
        revoked_at=now - 1.0 if revoked else None,
    )


# ---------------------------------------------------------------------------
# Phase 1 RED Test: activate_skill with SkillActivationAuthorization
# ---------------------------------------------------------------------------


def test_red_1_activate_skill_loads_skill_id_none(tmp_path):
    """Proves that passing SkillActivationAuthorization without skill_id kwarg previously failed because skill_id=None."""
    db_path = tmp_path / "test_state.db"
    traj_repo = TrajectoryRepository(db_path)
    skill_repo = SkillRepository(db_path)

    # Save candidate skill with exact ID
    now = "2026-07-20T10:00:00Z"
    verifier = SkillVerifierSpec(
        verifier_id="skill.reuse",
        version="1",
        target_pattern="*.py",
        required_observations=("passed",),
        minimum_strength=1,
    )
    skill = SkillRecord(
        skill_id="skill-test",
        version=1,
        problem_signature="test_problem",
        applicability_conditions={"file": "test.py"},
        known_exclusions=(),
        required_inputs=("code",),
        required_project_state={"env": "test"},
        procedure="do_test",
        allowed_tools=("read",),
        allowed_scope_pattern="src/*",
        expected_observations=("done",),
        verification_plan=verifier,
        escalation_conditions=(),
        source_trajectory_ids=("traj-1",),
        confidence=0.8,
        success_count=0,
        failure_count=0,
        last_validated_versions=("1.0",),
        state="candidate",
        created_at=now,
        updated_at=now,
    )
    if skill_repo.get(skill.skill_id, skill.version) is None:
        if skill_repo.get(skill.skill_id, skill.version) is None:
            if skill_repo.get(skill.skill_id, skill.version) is None:
                skill_repo.save(skill)

    mission_repo = SqliteMissionRepository(db_path)
    from aios.application.missions.mission_service import MissionService

    mission_service = MissionService(mission_repo)
    learning_service = LearningService(
        mission_service=mission_service,
        trajectory_repository=traj_repo,
        skill_repository=skill_repo,
    )

    proof = _make_proof(skill_id="skill-test", version=1)
    auth = SkillActivationAuthorization(proof=proof, skill_id="skill-test", version=1)

    # Calling activate_skill(auth) must activate "skill-test" using authorization.skill_id and authorization.version
    activated = learning_service.activate_skill(auth)
    assert activated.skill_id == "skill-test"
    assert activated.version == 1
    assert activated.state == "active"


def test_red_1_legacy_loose_activation_is_removed(tmp_path):
    """Proves legacy loose parameter signatures on activate_skill are forbidden."""
    db_path = tmp_path / "test_state.db"
    traj_repo = TrajectoryRepository(db_path)
    skill_repo = SkillRepository(db_path)
    mission_repo = SqliteMissionRepository(db_path)
    from aios.application.missions.mission_service import MissionService

    mission_service = MissionService(mission_repo)
    learning_service = LearningService(
        mission_service=mission_service,
        trajectory_repository=traj_repo,
        skill_repository=skill_repo,
    )

    # Loose activation calling style must raise TypeError or SkillActivationDenied
    with pytest.raises((TypeError, SkillActivationDenied)):
        learning_service.activate_skill(
            authorization="skill-test",
            version=1,
            operator_id="op-1",
            approval_digest="digest",
        )


# ---------------------------------------------------------------------------
# Phase 2 RED Test: CapabilityAuthority returns immutable ConsumedCapabilityProof
# ---------------------------------------------------------------------------


def test_red_2_capability_authority_returns_consumed_capability_proof(tmp_path):
    """Proves CapabilityAuthority.consume() returns an authority-produced ConsumedCapabilityProof."""
    db_file = tmp_path / "caps.db"
    auth = CapabilityAuthority(db_path=db_file, ttl_seconds=120.0)

    binding = CapabilityBinding(
        operator_id="op-1",
        device_id="dev-1",
        authentication_event_id="auth-1",
        session_id="sess-1",
        action_type="SKILL_ACTIVATION",
        route="/api/v1/skills/s1/versions/1/activate",
        http_method="POST",
        payload_digest=hashlib.sha256(b"{}").hexdigest(),
        resource_digest=hashlib.sha256(b"s1").hexdigest(),
        mission_id=None,
        contract_digest=None,
        policy_version="1.0",
        scope="route:/api/v1/skills/s1/versions/1/activate",
        verification_requirement="route_policy_v1",
    )
    token = auth.issue(binding)
    assert token

    proof = auth.consume(token, binding)
    assert isinstance(proof, ConsumedCapabilityProof)
    assert proof.operator_id == "op-1"
    assert proof.device_id == "dev-1"
    assert proof.session_id == "sess-1"
    assert proof.action_type == "SKILL_ACTIVATION"
    assert proof.route == "/api/v1/skills/s1/versions/1/activate"
    assert proof.http_method == "POST"
    assert proof.consumed_at > 0
    assert proof.expires_at > proof.consumed_at


# ---------------------------------------------------------------------------
# Phase 3 RED Test: PromotionAuthorization & No Token Guessing
# ---------------------------------------------------------------------------


def test_red_3_promotion_authorization_exact_binding():
    """Proves PromotionAuthorization binds exact consumed capability proof and mission identifiers."""
    from aios.domain.promotion.contracts import PromotionAuthorization

    proof = _make_proof(
        action_type="MAINTENANCE_REPAIR_RUN", route="/api/v1/maintenance/repairs/run"
    )
    promo_auth = PromotionAuthorization(
        proof=proof,
        promotion_attempt_id="promo-att-1",
        mission_id="m-1",
        action_id="a-1",
        worker_id="w-1",
        executor_job_id="j-1",
        contract_digest="0" * 64,
        workspace_digest="1" * 64,
        diff_digest="2" * 64,
        project_root_identity="root-1",
        required_targets=("target.txt",),
    )
    assert promo_auth.proof.capability_id == "cap-proof-1"
    assert promo_auth.mission_id == "m-1"
    assert promo_auth.required_targets == ("target.txt",)


# ---------------------------------------------------------------------------
# Phase 4 RED Test: CheckpointAuthority External Storage
# ---------------------------------------------------------------------------


def test_red_4_checkpoint_authority_external_storage(tmp_path):
    """Proves CheckpointAuthority rejects rollback directories equal to or inside project root."""
    from aios.application.promotion.checkpoint import (
        CheckpointAuthority,
        CheckpointError,
    )

    project_root = tmp_path / "project"
    project_root.mkdir()
    inside_rollback = project_root / "rollback"
    inside_rollback.mkdir()

    with pytest.raises(CheckpointError, match="inside project root"):
        CheckpointAuthority(project_root=project_root, storage_root=inside_rollback)


# ---------------------------------------------------------------------------
# Phase 5 RED Test: Two-Phase Rollback Restoration
# ---------------------------------------------------------------------------


def test_red_5_two_phase_rollback_restoration(tmp_path):
    """Proves CheckpointAuthority creates signed manifest and restores exact pre-promotion bytes."""
    from aios.application.promotion.checkpoint import CheckpointAuthority

    project_root = tmp_path / "project"
    project_root.mkdir()
    rollback_root = tmp_path / "rollback"
    rollback_root.mkdir()

    target_file = project_root / "file.txt"
    target_file.write_text("original content")

    ckpt_auth = CheckpointAuthority(
        project_root=project_root,
        storage_root=rollback_root,
        authority_key="test-checkpoint-key-32-bytes-long!",
    )

    manifest = ckpt_auth.create_checkpoint(
        mission_id="m-1",
        action_id="a-1",
        worker_id="w-1",
        executor_job_id="j-1",
        contract_digest="0" * 64,
        workspace_digest="1" * 64,
        diff_digest="2" * 64,
        affected_paths=["file.txt"],
    )
    assert manifest.checkpoint_id

    # Mutate project file
    target_file.write_text("mutated content")

    # Restore
    receipt = ckpt_auth.restore_checkpoint(manifest.checkpoint_id)
    assert receipt.status == "RESTORED"
    assert target_file.read_text() == "original content"

    # Second restore must fail
    with pytest.raises(Exception):
        ckpt_auth.restore_checkpoint(manifest.checkpoint_id)


# ---------------------------------------------------------------------------
# Phase 6 RED Test: Post-Promotion Verification Receipt
# ---------------------------------------------------------------------------


def test_red_6_post_promotion_verification_receipt():
    """Proves post promotion verification requires typed PostPromotionVerificationReceipt."""
    from aios.domain.evidence import PostPromotionVerificationReceipt

    receipt = PostPromotionVerificationReceipt(
        mission_id="m-1",
        action_id="a-1",
        worker_id="w-1",
        executor_job_id="j-1",
        promotion_id="p-1",
        project_digest="0" * 64,
        diff_digest="1" * 64,
        verifier_id="verifier-1",
        verifier_version="1.0",
        environment_digest="2" * 64,
        evidence_ids=("ev-1",),
        observation_time=time.time(),
        passed=True,
    )
    assert receipt.passed is True
    assert receipt.mission_id == "m-1"


# ---------------------------------------------------------------------------
# Phase 7 RED Test: ExecutorRepairReceipt Schema Alignment
# ---------------------------------------------------------------------------


def test_red_7_executor_repair_receipt_forbids_extra_fields():
    """Proves ExecutorRepairReceipt forbids extra fields and enforces strict validation."""
    raw = {
        "job_id": "j-1",
        "mission_contract_digest": "0" * 64,
        "operation_id": "REMOVE_MAINTENANCE_MARKER_V1",
        "target": "target.py",
        "changed": True,
        "before_target_digest": "1" * 64,
        "after_target_digest": "2" * 64,
        "workspace_digest_before": "3" * 64,
        "workspace_digest_after": "4" * 64,
        "isolation_backend": "private_executor_v1",
        "environment_digest": "5" * 64,
        "started_timestamp": "2026-07-20T10:00:00Z",
        "ended_timestamp": "2026-07-20T10:00:01Z",
        "executor_service_identity_version": "1.0.0",
        "exit_code": 0,
        "receipt_version": "1.0",
    }
    receipt = ExecutorRepairReceipt.model_validate(raw)
    assert receipt.job_id == "j-1"

    # Extra field must raise ValidationError
    raw_extra = {**raw, "unauthorized_field": "injected"}
    with pytest.raises(ValidationError):
        ExecutorRepairReceipt.model_validate(raw_extra)


# ---------------------------------------------------------------------------
# Phase 8 RED Test: SkillApplicabilityAdvisoryV1 Forbids Extra Fields
# ---------------------------------------------------------------------------


def test_red_8_granite_advisory_contract_strict():
    """Proves SkillApplicabilityAdvisoryV1 strictly forbids extra fields."""
    raw = {
        "schema_version": "1.0",
        "skill_id": "skill-1",
        "skill_version": 1,
        "applicable": True,
        "confidence": 0.9,
        "reason_code": "EXACT_MATCH",
        "reason": "exact match",
        "bounded_procedure_id": "proc-1",
        "required_inputs_present": True,
        "abstain": False,
        "escalation_reason": None,
        "evidence_reference_ids": ("ev-1",),
    }
    advisory = SkillApplicabilityAdvisoryV1.model_validate(raw)
    assert advisory.applicable is True

    raw_extra = {**raw, "extra": "invalid"}
    with pytest.raises(ValidationError):
        SkillApplicabilityAdvisoryV1.model_validate(raw_extra)


# ---------------------------------------------------------------------------
# Phase 9 RED Test: Local Workforce Job & Model Call Records
# ---------------------------------------------------------------------------


def test_red_9_local_job_provenance_records():
    """Proves local workforce job requests, model calls, and result records are structured."""
    from aios.domain.local_workforce.contracts import (
        LocalJobRequestRecord,
        LocalModelCallRecord,
    )

    req = LocalJobRequestRecord(
        job_id="job-1",
        mission_id="m-1",
        skill_id="s-1",
        skill_version=1,
        job_profile="SELECT_SKILL",
        input_schema_version="1.0",
        qualification_suite_version="r15-v2",
        model_allowlist=("granite3.2:2b",),
        requested_model="granite3.2:2b",
        evidence_references=("s-1",),
        redacted_input_digest="0" * 64,
        token_budget=128,
        deadline="2026-07-20T10:10:00Z",
        created_at="2026-07-20T10:00:00Z",
    )
    assert req.job_id == "job-1"

    call = LocalModelCallRecord(
        local_model_call_id="call-1",
        local_job_id="job-1",
        provider="ollama",
        exact_model_id="granite3.2:2b",
        qualification_version="r15-v2",
        request_digest="0" * 64,
        response_digest="1" * 64,
        token_limits=128,
        measured_latency=150.0,
        start_time="2026-07-20T10:00:00Z",
        end_time="2026-07-20T10:00:01Z",
        status="completed",
        failure_reason=None,
    )
    assert call.local_model_call_id == "call-1"


# ---------------------------------------------------------------------------
# Phase 10 RED Test: Reuse Lineage Mandatory Reference
# ---------------------------------------------------------------------------


def test_red_10_reuse_outcome_reference_mandatory():
    """Proves ReuseOutcomeReference requires all lineage fields."""
    ref = ReuseOutcomeReference(
        reuse_outcome_id="reuse-1",
        skill_id="skill-1",
        skill_version=1,
        source_trajectory_id="traj-1",
        mission_id="m-1",
        worker_id="w-1",
        executor_job_id="exec-1",
        promotion_id="prom-1",
        local_job_id="ljob-1",
        local_model_call_id="lcall-1",
        verification_ids=("v-1",),
        workspace_digest="0" * 64,
        diff_digest="1" * 64,
        project_digest="2" * 64,
        contract_digest="3" * 64,
        policy_version="1.0",
    )
    assert ref.reuse_outcome_id == "reuse-1"


# ---------------------------------------------------------------------------
# Phase 11 RED Test: Secure Signing Keys
# ---------------------------------------------------------------------------


def test_red_11_production_signing_key_security():
    """Proves insecure signing key defaults fail closed in production startup."""
    from aios.config import validate_authority_signing_keys

    # Missing / default key must fail validation
    with pytest.raises(ValueError, match="key"):
        validate_authority_signing_keys(
            verification_key="aios-authority-verification-key-v1",
            promotion_key="aios-authority-promotion-key-v1",
            checkpoint_key="aios-authority-key",
            is_production=True,
        )


def _approved_maintenance_service(tmp_path, executor):
    worker = _MaintenanceWorker()
    service, project = _maintenance_service(tmp_path, worker=worker, executor=executor)
    initial = service.run_scan(
        _maintenance_contract(root=project),
        _maintenance_scanner,
        scanner_id="controlled-scanner",
        scanner_version="1",
        target_id="bug.txt",
        source_digest="source-before",
    )
    mission = service.create_repair_mission(
        initial.findings[0].fingerprint,
        operator_id="operator-1",
        workspace_root=str(project),
    )
    service.mission_service.start_deliberation(mission.mission_id)
    service.mission_service.request_approval(mission.mission_id)
    service.mission_service.approve(
        mission.mission_id,
        operator_id="operator-1",
        capability_digest="operator-capability-1",
        contract_digest=mission.contract_digest,
        authentication_event_id="auth-1",
        session_id="session-1",
    )
    return service, project, mission


class _ReceiptMutatingExecutor:
    def __init__(self, mutate):
        self.mutate = mutate

    def execute(self, job):  # noqa: ANN001
        result = executor_repair_result(job)
        return self.mutate(job, result)


def _run_receipt_refusal(tmp_path, mutate):
    service, project, mission = _approved_maintenance_service(
        tmp_path, _ReceiptMutatingExecutor(mutate)
    )
    result = asyncio.run(
        service.run_approved_repair(
            mission.mission_id,
            scanner=_maintenance_scanner,
            rescan_contract=_maintenance_contract(root=project),
            capability_consumer=lambda _request: True,
            create_checkpoint=lambda _request: "checkpoint-1",
            restore_checkpoint=lambda _checkpoint, _request: True,
            smoke_test=lambda _request: True,
        )
    )
    assert result.status == "EXECUTOR_PROVENANCE_INVALID"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda _job, result: result.model_copy(update={"stdout": "   "}),
        lambda _job, result: result.model_copy(update={"stdout": "{not-json"}),
        lambda _job, result: result.model_copy(
            update={
                "stdout": json.dumps(
                    {
                        key: value
                        for key, value in json.loads(result.stdout).items()
                        if key != "mission_contract_digest"
                    }
                )
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": json.dumps(
                    {**json.loads(result.stdout), "extra_field": "forged"}
                )
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {**json.loads(result.stdout), "job_id": "wrong-job"}
                ).model_dump_json()
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {
                        **json.loads(result.stdout),
                        "mission_contract_digest": "wrong-contract",
                    }
                ).model_dump_json()
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {**json.loads(result.stdout), "operation_id": "wrong-op"}
                ).model_dump_json()
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {**json.loads(result.stdout), "target": "other.txt"}
                ).model_dump_json()
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {**json.loads(result.stdout), "changed": False}
                ).model_dump_json()
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {**json.loads(result.stdout), "workspace_digest_before": "wrong"}
                ).model_dump_json()
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {**json.loads(result.stdout), "isolation_backend": "host"}
                ).model_dump_json()
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {**json.loads(result.stdout), "environment_digest": ""}
                ).model_dump_json()
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {**json.loads(result.stdout), "exit_code": 1}
                ).model_dump_json()
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {**json.loads(result.stdout), "receipt_version": "2.0"}
                ).model_dump_json()
            }
        ),
        lambda _job, result: result.model_copy(
            update={
                "stdout": ExecutorRepairReceipt.model_validate(
                    {**json.loads(result.stdout), "after_target_digest": "bad-digest"}
                ).model_dump_json()
            }
        ),
    ],
)
def test_maintenance_refuses_invalid_executor_receipts(tmp_path, mutate):
    _run_receipt_refusal(tmp_path, mutate)


def _learning_reuse_fixture(tmp_path, *, reuse_db=None):
    db_path = tmp_path / "learning-final.db"
    mission_repo = SqliteMissionRepository(db_path)
    mission_service = MissionService(mission_repo)
    trajectory_repo = TrajectoryRepository(db_path)
    skill_repo = SkillRepository(db_path)
    authority = VerificationAuthority(database_path=db_path)
    service = LearningService(
        mission_service=mission_service,
        trajectory_repository=trajectory_repo,
        skill_repository=skill_repo,
        verification_authority=authority,
        reuse_outcome_repository=reuse_db,
    )
    skill = SkillRecord(
        skill_id="skill-final",
        version=1,
        problem_signature="repair-json-parser",
        applicability_conditions={"format": "json"},
        known_exclusions=(),
        required_inputs=("path",),
        required_project_state={"env": "test"},
        procedure="repair",
        allowed_tools=("run_tests",),
        allowed_scope_pattern="src/*",
        expected_observations=("tests pass",),
        verification_plan=SkillVerifierSpec(
            verifier_id="skill.reuse",
            version="1",
            target_pattern="src/*",
            required_observations=("passed",),
            minimum_strength=1,
        ),
        escalation_conditions=(),
        source_trajectory_ids=("trajectory-final",),
        confidence=0.8,
        success_count=0,
        failure_count=0,
        last_validated_versions=("1",),
        state="active",
        created_at="2026-07-20T00:00:00Z",
        updated_at="2026-07-20T00:00:00Z",
    )
    if skill_repo.get(skill.skill_id, skill.version) is None:
        skill_repo.save(skill)
    save_minimal_trajectory(trajectory_repo, "trajectory-final")
    try:
        mission = mission_repo.get("reuse-final")
    except Exception:
        mission = mission_repo.create(
            MissionContract(
                mission_id="reuse-final",
                project_id="project-final",
                operator_id="operator-1",
                goal="reuse",
                worker_type="local-clerk",
                created_by="test",
                metadata={"skill_id": skill.skill_id},
            ),
            state=MissionState.COMPLETED,
        )
    verification = authority.verify(
        mission_id=mission.mission_id,
        action_id="reuse-action",
        worker_id="worker-final",
        target="unit-tests",
        plan=VerificationPlanV1(
            intended_behavior="reuse passes",
            targets=("unit-tests",),
            minimum_strength=1,
        ),
        workspace_digest="workspace-final",
        diff_digest="diff-final",
        environment_digest="env-final",
        observation=VerificationObservation(
            command="pytest",
            exit_code=0,
            stdout="1 passed",
            passed_count=1,
            tool_version="pytest",
        ),
    )
    reference = reuse_outcome_reference(
        reuse_outcome_id="reuse-outcome-final",
        skill=skill,
        trajectory_id="trajectory-final",
        mission=mission,
        verification=verification,
        worker_id="worker-final",
        workspace_digest="workspace-final",
        diff_digest="diff-final",
    )
    return service, reference


def test_record_reuse_outcome_rejects_legacy_kwargs(tmp_path):
    service, _reference = _learning_reuse_fixture(tmp_path)
    with pytest.raises(TypeError):
        service.record_reuse_outcome(
            skill_id="skill-final",
            version=1,
            mission_id="reuse-final",
            verification_results=(),
            workspace_digest="workspace-final",
            diff_digest="diff-final",
        )


def test_duplicate_reuse_reference_does_not_double_increment(tmp_path):
    service, reference = _learning_reuse_fixture(tmp_path)
    first = service.record_reuse_outcome(reference)
    second = service.record_reuse_outcome(reference)
    assert first.success_count == 1
    assert second.success_count == 1
    assert second.confidence == first.confidence


def test_reuse_idempotency_survives_learning_service_restart(tmp_path):
    repo = ReuseOutcomeRepository(tmp_path / "reuse-outcomes.db")
    first_service, reference = _learning_reuse_fixture(tmp_path, reuse_db=repo)
    first = first_service.record_reuse_outcome(reference)
    second_service, _ = _learning_reuse_fixture(tmp_path, reuse_db=repo)
    second = second_service.record_reuse_outcome(reference)
    assert first.success_count == 1
    assert second.success_count == 1
    assert second.confidence == first.confidence
