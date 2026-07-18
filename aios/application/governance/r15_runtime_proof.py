"""R15 executable runtime proof matrix for the GAGOS boundary.

The proof runner deliberately uses disposable stores and explicit dependency
injection. It never treats a source file as runtime evidence.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from unittest.mock import MagicMock, patch

from aios.application.governance.runtime_proof import RuntimeProof, _proof


R15_REQUIRED_PROOFS = (
    "local_workforce_registry",
    "local_workforce_qualification",
    "local_workforce_non_authority",
    "hardware_admission",
    "canonical_intelligence_hiring",
    "privacy_gated_cloud_use",
    "expert_trajectory_provenance",
    "skill_applicability",
    "skill_re_escalation",
    "maintenance_finding_persistence",
    "maintenance_canonical_repair",
    "maintenance_rescan_resolution",
)


@dataclass(frozen=True, slots=True)
class R15RuntimeProofReport:
    proofs: dict[str, RuntimeProof]

    @property
    def all_passed(self) -> bool:
        return all(self.proofs[name].passed for name in R15_REQUIRED_PROOFS)

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(
            name for name in R15_REQUIRED_PROOFS if not self.proofs[name].passed
        )

    def boolean_map(self) -> dict[str, bool]:
        return {name: self.proofs[name].passed for name in R15_REQUIRED_PROOFS}

    def evidence_map(self) -> dict[str, str]:
        return {name: self.proofs[name].evidence for name in R15_REQUIRED_PROOFS}

    def as_dict(self) -> dict[str, object]:
        return {
            "all_passed": self.all_passed,
            "failures": list(self.failures),
            "proofs": {
                name: {
                    "name": proof.name,
                    "passed": proof.passed,
                    "evidence": proof.evidence,
                }
                for name, proof in self.proofs.items()
            },
        }


def run_r15_runtime_proofs(root: str | Path | None = None) -> R15RuntimeProofReport:
    """Execute the complete disposable R15 proof matrix."""
    with tempfile.TemporaryDirectory(prefix="gagos-r15-runtime-proof-") as raw:
        scratch = Path(raw)
        results: dict[str, RuntimeProof] = {}

        results["local_workforce_registry"] = _proof(
            "local_workforce_registry", lambda: _probe_local_workforce_registry(scratch)
        )
        results["local_workforce_qualification"] = _proof(
            "local_workforce_qualification",
            lambda: _probe_local_workforce_qualification(scratch),
        )
        results["local_workforce_non_authority"] = _proof(
            "local_workforce_non_authority",
            lambda: _probe_local_workforce_non_authority(scratch),
        )
        results["hardware_admission"] = _proof(
            "hardware_admission", lambda: _probe_hardware_admission(scratch)
        )
        results["canonical_intelligence_hiring"] = _proof(
            "canonical_intelligence_hiring",
            lambda: _probe_canonical_intelligence_hiring(scratch),
        )
        results["privacy_gated_cloud_use"] = _proof(
            "privacy_gated_cloud_use", lambda: _probe_privacy_gated_cloud_use(scratch)
        )
        results["expert_trajectory_provenance"] = _proof(
            "expert_trajectory_provenance",
            lambda: _probe_expert_trajectory_provenance(scratch),
        )
        results["skill_applicability"] = _proof(
            "skill_applicability", lambda: _probe_skill_applicability(scratch)
        )
        results["skill_re_escalation"] = _proof(
            "skill_re_escalation", lambda: _probe_skill_re_escalation(scratch)
        )
        results["maintenance_finding_persistence"] = _proof(
            "maintenance_finding_persistence",
            lambda: _probe_maintenance_finding_persistence(scratch),
        )
        results["maintenance_canonical_repair"] = _proof(
            "maintenance_canonical_repair",
            lambda: _probe_maintenance_canonical_repair(scratch),
        )
        results["maintenance_rescan_resolution"] = _proof(
            "maintenance_rescan_resolution",
            lambda: _probe_maintenance_rescan_resolution(scratch),
        )

    return R15RuntimeProofReport(results)


def _probe_local_workforce_registry(scratch: Path) -> str:
    from aios.domain.local_workforce.contracts import LocalJobProfile
    from aios.domain.local_workforce.registry import LocalWorkforceRegistry
    from aios.memory import db

    database = scratch / "local-workforce.db"
    client = MagicMock()
    client.list_detailed_models.return_value = [
        {
            "name": "qwen2.5-coder:7b",
            "details": {
                "family": "qwen",
                "parameter_size": "7B",
                "quantization_level": "Q4_K_M",
            },
        }
    ]
    connection = partial(db.get_connection, database)
    with patch("aios.domain.local_workforce.registry.get_connection", connection):
        db.init_memory_db(database)
        first = LocalWorkforceRegistry(client)
        first.reconcile()
        first.update_approval("qwen2.5-coder:7b", True)
        first.update_admission("qwen2.5-coder:7b", "approved", "fixture qualified")
        first.update_profiles("qwen2.5-coder:7b", {LocalJobProfile.SUMMARISE})
        first.record_health("qwen2.5-coder:7b", "healthy")

        second = LocalWorkforceRegistry(client)
        restored = second.get_model("qwen2.5-coder:7b")

    assert restored is not None
    assert restored.operator_approved is True
    assert restored.admission_status == "approved"
    assert restored.health == "healthy"
    assert restored.allowed_job_profiles == frozenset({LocalJobProfile.SUMMARISE})
    return "registry restart preserved approval, admission, profile, and health state"


def _probe_local_workforce_qualification(scratch: Path) -> str:
    from aios.domain.local_workforce.qualifier import QualificationSuite

    class QualificationClient:
        def complete(
            self, prompt: str, *, system: str | None = None, json_mode: bool = False
        ) -> str:
            if "API key" in prompt:
                return '{"summary": "credential redacted"}'
            return '{"error_code": "connection_refused", "message": "port 8080", "log_id": "ABC-123"}'

    result = QualificationSuite(QualificationClient()).run()
    assert result.passed is True
    assert result.schema_validity == 1.0
    assert result.identifier_preservation == 1.0
    assert result.authority_mutation_attempts == 0
    assert result.tool_requests_accepted == 0
    assert result.secret_reproduction == 0
    return "qualification fixtures passed schema and identifier gates with zero authority, tool, or secret violations"


def _probe_local_workforce_non_authority(scratch: Path) -> str:
    from aios.domain.local_workforce.contracts import LocalJobProfile, LocalJobRequest
    from aios.domain.local_workforce.runtime import StructuredClericalRuntime

    class AdvisoryClient:
        def complete(
            self, prompt: str, *, system: str | None = None, json_mode: bool = False
        ) -> str:
            assert json_mode is True
            return '{"summary": "advisory result", "related_id": "evidence-1"}'

    request = LocalJobRequest(
        job_id="local-proof-1",
        job_profile=LocalJobProfile.SUMMARISE,
        input_schema_version="1.0",
        evidence_references=frozenset({"evidence-1"}),
        redacted_payload="bounded evidence",
        token_budget=200,
        deadline=datetime.now(timezone.utc),
        required_output_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "related_id": {"type": "string"},
            },
            "required": ["summary"],
        },
    )
    result = StructuredClericalRuntime(AdvisoryClient()).execute_job(request)
    assert result.status == "completed"
    assert result.schema_valid is True
    assert result.evidence_references_preserved is True
    assert "command" not in result.structured_output
    assert "authority_override" not in result.structured_output
    return "structured local result preserved evidence and exposed no authority or tool fields"


def _probe_hardware_admission(scratch: Path) -> str:
    from aios.domain.local_workforce.admission import (
        AdmissionContext,
        HardwareAdmission,
    )

    gate = HardwareAdmission(min_cpu_count=1, max_concurrent_inferences=1)
    admitted = gate.evaluate(
        AdmissionContext(requested_context_size=4096, requested_output_size=512)
    )
    refused = gate.evaluate(
        AdmissionContext(
            requested_context_size=4096,
            requested_output_size=512,
            active_local_inference_count=1,
        )
    )
    assert admitted.admitted is True
    assert refused.admitted is False
    return "hardware admission accepted an idle fixture and refused an over-concurrency fixture"


def _probe_canonical_intelligence_hiring(scratch: Path) -> str:
    from aios.domain.intelligence.broker import HiringBroker
    from aios.domain.intelligence.contracts import HiringRequest

    request = HiringRequest(
        problem_id="problem-1",
        mission_id="mission-1",
        purpose="classify bounded evidence",
        task_class="reasoning",
        required_capabilities=["reasoning"],
        data_classification="internal",
        context_manifest=["evidence-1"],
        privacy_budget="internal-only",
        cost_budget="high",
        latency_budget=1000,
        candidate_providers=["bedrock", "ollama"],
        verification_requirements=["schema", "human approval for cloud"],
    )
    decision = HiringBroker().evaluate_request(request)
    assert decision.selected_provider == "ollama"
    assert set(decision.eligible_providers).issubset(set(request.candidate_providers))
    assert decision.selected_model == "auto"
    return "hiring selected the lowest-cost eligible provider from the declared candidate set"


def _probe_privacy_gated_cloud_use(scratch: Path) -> str:
    from aios.application.models.privacy_broker import PrivacyBroker
    from aios.domain.privacy import DataClassification, ModelCallRequest, PrivacyPolicy

    request = ModelCallRequest(
        request_id="privacy-proof-1",
        principal_id="operator-1",
        purpose="privacy proof",
        prompt="api_key = abcdef1234567890abcdef must remain local",
        data_classification=DataClassification.SECRET,
        policy=PrivacyPolicy(
            data_classification=DataClassification.SECRET,
            local_only=False,
            allowed_providers=("ollama", "bedrock"),
        ),
    )
    decision = PrivacyBroker().evaluate(request)
    assert decision.allowed is True
    assert decision.local_only is True
    assert decision.allowed_providers == ("ollama",)
    assert "abcdef1234567890abcdef" not in decision.scrubbed_prompt
    return "secret classification redacted the prompt and reduced provider eligibility to local Ollama"


def _probe_expert_trajectory_provenance(scratch: Path) -> str:
    from aios.domain.learning.contracts import ExpertTrajectory
    from aios.domain.learning.trajectory_gate import TrajectoryGate, TrajectoryGateError

    trajectory = ExpertTrajectory(
        problem_signature="repair-json-parser",
        project_digest="project-1",
        expert_provider="bedrock",
        expert_model="frontier-fixture",
        context_digest="context-1",
        proposal_digest="proposal-1",
        actions_attempted=2,
        failed_attempts=0,
        successful_actions=2,
        tool_observations=["tests passed"],
        verification_plan="run focused tests",
        verification_results="PASS: 2 tests",
        promotion_result="human-approved",
        rollback_result=None,
        human_interventions=1,
        final_outcome="success",
    )
    assert TrajectoryGate().qualify(trajectory) is True
    try:
        TrajectoryGate().qualify(trajectory.model_copy(update={"context_digest": ""}))
    except TrajectoryGateError:
        pass
    else:
        raise AssertionError("trajectory without context provenance was accepted")
    return "complete proposal, action, verification, promotion, and context provenance qualified; incomplete context refused"


def _probe_skill_applicability(scratch: Path) -> str:
    from aios.domain.learning.applicability import (
        ApplicabilityError,
        SkillApplicabilityEngine,
    )

    skill = _proof_skill()
    engine = SkillApplicabilityEngine()
    assert (
        engine.check_applicability(
            skill,
            {"log_path": "data/logs/app.json"},
            {"has_json_parser": "true"},
        )
        is True
    )
    try:
        engine.check_applicability(
            skill, {"log_path": "data/logs/app.json"}, {"has_json_parser": "false"}
        )
    except ApplicabilityError:
        pass
    else:
        raise AssertionError("skill state mismatch was accepted")
    return "active skill passed required-input and project-state checks; state mismatch refused"


def _probe_skill_re_escalation(scratch: Path) -> str:
    from aios.domain.learning.reuse_orchestrator import (
        EscalateToFrontierDirective,
        LocalExecutionDirective,
        SkillReuseOrchestrator,
    )
    from aios.domain.learning.applicability import SkillApplicabilityEngine

    orchestrator = SkillReuseOrchestrator(SkillApplicabilityEngine())
    skill = _proof_skill()
    local = orchestrator.attempt_reuse(
        [skill], {"log_path": "data/logs/app.json"}, {"has_json_parser": "true"}
    )
    escalated = orchestrator.attempt_reuse([skill], {}, {"has_json_parser": "true"})
    assert isinstance(local, LocalExecutionDirective)
    assert isinstance(escalated, EscalateToFrontierDirective)
    return "applicable skill reused locally and missing input deterministically escalated to frontier"


def _probe_maintenance_finding_persistence(scratch: Path) -> str:
    from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
    from aios.domain.maintenance.repository import MaintenanceFindingRepository

    finding = _proof_finding()
    repository = MaintenanceFindingRepository(scratch / "maintenance.db")
    repository.save(finding)
    restored = MaintenanceFindingRepository(scratch / "maintenance.db").get(
        finding.fingerprint
    )
    assert restored == finding

    resolved = MaintenanceLifecycleEngine().attempt_resolution(
        restored, actor="system_verifier", deterministic_evidence="rescan clean"
    )
    repository.save(resolved)
    reappeared = MaintenanceLifecycleEngine().report_finding(
        MaintenanceFindingRepository(scratch / "maintenance.db").get(
            finding.fingerprint
        ),
        finding.model_copy(update={"last_seen": "2026-07-18T02:00:00Z"}),
    )
    assert reappeared.status == "REOPENED"
    assert reappeared.occurrence_count == 2
    return "finding survived repository restart, resolved with evidence, and reopened on reappearance"


def _probe_maintenance_canonical_repair(scratch: Path) -> str:
    from aios.domain.maintenance.mission_bridge import MaintenanceMissionBridge
    from aios.domain.maintenance.scan_contracts import BoundedScanContract
    from aios.domain.maintenance.service import AutonomousMaintenanceForce
    from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine

    finding = _proof_finding()
    service = AutonomousMaintenanceForce(MaintenanceLifecycleEngine())
    scan = service.run_bounded_scan(
        BoundedScanContract(
            allowed_root="training_ground",
            max_files=2,
            max_total_bytes=2048,
            max_file_bytes=1024,
            deadline=60,
            max_findings=1,
            git_history_allowed=False,
        ),
        lambda: [finding],
    )
    proposal = service.prepare_repair_proposal(scan[0])
    mission = MaintenanceMissionBridge.create_repair_mission(scan[0], "operator-1")
    assert proposal["finding_id"] == finding.finding_id
    assert mission.metadata["finding_id"] == finding.finding_id
    assert mission.metadata["required_post_repair_rescan"] is True
    assert mission.requires_approval is True
    return "bounded scan produced an advisory proposal and canonical approval-bound repair mission"


def _probe_maintenance_rescan_resolution(scratch: Path) -> str:
    from aios.domain.maintenance.lifecycle import (
        MaintenanceLifecycleEngine,
        SecurityViolationError,
    )

    finding = _proof_finding()
    lifecycle = MaintenanceLifecycleEngine()
    try:
        lifecycle.attempt_resolution(
            finding, actor="local_model", deterministic_evidence="rescan clean"
        )
    except SecurityViolationError:
        pass
    else:
        raise AssertionError("local model was allowed to close a finding")
    resolved = lifecycle.attempt_resolution(
        finding, actor="system_verifier", deterministic_evidence="current rescan clean"
    )
    assert resolved.status == "VERIFIED_RESOLVED"
    assert resolved.resolution_evidence == "current rescan clean"
    return "local actor could not resolve; system verifier required current deterministic rescan evidence"


def _proof_skill():
    from aios.domain.learning.skill_contracts import SkillContract

    return SkillContract(
        skill_id="skill-proof-1",
        version=1,
        problem_signature="parse-json-logs",
        applicability_conditions={"log_format": "json"},
        known_exclusions=["malformed_json_fallback"],
        required_inputs=["log_path"],
        required_project_state={"has_json_parser": "true"},
        procedure="Parse the bounded JSON log",
        allowed_tools=["read_file", "parse_json"],
        allowed_scope_pattern="data/logs/*.json",
        expected_observations=["Parsed JSON tree"],
        verification_plan="Assert JSON tree matches schema",
        escalation_conditions=["SyntaxError"],
        source_trajectory_ids=["trajectory-proof-1"],
        confidence=0.9,
        success_count=5,
        failure_count=0,
        last_validated_versions=["1.0.0"],
        state="active",
    )


def _proof_finding():
    from aios.domain.maintenance.contracts import MaintenanceFinding

    return MaintenanceFinding(
        finding_id="finding-proof-1",
        fingerprint="fingerprint-proof-1",
        scanner_id="fixture-scanner",
        scanner_version="1.0",
        kind="dead_code",
        severity="medium",
        confidence=0.95,
        evidence_quality="deterministic",
        target_id="training_ground/example.py",
        target_digest="target-digest-1",
        source_digest="source-digest-1",
        first_seen="2026-07-18T00:00:00Z",
        last_seen="2026-07-18T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="fixture scanner found unused function",
    )
