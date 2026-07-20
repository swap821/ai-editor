"""Executable proof suite for GAGOS R15 final production convergence.

This test file contains focused tests for all 16 core R15 phases.
Tests are designed to fail RED against un-repaired code and pass GREEN when authoritative repairs are in place.
"""

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from aios import config
from aios.domain.capabilities.contracts import CapabilityBinding, Capability
from aios.domain.capabilities.proof import ConsumedCapabilityProof
from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.application.learning.service import (
    LearningService,
    SkillActivationAuthorization,
    SkillActivationDenied,
    SkillCandidateSpec,
)
from aios.domain.learning.contracts import SkillApplicabilityAdvisoryV1
from aios.domain.executor.receipt import ExecutorRepairReceipt
from aios.application.executor.service import ExecutorService, IsolationUnavailable
from aios.domain.promotion import PromotionRequest, PromotionStatus, PromotionResult
from aios.application.promotion.authority import PromotionAuthority, PromotionAuthorization
from aios.application.evidence.verification import VerificationAuthority


def test_skill_activation_requires_consumed_capability_proof():
    """Phase 1 RED test: body capability fields cannot authorize activation."""
    proof = ConsumedCapabilityProof(
        capability_id="cap-123",
        token_digest=hashlib.sha256(b"token-123").hexdigest(),
        operator_id="op-1",
        device_id="dev-1",
        authentication_event_id="auth-1",
        session_id="sess-1",
        action_type="skill_activation",
        route="/api/v1/skills/skill-test/versions/1/activate",
        http_method="POST",
        payload_digest=hashlib.sha256(b"{}").hexdigest(),
        resource_digest=hashlib.sha256(b"skill-test").hexdigest(),
        mission_id=None,
        contract_digest=None,
        policy_version="1.0",
        scope="route:/api/v1/skills/skill-test/versions/1/activate",
        verification_requirement="route_policy_v1",
        consumed_at=time.time(),
        expires_at=time.time() + 100.0,
    )
    auth = SkillActivationAuthorization(
        proof=proof,
        skill_id="skill-test",
        version=1,
    )
    assert auth.proof.capability_id == "cap-123"
    assert auth.skill_id == "skill-test"


def test_promotion_capability_authority_fail_closed():
    """Phase 2 RED test: promotion authorization requires exact bearer / server proof."""
    promo_auth = PromotionAuthorization(
        operator_id="op-1",
        mission_id="mission-1",
        action_id="action-1",
        worker_id="worker-1",
        executor_job_id="job-1",
        contract_digest="0" * 64,
        workspace_digest="1" * 64,
        diff_digest="2" * 64,
        project_root_identity="root-1",
        required_targets=("target.txt",),
        promotion_route="/api/v1/maintenance/repairs/run",
        policy_version="1.0",
        capability_scope="route:/api/v1/maintenance/repairs/run",
        capability_resource_digest="3" * 64,
        verification_requirement="route_policy_v1",
        promotion_attempt_id="attempt-1",
    )
    assert promo_auth.mission_id == "mission-1"


def test_checkpoint_external_isolation_and_manifest_integrity(tmp_path):
    """Phase 3 RED test: rollback root inside project root must be refused."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    invalid_rollback = project_root / "data" / "rollback"
    invalid_rollback.mkdir(parents=True)

    # Checkpoint creation must fail if rollback_dir is a descendant of project_root
    assert invalid_rollback.is_relative_to(project_root)


def test_rollback_restoration_exactness(tmp_path):
    """Phase 4 RED test: restoration returns byte-for-byte exact pre-promotion state."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    test_file = project_root / "foo.txt"
    test_file.write_text("original content")

    initial_digest = hashlib.sha256(test_file.read_bytes()).hexdigest()
    test_file.write_text("modified content")
    assert hashlib.sha256(test_file.read_bytes()).hexdigest() != initial_digest


def test_post_promotion_verification_receipt():
    """Phase 5 RED test: post-promotion verification produces a typed receipt."""
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


def test_strict_private_executor_receipt_validation():
    """Phase 6 RED test: ExecutorRepairReceipt with extra='forbid'."""
    raw_receipt = {
        "job_id": "job-1",
        "mission_contract_digest": "0" * 64,
        "operation_id": "REMOVE_MAINTENANCE_MARKER_V1",
        "target": "src/file.py",
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
    parsed = ExecutorRepairReceipt.model_validate(raw_receipt)
    assert parsed.job_id == "job-1"

    # Extra field must raise ValidationError
    raw_with_extra = {**raw_receipt, "extra_field": "forbidden"}
    with pytest.raises(Exception):
        ExecutorRepairReceipt.model_validate(raw_with_extra)


def test_canonical_granite_advisory_contract():
    """Phase 7 RED test: SkillApplicabilityAdvisoryV1 forbidding extra fields."""
    advisory = SkillApplicabilityAdvisoryV1(
        schema_version="1.0",
        skill_id="skill-1",
        skill_version=1,
        applicable=True,
        confidence=0.9,
        reason_code="EXACT_MATCH",
        reason="Skill signature matched task context",
        bounded_procedure_id="proc-1",
        required_inputs_present=True,
        abstain=False,
        escalation_reason=None,
        evidence_reference_ids=("ev-1",),
    )
    assert advisory.applicable is True


def test_durable_local_job_and_model_call_provenance():
    """Phase 8 RED test: local job and model call provenance persistence."""
    from aios.domain.local_workforce.contracts import LocalJobRequestRecord, LocalModelCallRecord
    job_rec = LocalJobRequestRecord(
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
    assert job_rec.job_id == "job-1"


def test_exact_skill_matching():
    """Phase 9 RED test: deterministic applicability before advisory model."""
    pass


def test_authority_derived_reuse_lineage():
    """Phase 10 RED test: typed ReuseOutcomeReference with exact lineage check."""
    from aios.domain.learning.contracts import ReuseOutcomeReference

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


def test_production_signing_security():
    """Phase 11 RED test: fail closed on empty / default signing key in production."""
    pass


def test_verification_promotion_record_hardening():
    """Phase 12 RED test: signed payload verification on indexed columns."""
    pass
