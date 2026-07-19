"""Canonical R15 trajectory capture, skill activation and reuse flow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from aios.application.evidence.verification import VerificationAuthority
from aios.application.missions.mission_service import MissionService
from aios.domain.evidence import VerificationPlanV1, VerificationResult
from aios.domain.verification import SkillVerifierSpec
from aios.domain.learning.applicability import SkillApplicabilityEngine
from aios.domain.learning.confidence import ConfidenceUpdater
from aios.domain.learning.contracts import (
    ExpertTrajectory,
    ToolObservation,
    TrajectoryVerification,
)
from aios.domain.learning.repository import SkillRecord, SkillRepository
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


class LearningService:
    """Use existing mission, verification and durable-memory authorities."""

    def __init__(
        self,
        *,
        mission_service: MissionService,
        trajectory_repository: TrajectoryRepository,
        skill_repository: SkillRepository | None = None,
        activation_authorizer: Callable[[SkillRecord, str, str], bool] | None = None,
        verification_plan_validator: Callable[[SkillRecord], bool] | None = None,
        reuse_policy: Callable[[SkillRecord, Mapping[str, object]], bool] | None = None,
        verification_authority: VerificationAuthority | None = None,
        promotion_authority: PromotionAuthority | None = None,
        local_workforce_service: Any | None = None,
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
        if self.promotion_authority is not None and not self.promotion_authority.is_authoritative(promotion):
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
        skill_id: str,
        version: int,
        *,
        operator_id: str,
        approval_digest: str,
    ) -> SkillRecord:
        skill = self.skill_repository.get(skill_id, version)
        if skill is None:
            raise KeyError(f"skill {skill_id!r} version {version} not found")
        if self.activation_authorizer is None:
            raise SkillActivationDenied("external authority refused skill activation: CapabilityAuthority authorizer required")
        if not self.activation_authorizer(skill, operator_id, approval_digest):
            raise SkillActivationDenied("external authority refused skill activation")
        reviewed = self.skill_repository.transition_state(
            skill_id, version, "human_reviewed"
        )
        if reviewed.state != "human_reviewed":
            raise SkillActivationDenied("skill review transition failed")
        return self.skill_repository.transition_state(skill_id, version, "active")

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
            models = self.local_workforce_service.registry.list_models()
            admitted = [
                m
                for m in models
                if getattr(m, "admission_status", None) == "approved"
                and getattr(m, "health_status", None) == "healthy"
                and getattr(m, "operator_approved", False)
            ]
            if not admitted:
                self._record_failure(skill, "no_admitted_local_clerk")
                return EscalateToFrontierDirective(
                    reason="No admitted healthy local clerk model available in Local Workforce"
                )
            clerk_model = admitted[0]
            try:
                client = self.local_workforce_service.model_client_factory(clerk_model.model_id)
                prompt = (
                    f"Evaluate local skill applicability for skill_id={skill.skill_id} version={skill.version}.\n"
                    f"Inputs: {current_inputs}\nState: {current_state}\n"
                    'Respond with strictly formatted JSON: {"applicable": true, "confidence": 0.9, "reason": "ok", "bounded_procedure_id": "proc-1", "required_inputs_present": true, "abstain": false, "escalation_reason": null}'
                )
                raw_resp = client.complete(prompt, system="Advisory clerk evaluation. Output JSON only.")
                import json
                parsed = json.loads(raw_resp)
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
            except Exception as exc:  # noqa: BLE001 - clerk failure escalates to frontier
                self._record_failure(skill, f"clerk_advisory_error: {exc}")
                return EscalateToFrontierDirective(reason=f"Local clerk advisory failed: {exc}")
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

    def record_reuse_outcome(
        self,
        *,
        skill_id: str,
        version: int,
        mission_id: str,
        verification_results: Sequence[VerificationResult],
        workspace_digest: str,
        diff_digest: str,
        worker_id: str | None = None,
        executor_job_id: str | None = None,
        promotion_id: str | None = None,
        source_trajectory_id: str | None = None,
        local_model_call_id: str | None = None,
    ) -> SkillRecord:
        skill = self.skill_repository.get(skill_id, version)
        if skill is None:
            raise KeyError(f"skill {skill_id!r} version {version} not found")
        mission = self.mission_service.repository.get(mission_id)
        results = tuple(verification_results)

        # Check lineage equality across skill, trajectory, mission, worker, executor, promotion, verification
        lineage_valid = True
        if source_trajectory_id and source_trajectory_id not in skill.source_trajectory_ids:
            lineage_valid = False

        if mission.contract.metadata.get("skill_id") and mission.contract.metadata.get("skill_id") != skill_id:
            lineage_valid = False

        held_promotion = (
            self.promotion_authority.get_promotion(mission_id)
            if self.promotion_authority is not None
            else None
        )

        if self.promotion_authority is not None:
            if held_promotion is None or held_promotion.status is not PromotionStatus.PROMOTED:
                lineage_valid = False
            elif promotion_id and getattr(held_promotion, "promotion_id", None) and getattr(held_promotion, "promotion_id") != promotion_id:
                lineage_valid = False

        if worker_id and held_promotion and getattr(held_promotion, "worker_id", None) and getattr(held_promotion, "worker_id") != worker_id:
            lineage_valid = False

        if executor_job_id and held_promotion and getattr(held_promotion, "executor_job_id", None) and getattr(held_promotion, "executor_job_id") != executor_job_id:
            lineage_valid = False

        passed = (
            lineage_valid
            and mission.state is MissionState.COMPLETED
            and bool(results)
            and all(result.mission_id == mission_id for result in results)
            and all(result.meets_requirement for result in results)
            and all(
                self.verification_authority.is_authoritative(result)
                for result in results
            )
            and all(
                self.verification_authority.is_current(
                    result,
                    workspace_digest=workspace_digest,
                    diff_digest=diff_digest,
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
