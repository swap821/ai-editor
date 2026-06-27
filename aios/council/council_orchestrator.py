"""Simulated Council Runtime orchestrator for Phase 2."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aios.council.queen_verdict import (
    has_blocking_verdict,
    highest_risk,
    verdicts_as_metadata,
)
from aios.council.queens.memory import MemoryQueen
from aios.council.queens.planner import CouncilMissionRequest, PlannerQueen
from aios.council.queens.security import SecurityQueen
from aios.council.queens.testing import TestingQueen
from aios.runtime.contracts import (
    KingReport,
    MissionContract,
    QueenVerdict,
    RunLedger,
    WorkerResult,
)
from aios.runtime.king_report import KingReportStore, build_king_report
from aios.runtime.run_ledger import RunLedgerStore
from aios.runtime.spawner import WorkerRun, WorkerSpawner, claim_mission


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
        ledger_store: RunLedgerStore | None = None,
        report_store: KingReportStore | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root).resolve()
        self.spawner = spawner or WorkerSpawner(runtime_root=self.runtime_root)
        self.planner = planner or PlannerQueen()
        self.security = security or SecurityQueen()
        self.memory = memory or MemoryQueen()
        self.testing = testing or TestingQueen()
        self.ledger_store = ledger_store or self.spawner.ledger_store
        self.report_store = report_store or self.spawner.report_store

    async def run(self, request: CouncilMissionRequest | MissionContract) -> CouncilRun:
        draft = self.planner.draft(request)
        contract = draft.contract
        verdicts = [draft.verdict]

        security_verdict = self.security.review(contract)
        verdicts.append(security_verdict)

        memory_verdict = self.memory.review(contract)
        verdicts.append(memory_verdict)

        contract = self._apply_council_context(contract, verdicts)
        if has_blocking_verdict(verdicts):
            return self._blocked_run(contract=contract, verdicts=verdicts)

        worker_run = await self.spawner.run(contract)
        testing_verdict = self.testing.verify(
            contract=worker_run.contract,
            ledger=worker_run.ledger,
        )
        verdicts.append(testing_verdict)

        ledger = self._enrich_worker_ledger(worker_run=worker_run, verdicts=verdicts)
        ledger_path = self.ledger_store.write(ledger)
        report = build_king_report(ledger=ledger, result=worker_run.result)
        report_path = self.report_store.write(report)
        return CouncilRun(
            contract=worker_run.contract,
            verdicts=verdicts,
            ledger=ledger,
            report=report,
            worker_run=worker_run,
            ledger_path=ledger_path,
            report_path=report_path,
        )

    def _apply_council_context(
        self,
        contract: MissionContract,
        verdicts: list[QueenVerdict],
    ) -> MissionContract:
        metadata = dict(contract.metadata)
        metadata["council_verdicts"] = verdicts_as_metadata(verdicts)
        constraints = [
            constraint
            for verdict in verdicts
            for constraint in verdict.constraints
        ]
        if constraints:
            metadata["council_constraints"] = constraints
        return contract.model_copy(update={"metadata": metadata})

    def _blocked_run(
        self,
        *,
        contract: MissionContract,
        verdicts: list[QueenVerdict],
    ) -> CouncilRun:
        now = _utc_now()
        # The blocked path never reaches spawner.run (which would claim the
        # mission), so claim here to keep the same fail-closed collision guard.
        claim_mission(self.runtime_root, contract.mission_id)
        risk = highest_risk([contract.risk_level, *(verdict.risk for verdict in verdicts)])
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
            evidence={"council": verdicts_as_metadata(verdicts)},
        )
        ledger_path = self.ledger_store.write(ledger)
        report = build_king_report(ledger=ledger, result=result)
        report_path = self.report_store.write(report)
        return CouncilRun(
            contract=contract,
            verdicts=verdicts,
            ledger=ledger,
            report=report,
            worker_run=None,
            ledger_path=ledger_path,
            report_path=report_path,
        )

    def _enrich_worker_ledger(
        self,
        *,
        worker_run: WorkerRun,
        verdicts: list[QueenVerdict],
    ) -> RunLedger:
        risk = highest_risk(
            [worker_run.ledger.risk_after, *(verdict.risk for verdict in verdicts)]
        )
        status = worker_run.ledger.status
        if has_blocking_verdict(verdicts):
            status = "failed"
        evidence = dict(worker_run.ledger.evidence)
        evidence["council"] = verdicts_as_metadata(verdicts)
        return worker_run.ledger.model_copy(
            update={
                "risk_after": risk,
                "status": status,
                "council_verdicts": verdicts,
                "evidence": evidence,
            }
        )


__all__ = ["CouncilOrchestrator", "CouncilRun"]
