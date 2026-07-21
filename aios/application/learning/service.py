"""Canonical R15 trajectory capture, skill activation and reuse flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from aios.domain.capabilities.proof import ConsumedCapabilityProof


from aios.application.evidence.verification import VerificationAuthority
from aios.application.missions.mission_service import MissionService
from aios.domain.evidence import VerificationPlanV1, VerificationResult
from aios.domain.verification import SkillVerifierSpec
from aios.domain.learning.applicability import SkillApplicabilityEngine
from aios.domain.learning.confidence import ConfidenceUpdater
from aios.domain.learning.contracts import (
    ExpertTrajectory,
    ReuseOutcomeReference,
    ToolObservation,
    TrajectoryVerification,
)
from aios.domain.learning.repository import SkillRecord, SkillRepository
from aios.domain.learning.reuse_outcome_repository import ReuseOutcomeRepository
from aios.domain.learning.reuse_orchestrator import (
    EscalateToFrontierDirective,
    LocalExecutionDirective,
    SkillReuseOrchestrator,
)
from aios.domain.learning.trajectory_gate import TrajectoryGate
from aios.domain.learning.trajectory_repository import (
    TrajectoryRecord,
    TrajectoryRepository,
)
from aios.domain.missions.mission_contract import (
    MissionContract,
    VerificationPlan as MissionVerificationPlan,
)
from aios.domain.missions.mission_repository import MissionRecord
from aios.domain.missions.mission_state import MissionState
from aios.domain.promotion import PromotionResult, PromotionStatus


from aios.application.promotion.authority import PromotionAuthority


class SkillActivationDenied(RuntimeError):
    """Raised when a skill lacks an external Human/authority approval."""


@dataclass(frozen=True)
class SkillActivationAuthorization:
    """Server-issued activation authorization derived from a consumed capability proof."""

    proof: ConsumedCapabilityProof
    skill_id: str
    version: int


class SkillCandidateSpec(BaseModel):
    """Structured candidate fields supplied by intelligence, never authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_id: str
    version: int
    problem_signature: str
    applicability_conditions: dict[str, str]
    known_exclusions: tuple[str, ...]
    required_inputs: tuple[str, ...]
    required_project_state: dict[str, str]
    procedure: str
    allowed_tools: tuple[str, ...]
    allowed_scope_pattern: str
    expected_observations: tuple[str, ...]
    verification_plan: SkillVerifierSpec
    escalation_conditions: tuple[str, ...]
    validated_versions: tuple[str, ...]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_reuse_outcome_db(repository: TrajectoryRepository) -> Path | str:
    database = getattr(repository, "database", None)
    if isinstance(database, Path | str):
        return database
    return ":memory:"


