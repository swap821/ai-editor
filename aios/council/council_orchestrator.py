"""Council Runtime orchestrator.

Drives one mission: Planner drafts, Security/Memory deliberate, a worker runs,
Testing verifies, and a King report is produced. Phase 3A optionally persists
every verdict and lifecycle event to a durable CouncilState store (best-effort).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aios.council.council_state import CouncilState
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

_LOGGER = logging.getLogger(__name__)


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
        council_state: CouncilState | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root).resolve()
        self.spawner = spawner or WorkerSpawner(runtime_root=self.runtime_root)
        self.planner = planner or PlannerQueen()
        self.security = security or SecurityQueen()
        self.memory = memory or MemoryQueen()
        self.testing = testing or TestingQueen()
        self.ledger_store = ledger_store or self.spawner.ledger_store
        self.report_store = report_store or self.spawner.report_store
        # Optional Phase-3A durable deliberation log. None → no persistence.
        self.council_state = council_state

    async def run(self, request: CouncilMissionRequest | MissionContract) -> CouncilRun:
        draft = self.planner.draft(request)
        contract = draft.contract
        verdicts = [draft.verdict]
        self._persist_verdict(contract.mission_id, draft.verdict)

        security_verdict = self.security.review(contract)
        verdicts.append(security_verdict)
        self._persist_verdict(contract.mission_id, security_verdict)

        memory_verdict = self.memory.review(contract)
        verdicts.append(memory_verdict)
        self._persist_verdict(contract.mission_id, memory_verdict)

        contract = self._apply_council_context(contract, verdicts)
        if has_blocking_verdict(verdicts):
            return self._blocked_run(contract=contract, verdicts=verdicts)

        worker_run = await self.spawner.run(contract)
        self._persist_event(
            contract.mission_id,
            "worker_spawned",
            snapshot_id=worker_run.contract.snapshot_id,
        )
        testing_verdict = self.testing.verify(
            contract=worker_run.contract,
            ledger=worker_run.ledger,
        )
        verdicts.append(testing_verdict)
        self._persist_verdict(contract.mission_id, testing_verdict)

        ledger = self._enrich_worker_ledger(worker_run=worker_run, verdicts=verdicts)
        ledger_path = self.ledger_store.write(ledger)
        report = build_king_report(ledger=ledger, result=worker_run.result)
        report_path = self.report_store.write(report)
        self._persist_event(
            contract.mission_id,
            "report",
            risk=report.risk,
            snapshot_id=worker_run.contract.snapshot_id,
        )
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
