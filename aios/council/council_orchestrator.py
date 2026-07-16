"""Council Runtime orchestrator.

Drives one mission: Planner drafts, Security/Memory deliberate, a worker runs,
Testing verifies, and a King report is produced. Phase 3A optionally persists
every verdict and lifecycle event to a durable CouncilState store (best-effort).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios import config
from aios.council import queen_service as queen_service_registry
from aios.council.council_memory import CouncilMemory
from aios.council.council_state import CouncilState
from aios.council.ganglia import (
    GanglionSignal,
    SignalSynthesis,
    signals_from_verdicts,
    synthesize_signals,
)
from aios.council.king_reasoning import reason_king
from aios.council.reasoning import MistakeBackedRetriever
from aios.council.participation import CouncilParticipationPolicy
from aios.council.queen_verdict import (
    has_blocking_verdict,
    highest_risk,
    verdicts_as_metadata,
)
from aios.council.queens import (
    CouncilMissionRequest,
    CritiqueQueen,
    MemoryQueen,
    PlannerQueen,
    ProjectUnderstandingQueen,
    ReflectionQueen,
    RoutingQueen,
    SecurityQueen,
    TestingQueen,
)
from aios.application.evidence import EvidenceAuthority, VerificationAuthority
from aios.domain.missions.mission_contract import (
    MissionBudget,
    MissionContract as DomainMissionContract,
    VerificationPlan,
)
from aios.domain.evidence import VerificationObservation, VerificationPlanV1
from aios.domain.capabilities.digest import payload_digest
from aios.domain.missions.mission_repository import MissionTransitionError
from aios.domain.missions.mission_state import MissionState
from aios.application.missions.mission_service import MissionService
from aios.application.promotion import PromotionAuthority, WorkspacePromotionRuntime
from aios.domain.promotion import PromotionRequest, PromotionResult, PromotionStatus
from aios.application.workers.foundry import WorkerFoundry
from aios.application.workspaces import StagedWorkspaceManager
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.runtime.contracts import (
    KingReport,
    MissionContract,
    QueenVerdict,
    RunLedger,
    WorkerResult,
)
from aios.runtime.cortex_bus import CortexBus
from aios.runtime.king_report import (
    KingReportStore,
    build_deliberation_report,
    build_king_report,
)
from aios.runtime.run_ledger import RunLedgerStore
from aios.runtime.spawner import WorkerRun, WorkerSpawner, claim_mission
from aios.core.verification_strength import (
    VerificationStrength,
    parse_test_counts,
    strength_from_name,
)

_LOGGER = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ledger_strength(ledger: RunLedger) -> int:
    return int(
        strength_from_name(
            ledger.verification.get("strength"),
            VerificationStrength.NONE,
        )
    )


@dataclass(frozen=True)
class CouncilRun:
    """Complete result of one simulated Council mission."""

    contract: MissionContract
    verdicts: list[QueenVerdict]
    ledger: RunLedger
    report: KingReport
    worker_run: WorkerRun | None
    ledger_path: Path
    report_path: Path


class CouncilOrchestrator:
    """Permanent council wrapper around temporary worker execution."""

    def __init__(
        self,
        *,
        runtime_root: str | Path,
        spawner: WorkerSpawner | None = None,
        planner: PlannerQueen | None = None,
        security: SecurityQueen | None = None,
        memory: MemoryQueen | None = None,
        testing: TestingQueen | None = None,
        critique: CritiqueQueen | None = None,
        routing: RoutingQueen | None = None,
        reflection: ReflectionQueen | None = None,
        project_understanding: ProjectUnderstandingQueen | None = None,
        participation_policy: CouncilParticipationPolicy | None = None,
        use_queen_services: bool | None = None,
        king_complete: Callable[[str], str] | None = None,
        ledger_store: RunLedgerStore | None = None,
        report_store: KingReportStore | None = None,
        council_state: CouncilState | None = None,
        council_memory: CouncilMemory | None = None,
        pheromone_store: Any | None = None,
        bus: CortexBus | None = None,
        mission_service: MissionService | None = None,
        foundry: WorkerFoundry | None = None,
        workspace_manager: StagedWorkspaceManager | None = None,
        evidence_authority: EvidenceAuthority | None = None,
        verification_authority: VerificationAuthority | None = None,
        promotion_authority: PromotionAuthority | None = None,
        promotion_runtime: WorkspacePromotionRuntime | None = None,
        memory_authority: Any | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root).resolve()
        self.bus = bus
        self.spawner = spawner or WorkerSpawner(
            runtime_root=self.runtime_root, bus=self.bus
        )
        if workspace_manager is None and os.getenv(
            "AIOS_PROFILE", "development"
        ).strip().lower() in {
            "production",
            "demo",
        }:
            workspace_manager = StagedWorkspaceManager(
                config.EXECUTOR_WORKSPACE_ROOT,
                enrolled_roots=(config.COUNCIL_WORKSPACE_ROOT, *config.SCOPE_ROOTS),
            )
        self.workspace_manager = workspace_manager
        self.evidence_authority = evidence_authority or EvidenceAuthority()
        self.verification_authority = verification_authority or VerificationAuthority(
            self.evidence_authority
        )
        production_profile = os.getenv(
            "AIOS_PROFILE", "development"
        ).strip().lower() in {
            "production",
            "demo",
        }
        if (
            promotion_runtime is None
            and workspace_manager is not None
            and production_profile
        ):
            promotion_runtime = WorkspacePromotionRuntime(
                workspace_manager,
                self.runtime_root,
            )
        self.promotion_runtime = promotion_runtime
        if (
            promotion_authority is None
            and workspace_manager is not None
            and production_profile
        ):
            promotion_authority = PromotionAuthority(
                workspace_manager,
                verification=self.verification_authority,
            )
        self.promotion_authority = promotion_authority
        # Slice 9: all temporary worker styles enter through one bounded Foundry.
        # The deterministic strategy still delegates to the existing spawner so
        # its security, snapshot and evidence behavior remains unchanged.
        self.foundry = foundry or WorkerFoundry(
            runtime_root=self.runtime_root,
            spawner=self.spawner,
            bus=self.bus,
            workspace_manager=self.workspace_manager,
        )
        self.planner = planner or PlannerQueen()
        self.security = security or SecurityQueen()
        if memory is not None:
            self.memory = memory
        elif memory_authority is not None and config.COUNCIL_REASONING:
            self.memory = MemoryQueen(
                MistakeBackedRetriever(authority=memory_authority)
            )
        else:
            self.memory = MemoryQueen()
        self.testing = testing or TestingQueen()
        self.routing = routing or RoutingQueen()
        self.reflection = reflection or ReflectionQueen()
        self.project_understanding = (
            project_understanding or ProjectUnderstandingQueen()
        )
        # Opt-in (AIOS_COUNCIL_CRITIQUE): a second-order check on verification
        # sufficiency. None → the Queen is absent (no behavior change).
        self.critique = (
            critique
            if critique is not None
            else (CritiqueQueen() if config.COUNCIL_CRITIQUE else None)
        )
        self.participation_policy = participation_policy or CouncilParticipationPolicy()
        # Opt-in (AIOS_QUEEN_SERVICES): use long-lived async Queen services when
        # available. Registry is initialized lazily; callers still start/stop.
        self.use_queen_services = (
            use_queen_services
            if use_queen_services is not None
            else config.QUEEN_SERVICES
        )
        if self.use_queen_services:
            queen_service_registry.init_queen_services()
        # Opt-in (AIOS_COUNCIL_KING_REASONING): an injected LLM `complete` the King
        # uses to reason over the verdicts, clamped strengthen-only. None → off.
        self.king_complete = king_complete
        self.ledger_store = ledger_store or self.spawner.ledger_store
        self.report_store = report_store or self.spawner.report_store
        # Optional Phase-3A durable deliberation log. None → no persistence.
        self.council_state = council_state
        # Optional v10 deliberation memory. None → no persistence.
        self.council_memory = council_memory
        # Optional mission-scoped memory authority. The Council adapter is
        # bound to the same runtime-local CouncilMemory instance.
        self.memory_authority = memory_authority
        self.pheromone_store = pheromone_store
        if (
            self.pheromone_store is None
            and self.memory_authority is None
            and config.PHEROMONE_ENABLED
        ):
            raise RuntimeError(
                "MemoryAuthority is required when advisory pheromones are enabled"
            )
        # Authoritative mission state service (Slice 7). Defaults to an isolated
        # SQLite store under the runtime root so every orchestrator instance owns
        # its own mission authority unless one is injected.
        self.mission_service = mission_service or MissionService(
            SqliteMissionRepository(self.runtime_root / "missions.db"),
            export_dir=self.runtime_root / "mission_exports",
            workspace_manager=self.workspace_manager,
        )

    def _to_domain_contract(self, contract: MissionContract) -> DomainMissionContract:
        """Map a runtime v0.1 contract to the authoritative v1 domain contract."""
        return DomainMissionContract(
            mission_id=contract.mission_id,
            parent_mission_id=contract.parent_mission_id,
            turn_id=getattr(contract, "turn_id", None),
            project_id=getattr(contract, "project_id", None),
            operator_id=getattr(contract, "operator_id", None) or "system",
            goal=contract.goal,
            worker_type=contract.worker_type,
            created_by=contract.created_by,
            risk_level=contract.risk_level,
            requires_approval=contract.requires_approval,
            budget=MissionBudget(
                max_steps=contract.max_steps,
                timeout_seconds=contract.timeout_seconds,
            ),
            scope={"workspace_root": str(contract.workspace_root)},
            allowed_files=list(contract.allowed_files),
            forbidden_files=list(contract.forbidden_files),
            allowed_tools=list(contract.allowed_tools),
            forbidden_tools=list(contract.forbidden_tools),
            verification_plan=VerificationPlan(
                commands=list(contract.verification_commands),
            ),
            workspace_root=str(contract.workspace_root),
            snapshot_id=contract.snapshot_id,
            metadata=dict(contract.metadata),
        )

    async def run(self, request: CouncilMissionRequest | MissionContract) -> CouncilRun:
        """Deliberate a mission and return its proposal for human approval.

        A programmatic one-shot caller must not become an approval authority.
        Execution is a separate phase entered only after the authoritative
        mission repository records an authenticated Human Sovereign approval.
        """
        deliberation = self.deliberate(request)
        if has_blocking_verdict(deliberation.verdicts):
            return deliberation
        return deliberation

    def deliberate(
        self, request: CouncilMissionRequest | MissionContract
    ) -> CouncilRun:
        """Phase 1 (sync): Queens deliberate; NO worker spawns. Produces a King
        report with status ``awaiting_approval`` (passed) or ``blocked`` (denied).
        Claims the mission dir so a later execute() need not re-claim."""
        deliberation_start = time.perf_counter()
        draft = self.planner.draft(request)
        contract = self._apply_pheromone_context(draft.contract)
        verdicts = [draft.verdict]
        # Claim once, here — covers both the blocked and awaiting-approval paths
        # (and the later execute() phase, which spawns with claim=False).
        claim_mission(self.runtime_root, contract.mission_id)
        self._persist_verdict(contract.mission_id, draft.verdict)

        participation = self.participation_policy.decide(
            contract, prior_verdicts=verdicts
        )

        # Required deliberation queens. Testing and critique are execute-phase.
        execute_phase = {"testing", "critique"}
        for queen_name in participation.required:
            if queen_name == "planner":
                continue  # draft verdict already collected
            if queen_name in execute_phase:
                continue
            verdict = self._review_queen_sync(queen_name, contract)
            verdicts.append(verdict)
            self._persist_verdict(contract.mission_id, verdict)

        # Optional deliberation queens. Critique and testing are execute-phase.
        for queen_name in participation.optional:
            if queen_name in execute_phase:
                continue
            verdict = self._review_queen_sync(queen_name, contract)
            verdicts.append(verdict)
            self._persist_verdict(contract.mission_id, verdict)

        contract = self._apply_council_context(contract, verdicts)
        signals, synthesis = self._ganglia_for(verdicts)
        contract = self._apply_ganglia_context(contract, signals, synthesis)
        self._persist_council_memory(
            contract.mission_id,
            verdicts=verdicts,
            signals=signals,
            synthesis=synthesis,
        )
        # Slice 7: persist the final, fully contextualized runtime contract as
        # the authoritative mission proposal before any terminal or approval
        # transition is recorded.  The JSON ledger remains a projection.
        domain_contract = self._to_domain_contract(contract)
        self.mission_service.create(
            domain_contract,
            runtime_contract_digest=payload_digest(contract.model_dump(mode="json")),
        )
        self.mission_service.start_deliberation(contract.mission_id)
        if has_blocking_verdict(verdicts):
            self.mission_service.block(
                contract.mission_id,
                reason=highest_risk([v.risk for v in verdicts]),
            )
            self.mission_service.export(contract.mission_id)
            return self._blocked_run(contract=contract, verdicts=verdicts)

        self.mission_service.request_approval(contract.mission_id)
        export_path = self.mission_service.export(contract.mission_id)

        now = _utc_now()
        risk = highest_risk([contract.risk_level, *(v.risk for v in verdicts)])
        evidence = self._council_evidence(contract, verdicts)
        evidence["mission_state_authority"] = "sqlite_mission_repository"
        evidence["mission_state_export_path"] = str(export_path)
        evidence["council_participation"] = {
            "required": list(participation.required),
            "optional": list(participation.optional),
            "reason": participation.reason,
        }
        elapsed_ms = int((time.perf_counter() - deliberation_start) * 1000)
        evidence["council_metrics"] = {
            "latency_ms": elapsed_ms,
            "cost_usd": 0.0,
        }
        ledger = RunLedger(
            mission_id=contract.mission_id,
            mission=contract.goal,
            risk_before=contract.risk_level,
            risk_after=risk,
            contract=contract,
            workers_created=[],
            files_allowed=list(contract.allowed_files),
            council_verdicts=verdicts,
            status="awaiting_approval",
            created_at=now,
            completed_at=None,
            evidence=evidence,
        )
        ledger_path = self.ledger_store.write(ledger)
        report = build_deliberation_report(contract=contract, verdicts=verdicts)
        report_path = self.report_store.write(report)
        self._persist_event(contract.mission_id, "deliberated", risk=report.risk)
        return CouncilRun(
            contract=contract,
            verdicts=verdicts,
            ledger=ledger,
            report=report,
            worker_run=None,
            ledger_path=ledger_path,
            report_path=report_path,
        )

    async def execute(
        self,
        contract: MissionContract,
        verdicts: list[QueenVerdict],
    ) -> CouncilRun:
        """Phase 2 (async): the worker acts (post-approval). The mission dir was
        already claimed by deliberate(), so the spawner runs with claim=False."""
        execute_start = time.perf_counter()
        mission_record = self.mission_service.repository.get(contract.mission_id)
        if mission_record.state is not MissionState.APPROVED:
            raise MissionTransitionError(
                "human approval is required before mission execution"
            )
        if (
            mission_record.runtime_contract_digest
            and mission_record.runtime_contract_digest
            != payload_digest(contract.model_dump(mode="json"))
        ):
            raise MissionTransitionError(
                "runtime contract digest does not match authoritative mission"
            )
        self.mission_service.start_execution(contract.mission_id)
        worker_run = await self.foundry.run(
            contract,
            strategy=contract.metadata.get("worker_strategy"),
            context={"claim": False},
        )
        self._persist_event(
            contract.mission_id,
            "worker_spawned",
            snapshot_id=worker_run.contract.snapshot_id,
        )
        testing_verdict = self.testing.verify(
            contract=worker_run.contract,
            ledger=worker_run.ledger,
        )
        verdicts = [*verdicts, testing_verdict]
        self._persist_verdict(contract.mission_id, testing_verdict)

        # Deeper cognition (opt-in): the Critique Queen scrutinizes whether the
        # PASSING verification was actually sufficient (strong + exercised the
        # change). Strengthen-only — it can only add caution, never relax a block.
        # Gated by participation policy so critique runs only when justified.
        critique_participation = self.participation_policy.decide(
            worker_run.contract, prior_verdicts=verdicts
        )
        if self.critique is not None and "critique" in critique_participation.optional:
            critique_verdict = self.critique.review(
                contract=worker_run.contract, testing_verdict=testing_verdict
            )
            verdicts = [*verdicts, critique_verdict]
            self._persist_verdict(contract.mission_id, critique_verdict)

        execute_latency_ms = int((time.perf_counter() - execute_start) * 1000)

        promotion_result: PromotionResult | None = None
        promotion_bundle_digest: str | None = None
        if has_blocking_verdict(verdicts):
            self.mission_service.start_verification(contract.mission_id)
            self.mission_service.fail(
                contract.mission_id,
                reason=f"Council blocked after worker; highest risk {highest_risk([v.risk for v in verdicts])}",
                retain_workspace=True,
            )
        elif self.promotion_authority is not None:
            self.mission_service.start_verification(contract.mission_id)
            try:
                promotion_result, promotion_bundle_digest = self._promote_worker(
                    contract=contract,
                    worker_run=worker_run,
                )
            except Exception as exc:  # noqa: BLE001 - promotion fails closed
                _LOGGER.warning(
                    "council_promotion_failed_closed",
                    mission_id=contract.mission_id,
                    exc_info=exc,
                )
                self.mission_service.fail(
                    contract.mission_id,
                    reason=f"Promotion pipeline failed closed: {type(exc).__name__}",
                    retain_workspace=True,
                )
                promotion_result = PromotionResult(
                    mission_id=contract.mission_id,
                    action_id=f"promotion:{contract.mission_id}",
                    status=PromotionStatus.FAILED,
                    reason_codes=("promotion_pipeline_exception", type(exc).__name__),
                )
            else:
                if promotion_result.status is PromotionStatus.PROMOTED:
                    self.mission_service.complete(
                        contract.mission_id,
                        evidence_digest=promotion_bundle_digest,
                    )
                else:
                    self.mission_service.fail(
                        contract.mission_id,
                        reason=(
                            "Promotion refused: "
                            + ",".join(promotion_result.reason_codes)
                        ),
                        retain_workspace=True,
                    )
        else:
            self.mission_service.start_verification(contract.mission_id)
            self.mission_service.complete(contract.mission_id)

        signals, synthesis = self._ganglia_for(verdicts)
        contract_with_ganglia = self._apply_ganglia_context(
            worker_run.contract,
            signals,
            synthesis,
        )
        self._persist_council_memory(
            contract_with_ganglia.mission_id,
            verdicts=verdicts,
            signals=signals,
            synthesis=synthesis,
        )
        extra_evidence: dict[str, object] = {
            "council_metrics": {
                "execute_latency_ms": execute_latency_ms,
                "cost_usd": 0.0,
            },
        }
        if promotion_result is not None:
            extra_evidence["promotion"] = promotion_result.model_dump(mode="json")
            if promotion_bundle_digest is not None:
                extra_evidence["evidence_bundle_digest"] = promotion_bundle_digest
        ledger = self._enrich_worker_ledger(
            worker_run=worker_run,
            verdicts=verdicts,
            contract=contract_with_ganglia,
            extra_evidence=extra_evidence,
            status_override=(
                worker_run.ledger.status
                if promotion_result is None
                else (
                    "completed"
                    if promotion_result.status is PromotionStatus.PROMOTED
                    else "failed"
                )
            ),
        )
        ledger_path = self.ledger_store.write(ledger)
        report = build_king_report(ledger=ledger, result=worker_run.result)
        # Deeper cognition (opt-in): the Reasoning King enriches the recommendation +
        # rationale, CLAMPED strengthen-only (never overrides a block; fail-closed).
        if config.COUNCIL_KING_REASONING and self.king_complete is not None:
            report = reason_king(
                report,
                contract=contract_with_ganglia,
                verdicts=verdicts,
                complete=self.king_complete,
            )
        report_path = self.report_store.write(report)
        self.mission_service.export(contract.mission_id)
        self._persist_event(
            contract.mission_id,
            "report",
            risk=report.risk,
            snapshot_id=worker_run.contract.snapshot_id,
        )
        return CouncilRun(
            contract=contract_with_ganglia,
            verdicts=verdicts,
            ledger=ledger,
            report=report,
            worker_run=worker_run,
            ledger_path=ledger_path,
            report_path=report_path,
        )

    def _promote_worker(
        self,
        *,
        contract: MissionContract,
        worker_run: WorkerRun,
    ) -> tuple[PromotionResult, str]:
        if self.workspace_manager is None or self.promotion_authority is None:
            raise RuntimeError("promotion authority is not configured")
        if self.promotion_runtime is None:
            raise RuntimeError("promotion runtime adapters are not configured")
        lease = self.workspace_manager.for_mission(contract.mission_id)
        if lease is None:
            raise RuntimeError("worker completed without a durable staged lease")
        diff = self.workspace_manager.diff(lease)
        workspace_digest = str(diff["workspace_digest"])
        diff_digest = str(diff["diff_digest"])
        contract_digest = payload_digest(contract.model_dump(mode="json"))
        environment_digest = payload_digest(
            {
                "backend": worker_run.handle.backend,
                "executor_policy": worker_run.contract.metadata.get(
                    "executor_policy", "default"
                ),
                "profile": os.getenv("AIOS_PROFILE", "development"),
            }
        )
        commands = worker_run.ledger.verification.get("commands", [])
        if not isinstance(commands, list):
            commands = []
        targets = tuple(worker_run.result.files_touched or contract.allowed_files)
        bundle = self.evidence_authority.bundle(
            mission_id=contract.mission_id,
            worker_id=worker_run.handle.worker_id,
            contract_digest=contract_digest,
            workspace_digest=workspace_digest,
            diff_digest=diff_digest,
            executor_job_id=worker_run.handle.worker_id,
            environment_digest=environment_digest,
            commands=commands,
            verification_strength=_ledger_strength(worker_run.ledger),
            targets_exercised=targets,
            started_at=worker_run.result.started_at,
            ended_at=worker_run.result.ended_at,
        )
        verification_results = []
        for entry in commands:
            if not isinstance(entry, dict):
                continue
            raw_command = entry.get("command", "")
            command = (
                raw_command
                if isinstance(raw_command, str)
                else " ".join(str(part) for part in raw_command)
            )
            passed_count, failed_count = parse_test_counts(
                str(entry.get("stdout") or "") + str(entry.get("stderr") or "")
            )
            observation = VerificationObservation(
                command=command,
                exit_code=entry.get("returncode"),
                stdout=str(entry.get("stdout") or ""),
                stderr=str(entry.get("stderr") or ""),
                passed_count=passed_count,
                failed_count=failed_count,
                tool_version=str(entry.get("tool_version") or "worker-executor"),
                observed_at=worker_run.result.ended_at,
            )
            for target in targets:
                verification_results.append(
                    self.verification_authority.verify(
                        mission_id=contract.mission_id,
                        action_id=f"promotion:{contract.mission_id}",
                        worker_id=worker_run.handle.worker_id,
                        target=target,
                        plan=VerificationPlanV1(
                            intended_behavior=contract.goal,
                            targets=(target,),
                            required_tests=(command,),
                            minimum_strength=int(VerificationStrength.STRONG),
                        ),
                        workspace_digest=workspace_digest,
                        diff_digest=diff_digest,
                        environment_digest=environment_digest,
                        observation=observation,
                    )
                )
        record = self.mission_service.repository.get(contract.mission_id)
        request = PromotionRequest(
            mission_id=contract.mission_id,
            action_id=f"promotion:{contract.mission_id}",
            worker_id=worker_run.handle.worker_id,
            executor_job_id=worker_run.handle.worker_id,
            environment_digest=environment_digest,
            project_root=lease.project_root,
            lease=lease,
            current_state=MissionState.VERIFYING,
            contract_digest=contract_digest,
            authoritative_contract_digest=record.runtime_contract_digest
            or contract_digest,
            policy_version=record.policy_version,
            authoritative_policy_version=record.policy_version,
            workspace_digest=workspace_digest,
            diff_digest=diff_digest,
            verification_results=tuple(verification_results),
            evidence_bundle=bundle,
            required_targets=targets,
            required_strength=int(VerificationStrength.STRONG),
            freshness_seconds=300,
        )
        result = self.promotion_authority.promote(
            request,
            create_checkpoint=self.promotion_runtime.create_checkpoint,
            apply_staged_diff=self.promotion_runtime.apply_staged_diff,
            smoke_test=self.promotion_runtime.post_promotion_smoke,
            restore_checkpoint=self.promotion_runtime.restore_checkpoint,
            emit_observation=lambda req, promotion: self._persist_event(
                req.mission_id,
                "promotion",
                payload=promotion.model_dump(mode="json"),
            ),
        )
        return result, bundle.digest()

    def _apply_pheromone_context(self, contract: MissionContract) -> MissionContract:
        """Attach decayed pheromone hints as non-authoritative contract context."""
        if not config.PHEROMONE_ENABLED:
            return contract
        if not contract.allowed_files:
            return contract
        if self.memory_authority is None and self.pheromone_store is None:
            return contract
        try:
            if self.memory_authority is not None:
                contexts = self.memory_authority.pheromone_for_contract(
                    list(contract.allowed_files)
                )
                context_source = "MemoryAuthority.pheromone_for_contract"
            else:
                contexts = self.pheromone_store.for_contract(
                    list(contract.allowed_files)
                )
                context_source = "PheromoneStore.for_contract"
        except Exception as exc:  # noqa: BLE001 - pheromones may suggest, never block
            _LOGGER.warning("pheromone_context_unavailable", exc_info=exc)
            return contract
        if not contexts:
            return contract
        combined: list[str] = []
        for item in [*contract.pheromone_context, *contexts]:
            if item and item not in combined:
                combined.append(item)
        metadata = dict(contract.metadata)
        metadata["pheromone_context_count"] = len(contexts)
        metadata["pheromone_context_non_authoritative"] = True
        metadata["pheromone_context_source"] = context_source
        return contract.model_copy(
            update={"pheromone_context": combined[:20], "metadata": metadata}
        )

    def _apply_council_context(
        self,
        contract: MissionContract,
        verdicts: list[QueenVerdict],
    ) -> MissionContract:
        metadata = dict(contract.metadata)
        metadata["council_verdicts"] = verdicts_as_metadata(verdicts)
        constraints = [
            constraint for verdict in verdicts for constraint in verdict.constraints
        ]
        if constraints:
            metadata["council_constraints"] = constraints
        return contract.model_copy(update={"metadata": metadata})

    def _ganglia_for(
        self,
        verdicts: list[QueenVerdict],
    ) -> tuple[list[GanglionSignal], SignalSynthesis]:
        signals = signals_from_verdicts(verdicts)
        return signals, synthesize_signals(signals)

    def _apply_ganglia_context(
        self,
        contract: MissionContract,
        signals: list[GanglionSignal],
        synthesis: SignalSynthesis,
    ) -> MissionContract:
        metadata = dict(contract.metadata)
        metadata["ganglia_signals"] = [signal.model_dump() for signal in signals]
        metadata["ganglia_synthesis"] = synthesis.model_dump()
        metadata["ganglia_authority"] = "proposal/evidence"
        return contract.model_copy(update={"metadata": metadata})

    def _review_queen_sync(self, name: str, contract: MissionContract) -> QueenVerdict:
        """Invoke a Queen by name, using the service registry when enabled."""
        if self.use_queen_services:
            svc = queen_service_registry.QUEEN_SERVICES.get(name)
            if svc is not None:
                return self._run_service_review_sync(svc, contract)
        queen = self._queen_instance(name)
        return queen.review(contract)

    def _queen_instance(self, name: str) -> Any:
        """Return the local Queen instance for *name*."""
        mapping: dict[str, Any] = {
            "planner": self.planner,
            "security": self.security,
            "memory": self.memory,
            "testing": self.testing,
            "critique": self.critique,
            "routing": self.routing,
            "reflection": self.reflection,
            "project_understanding": self.project_understanding,
        }
        queen = mapping.get(name)
        if queen is None:
            raise ValueError(f"unknown queen: {name}")
        return queen

    def _run_service_review_sync(
        self, svc: queen_service_registry.QueenService, contract: MissionContract
    ) -> QueenVerdict:
        """Run one async Queen service review from a synchronous context."""

        async def _start_and_submit() -> QueenVerdict:
            await svc.start()
            return await svc.submit(contract)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_start_and_submit())
        # If we are already inside an event loop, schedule on it without blocking.
        future = asyncio.run_coroutine_threadsafe(_start_and_submit(), loop)
        return future.result()

    def _council_evidence(
        self,
        contract: MissionContract,
        verdicts: list[QueenVerdict],
    ) -> dict[str, object]:
        evidence: dict[str, object] = {"council": verdicts_as_metadata(verdicts)}
        if isinstance(contract.metadata.get("ganglia_signals"), list):
            evidence["ganglia_signals"] = contract.metadata["ganglia_signals"]
        if isinstance(contract.metadata.get("ganglia_synthesis"), dict):
            evidence["ganglia_synthesis"] = contract.metadata["ganglia_synthesis"]
        return evidence

    def _blocked_run(
        self,
        *,
        contract: MissionContract,
        verdicts: list[QueenVerdict],
    ) -> CouncilRun:
        now = _utc_now()
        # Mission already claimed by deliberate() before this is reached.
        risk = highest_risk(
            [contract.risk_level, *(verdict.risk for verdict in verdicts)]
        )
        result = WorkerResult(
            mission_id=contract.mission_id,
            worker_id="council-preflight",
            status="blocked",
            summary="Council blocked worker spawn before execution.",
            risk_after=risk,
            council_verdicts_applied=verdicts_as_metadata(verdicts),
            started_at=now,
            ended_at=now,
        )
        ledger = RunLedger(
            mission_id=contract.mission_id,
            mission=contract.goal,
            risk_before=contract.risk_level,
            risk_after=risk,
            contract=contract,
            workers_created=[],
            files_allowed=list(contract.allowed_files),
            council_verdicts=verdicts,
            status="blocked",
            created_at=now,
            completed_at=now,
            evidence=self._council_evidence(contract, verdicts),
        )
        ledger_path = self.ledger_store.write(ledger)
        report = build_king_report(ledger=ledger, result=result)
        report_path = self.report_store.write(report)
        self._persist_event(contract.mission_id, "blocked", risk=report.risk)
        return CouncilRun(
            contract=contract,
            verdicts=verdicts,
            ledger=ledger,
            report=report,
            worker_run=None,
            ledger_path=ledger_path,
            report_path=report_path,
        )

    def _persist_verdict(self, mission_id: str, verdict: QueenVerdict) -> None:
        """Best-effort durable verdict log; never fatal to deliberation."""
        if self.council_state is None:
            return
        try:
            self.council_state.record_verdict(mission_id, verdict)
        except Exception as exc:  # noqa: BLE001 - persistence is additive, not authority
            _LOGGER.warning("council_state_verdict_failed", exc_info=exc)

    def _persist_event(
        self,
        mission_id: str,
        event_type: str,
        *,
        risk: str | None = None,
        snapshot_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        """Best-effort durable lifecycle event; never fatal to deliberation."""
        if self.council_state is None:
            return
        try:
            self.council_state.record_event(
                mission_id,
                event_type=event_type,
                payload=payload,
                risk=risk,
                snapshot_id=snapshot_id,
            )
        except Exception as exc:  # noqa: BLE001 - persistence is additive, not authority
            _LOGGER.warning("council_state_event_failed", exc_info=exc)

    def _persist_council_memory(
        self,
        mission_id: str,
        *,
        verdicts: list[QueenVerdict],
        signals: list[GanglionSignal],
        synthesis: SignalSynthesis,
    ) -> None:
        """Best-effort v10 deliberation memory; never fatal or authoritative."""
        if self.council_memory is None:
            return
        try:
            recorder = getattr(
                self.memory_authority, "record_council_deliberation", None
            )
            adapters = getattr(self.memory_authority, "adapters", {})
            if (
                callable(recorder)
                and isinstance(adapters, dict)
                and "council" in adapters
            ):
                recorder(
                    mission_id=mission_id,
                    verdicts=verdicts,
                    signals=signals,
                    synthesis=synthesis,
                )
                return
            self.council_memory.record_deliberation(
                mission_id=mission_id,
                verdicts=verdicts,
                signals=signals,
                synthesis=synthesis,
            )
        except Exception as exc:  # noqa: BLE001 - memory may suggest, never block
            _LOGGER.warning("council_memory_record_failed", exc_info=exc)

    def _enrich_worker_ledger(
        self,
        *,
        worker_run: WorkerRun,
        verdicts: list[QueenVerdict],
        contract: MissionContract | None = None,
        extra_evidence: dict[str, object] | None = None,
        status_override: str | None = None,
    ) -> RunLedger:
        contract = contract or worker_run.contract
        risk = highest_risk(
            [worker_run.ledger.risk_after, *(verdict.risk for verdict in verdicts)]
        )
        status = worker_run.ledger.status
        if has_blocking_verdict(verdicts):
            status = "failed"
        if status_override is not None:
            status = status_override
        evidence = dict(worker_run.ledger.evidence)
        evidence.update(self._council_evidence(contract, verdicts))
        evidence["mission_state_authority"] = "sqlite_mission_repository"
        if extra_evidence:
            evidence.update(extra_evidence)
        return worker_run.ledger.model_copy(
            update={
                "contract": contract,
                "risk_after": risk,
                "status": status,
                "council_verdicts": verdicts,
                "evidence": evidence,
            }
        )


__all__ = ["CouncilOrchestrator", "CouncilRun"]