class LearningService:
    """Use existing mission, verification and durable-memory authorities."""

    def __init__(
        self,
        *,
        mission_service: MissionService,
        trajectory_repository: TrajectoryRepository,
        skill_repository: SkillRepository | None = None,
        activation_authorizer: Callable[..., bool] | None = None,
        verification_plan_validator: Callable[[SkillRecord], bool] | None = None,
        reuse_policy: Callable[[SkillRecord, Mapping[str, object]], bool] | None = None,
        verification_authority: VerificationAuthority | None = None,
        promotion_authority: PromotionAuthority | None = None,
        local_workforce_service: Any | None = None,
        reuse_outcome_repository: ReuseOutcomeRepository | None = None,
        minimum_confidence: float = 0.8,
    ) -> None:
        self.mission_service = mission_service
        self.trajectory_repository = trajectory_repository
        self.skill_repository = skill_repository or SkillRepository(
            trajectory_repository.database
        )
        self.activation_authorizer = activation_authorizer
        self.verification_plan_validator = verification_plan_validator
        self.reuse_policy = reuse_policy
        self.verification_authority = verification_authority or VerificationAuthority()
        self.promotion_authority = promotion_authority
        self.local_workforce_service = local_workforce_service
        self.reuse_outcome_repository = (
            reuse_outcome_repository
            if reuse_outcome_repository is not None
            else ReuseOutcomeRepository(_default_reuse_outcome_db(trajectory_repository))
        )
        self.applicability = SkillApplicabilityEngine(minimum_confidence)
        self.reuse = SkillReuseOrchestrator(self.applicability)
        self.trajectory_gate = TrajectoryGate()
        self.confidence = ConfidenceUpdater()

    def capture_trajectory(
        self,
        *,
        mission: MissionRecord,
        project_digest: str,
        expert_provider: str,
        expert_model: str,
        context_digest: str,
        proposal_digest: str,
        tool_observations: Sequence[ToolObservation],
        verification_plan: VerificationPlanV1,
        verification_results: Sequence[VerificationResult],
        promotion: PromotionResult,
        human_intervention_ids: Sequence[str],
    ) -> TrajectoryRecord:
        """Capture only the current authoritative mission outcome."""
        authoritative = self.mission_service.repository.get(mission.mission_id)
        if authoritative.contract_digest != mission.contract_digest:
            raise ValueError("mission contract digest is not authoritative")
        if authoritative.state is not MissionState.COMPLETED:
            raise ValueError("only a completed mission can produce a trajectory")
        if promotion.mission_id != authoritative.mission_id:
            raise ValueError("promotion mission does not match trajectory mission")
        if promotion.status is not PromotionStatus.PROMOTED:
            raise ValueError("only promoted work can produce a trajectory")
        if (
            self.promotion_authority is not None
            and not self.promotion_authority.is_authoritative(promotion)
        ):
            raise ValueError("promotion result is not held by PromotionAuthority")
        results = tuple(verification_results)
        if not results:
            raise ValueError("structured verification results are required")
        if any(result.mission_id != authoritative.mission_id for result in results):
            raise ValueError("verification mission does not match trajectory mission")
        if any(
            not self.verification_authority.is_authoritative(result)
            for result in results
        ):
            raise ValueError("verification evidence is not authoritative")
        if any(not result.meets_requirement for result in results):
            raise ValueError("verification requirement is not met")
        if any(
            not self.verification_authority.is_current(
                result,
                workspace_digest=result.workspace_digest,
                diff_digest=result.diff_digest,
            )
            for result in results
        ):
            raise ValueError("verification evidence is stale")
        if any(
            result.required_strength < verification_plan.minimum_strength
            for result in results
        ):
            raise ValueError("verification plan strength is not bound to result")

        observations = tuple(tool_observations)
        if not observations:
            raise ValueError("tool observations are required")
        structured_results = tuple(
            TrajectoryVerification(
                verification_id=result.verification_id,
                mission_id=result.mission_id,
                action_id=result.action_id,
                passed=result.passed,
                strength=result.strength,
                required_strength=result.required_strength,
                evidence_ids=result.evidence_ids,
            )
            for result in results
        )
        trajectory = ExpertTrajectory(
            trajectory_id=f"trajectory-{uuid4().hex}",
            mission_id=authoritative.mission_id,
            contract_digest=authoritative.contract_digest,
            problem_signature=authoritative.contract.metadata.get(
                "problem_signature", authoritative.contract.goal
            ),
            project_digest=project_digest,
            expert_provider=expert_provider,
            expert_model=expert_model,
            context_digest=context_digest,
            proposal_digest=proposal_digest,
            actions_attempted=len(observations),
            failed_attempts=sum(item.status != "completed" for item in observations),
            successful_actions=sum(item.status == "completed" for item in observations),
            tool_observations=observations,
            verification_plan=verification_plan,
            verification_results=structured_results,
            verification_strength=min(result.strength for result in results),
            promotion_status=promotion.status.value,
            promotion_evidence_ids=promotion.evidence_ids,
            rollback_result=None,
            human_intervention_ids=tuple(human_intervention_ids),
            final_mission_status=authoritative.state.value,
            final_outcome="success",
        )
        self.trajectory_gate.qualify(trajectory)
        now = _utc_now()
        record = TrajectoryRecord(
            **trajectory.model_dump(), created_at=now, updated_at=now
        )
        self.trajectory_repository.save(record)
        return record

    def create_skill_candidate(
        self, trajectory_id: str, candidate: SkillCandidateSpec
    ) -> SkillRecord:
        trajectory = self.trajectory_repository.get(trajectory_id)
        if trajectory is None:
            raise KeyError(f"trajectory {trajectory_id!r} not found")
        self.trajectory_gate.qualify(trajectory)
        if candidate.problem_signature != trajectory.problem_signature:
            raise ValueError("skill signature does not match source trajectory")
        now = _utc_now()
        skill = SkillRecord(
            **candidate.model_dump(exclude={"validated_versions"}, mode="python"),
            source_trajectory_ids=(trajectory_id,),
            confidence=0.8,
            success_count=0,
            failure_count=0,
            last_validated_versions=candidate.validated_versions,
            state="candidate",
            created_at=now,
            updated_at=now,
        )
        self.skill_repository.save(skill)
        return skill

    def activate_skill(
        self,
        authorization: SkillActivationAuthorization,
    ) -> SkillRecord:
        """Activate a candidate skill using an exact capability-backed Human approval."""
        if not isinstance(authorization, SkillActivationAuthorization):
            raise SkillActivationDenied(
                "authorization must be a SkillActivationAuthorization instance"
            )

        proof = authorization.proof
        target_skill_id = authorization.skill_id
        ver = authorization.version

        skill = self.skill_repository.get(target_skill_id, ver)
        if skill is None:
            raise KeyError(f"skill {target_skill_id!r} version {ver} not found")

        if skill.state != "candidate":
            raise SkillActivationDenied(
                f"skill is in state {skill.state!r}, expected 'candidate'"
            )

        now = time.time()
        if proof.expires_at <= now or proof.revoked_at is not None:
            raise SkillActivationDenied(
                "consumed capability proof is expired or revoked"
            )
        if not proof.operator_id or not proof.operator_id.strip():
            raise SkillActivationDenied(
                "consumed capability proof operator_id is invalid"
            )
        if proof.action_type.lower() not in (
            "skill_activation",
            "route.skill_activation",
            "yellow",
        ):
            raise SkillActivationDenied(
                f"consumed capability proof action_type mismatch: {proof.action_type}"
            )
        expected_route = f"/api/v1/skills/{target_skill_id}/versions/{ver}/activate"
        if expected_route not in proof.route:
            raise SkillActivationDenied(
                f"consumed capability proof route mismatch: {proof.route}"
            )
        if proof.http_method.upper() != "POST":
            raise SkillActivationDenied(
                f"consumed capability proof http_method mismatch: {proof.http_method}"
            )

        reviewed = self.skill_repository.transition_state(
            target_skill_id, ver, "human_reviewed"
        )
        if reviewed is None or reviewed.state != "human_reviewed":
            raise SkillActivationDenied("skill review transition failed")
        activated = self.skill_repository.transition_state(
            target_skill_id, ver, "active"
        )
        if activated is None or activated.state != "active":
            raise SkillActivationDenied("skill activation transition failed")

        return activated

    def attempt_local_reuse(
        self,
        *,
        skill_id: str,
        version: int,
        mission_id: str,
        operator_id: str,
        goal: str,
        project_id: str,
        current_inputs: dict[str, str],
        current_state: dict[str, str],
        current_scope: str,
        mission_allowed_tools: Sequence[str],
        validated_version: str,
    ) -> LocalExecutionDirective | EscalateToFrontierDirective:
        skill = self.skill_repository.get(skill_id, version)
        if skill is None:
            return EscalateToFrontierDirective(
                reason="Skill is not present in durable library"
            )
        context = {
            "mission_id": mission_id,
            "operator_id": operator_id,
            "project_id": project_id,
            "goal": goal,
        }
        verification_plan_executable = bool(
            self.verification_plan_validator is not None
            and self.verification_plan_validator(skill)
        )
        policy_allows = bool(
            self.reuse_policy is not None and self.reuse_policy(skill, context)
        )
        directive = self.reuse.attempt_reuse(
            [skill],
            current_inputs,
            current_state,
            current_scope=current_scope,
            mission_allowed_tools=mission_allowed_tools,
            validated_version=validated_version,
            verification_plan_executable=verification_plan_executable,
            policy_allows=policy_allows,
        )
        if isinstance(directive, EscalateToFrontierDirective):
            self._record_failure(skill, "applicability")
            return directive

        if self.local_workforce_service is not None:
            from datetime import datetime, timezone, timedelta
            from uuid import uuid4
            from aios.domain.local_workforce.contracts import (
                LocalJobProfile,
                LocalJobRequest,
            )

            job_req = LocalJobRequest(
                job_id=f"clerk-job-{uuid4().hex}",
                job_profile=LocalJobProfile.SELECT_SKILL,
                input_schema_version="1.0",
                evidence_references=frozenset({skill.skill_id}),
                redacted_payload=(
                    f"Evaluate local skill applicability for skill_id={skill.skill_id} version={skill.version}.\n"
                    f"Inputs: {current_inputs}\nState: {current_state}\n"
                    'Respond with strictly formatted JSON: {"applicable": true, "confidence": 0.9, "reason": "ok", "bounded_procedure_id": "proc-1", "required_inputs_present": true, "abstain": false, "escalation_reason": null}'
                ),
                token_budget=128,
                deadline=datetime.now(timezone.utc) + timedelta(seconds=10),
                required_output_schema={
                    "applicable": "bool",
                    "confidence": "float",
                    "reason": "str",
                },
            )

            clerk_res = self.local_workforce_service.run_advisory_job(job_req)
            # Blocker 8 fix: any unsuccessful advisory result ALWAYS escalates.
            # No special-case for "No admitted healthy local model" — that is also
            # a refusal that must escalate to the frontier; it must never fall
            # through to local mission creation.
            if clerk_res.status != "completed" or not clerk_res.structured_output:
                self._record_failure(skill, "clerk_advisory_refused")
                return EscalateToFrontierDirective(
                    reason=clerk_res.failure_reason or "Local clerk advisory failed"
                )
            parsed = clerk_res.structured_output
            if (
                not isinstance(parsed, dict)
                or not parsed.get("applicable")
                or parsed.get("abstain")
                or float(parsed.get("confidence", 0.0)) < 0.8
            ):
                reason = str(
                    parsed.get("escalation_reason")
                    or parsed.get("reason")
                    or "advisory evaluation declined local execution"
                )
                self._record_failure(skill, "clerk_advisory_refused")
                return EscalateToFrontierDirective(reason=reason)
        contract = MissionContract(
            mission_id=mission_id,
            project_id=project_id,
            operator_id=operator_id,
            goal=goal,
            worker_type="local-clerk",
            created_by="verified-skill-reuse",
            risk_level="YELLOW",
            requires_approval=True,
            allowed_files=[current_scope],
            allowed_tools=list(skill.allowed_tools),
            verification_plan=MissionVerificationPlan(
                required_strength="strong",
                verifiers=(skill.verification_plan,),
            ),
            metadata={
                "source": "verified_skill",
                "skill_id": skill.skill_id,
                "skill_version": skill.version,
                "validated_version": validated_version,
            },
        )
        created = self.mission_service.create(contract)
        return directive.model_copy(update={"mission_id": created.mission_id})

    def record_reuse_outcome(self, reference: ReuseOutcomeReference) -> SkillRecord:
        if not isinstance(reference, ReuseOutcomeReference):
            raise TypeError("reference must be a ReuseOutcomeReference")
        skill_id = reference.skill_id
        version = reference.skill_version
        mission_id = reference.mission_id
        skill = self.skill_repository.get(skill_id, version)
        if skill is None:
            raise KeyError(f"skill {skill_id!r} version {version} not found")
        if not self.reuse_outcome_repository.record(reference):
            return skill
        mission = self.mission_service.repository.get(mission_id)
        results = tuple(
            result
            for result in (
                self.verification_authority.get(verification_id)
                for verification_id in reference.verification_ids
            )
            if result is not None
        )

        # Lineage check across skill, mission, and promotion authority
        lineage_valid = True
        mandatory_values = (
            reference.reuse_outcome_id,
            reference.skill_id,
            str(reference.skill_version),
            reference.source_trajectory_id,
            reference.mission_id,
            reference.worker_id,
            reference.executor_job_id,
            reference.promotion_id,
            reference.local_job_id,
            reference.local_model_call_id,
            reference.workspace_digest,
            reference.diff_digest,
            reference.project_digest,
            reference.contract_digest,
            reference.policy_version,
        )
        if any(not value.strip() for value in mandatory_values):
            lineage_valid = False
        if not reference.verification_ids:
            lineage_valid = False
        if reference.source_trajectory_id not in skill.source_trajectory_ids:
            lineage_valid = False
        source_trajectory = self.trajectory_repository.get(reference.source_trajectory_id)
        if source_trajectory is None:
            lineage_valid = False

        if mission is None or mission.state is not MissionState.COMPLETED:
            lineage_valid = False
        elif mission.contract_digest != reference.contract_digest:
            lineage_valid = False

        if (
            mission
            and mission.contract.metadata.get("skill_id")
            and mission.contract.metadata.get("skill_id") != skill_id
        ):
            lineage_valid = False

        if mission is not None:
            metadata = mission.contract.metadata
            lineage_fields = {
                "worker_id": reference.worker_id,
                "executor_job_id": reference.executor_job_id,
                "promotion_id": reference.promotion_id,
                "local_job_id": reference.local_job_id,
                "local_model_call_id": reference.local_model_call_id,
                "source_trajectory_id": reference.source_trajectory_id,
            }
            for key, expected in lineage_fields.items():
                if metadata.get(key) and metadata.get(key) != expected:
                    lineage_valid = False

        if self.promotion_authority is not None:
            prom_record = self.promotion_authority.get_record(reference.promotion_id)
            term_record = self.promotion_authority.get_authoritative_terminal_record(
                mission_id
            )
            if prom_record is None:
                lineage_valid = False
            elif prom_record.get("status") not in (
                PromotionStatus.PROMOTED,
                PromotionStatus.PROMOTED.value,
            ):
                lineage_valid = False
            elif (
                term_record is not None
                and term_record.get("promotion_id") != reference.promotion_id
                and term_record.get("status")
                not in (PromotionStatus.PROMOTED, PromotionStatus.PROMOTED.value)
            ):
                lineage_valid = False
            elif prom_record.get("mission_id") != mission_id:
                lineage_valid = False
            elif prom_record.get("worker_id") != reference.worker_id:
                lineage_valid = False
            elif prom_record.get("executor_job_id") != reference.executor_job_id:
                lineage_valid = False
            elif prom_record.get("workspace_digest") != reference.workspace_digest:
                lineage_valid = False
            elif prom_record.get("diff_digest") != reference.diff_digest:
                lineage_valid = False

        passed = (
            lineage_valid
            and bool(results)
            and all(result.mission_id == mission_id for result in results)
            and tuple(result.verification_id for result in results)
            == reference.verification_ids
            and all(result.meets_requirement for result in results)
            and all(
                self.verification_authority.is_authoritative(result)
                for result in results
            )
            and all(
                self.verification_authority.is_current(
                    result,
                    workspace_digest=reference.workspace_digest,
                    diff_digest=reference.diff_digest,
                )
                for result in results
            )
        )
        if passed:
            updated_contract = self.confidence.record_success(skill)
        else:
            updated_contract = self.confidence.record_failure(skill, "verification")
            if updated_contract.confidence < self.applicability.minimum_confidence:
                updated_contract = updated_contract.model_copy(
                    update={"state": "degraded"}
                )
        updated = SkillRecord(
            **updated_contract.model_dump(
                mode="python", exclude={"created_at", "updated_at"}
            ),
            created_at=skill.created_at,
            updated_at=_utc_now(),
        )
        self.skill_repository.save(updated)
        return updated

    def _record_failure(self, skill: SkillRecord, reason: str) -> None:
        updated_contract = self.confidence.record_failure(skill, reason)  # type: ignore[arg-type]
        if updated_contract.confidence < self.applicability.minimum_confidence:
            updated_contract = updated_contract.model_copy(update={"state": "degraded"})
        self.skill_repository.save(
            SkillRecord(
                **updated_contract.model_dump(
                    mode="python", exclude={"created_at", "updated_at"}
                ),
                created_at=skill.created_at,
                updated_at=_utc_now(),
            )
        )


__all__ = ["LearningService", "SkillActivationDenied", "SkillCandidateSpec"]
