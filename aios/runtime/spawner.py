"""Council Runtime worker spawner for deterministic Phase 1A missions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aios.runtime.backends import ControlledSubprocessBackend, WorkerBackend, WorkerHandle
from aios.runtime.contracts import KingReport, MissionContract, RunLedger, WorkerResult
from aios.runtime.king_report import KingReportStore, build_king_report
from aios.runtime.run_ledger import RunLedgerStore, build_run_ledger
from aios.runtime.snapshots import SnapshotManager


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class WorkerRun:
    contract: MissionContract
    handle: WorkerHandle
    result: WorkerResult
    ledger: RunLedger
    report: KingReport
    ledger_path: Path
    report_path: Path


class WorkerSpawner:
    """Spawn, reap, ledger, and report one temporary worker."""

    def __init__(
        self,
        *,
        runtime_root: str | Path,
        backend: WorkerBackend | None = None,
        snapshot_manager: SnapshotManager | None = None,
        ledger_store: RunLedgerStore | None = None,
        report_store: KingReportStore | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root).resolve()
        self.backend = backend or ControlledSubprocessBackend(self.runtime_root)
        self.snapshot_manager = snapshot_manager or SnapshotManager(self.runtime_root)
        self.ledger_store = ledger_store or RunLedgerStore(self.runtime_root)
        self.report_store = report_store or KingReportStore(self.runtime_root)

    async def run(self, contract: MissionContract) -> WorkerRun:
        created_at = _utc_now()
        sealed_contract = self._seal_contract(contract)
        handle = await self.backend.spawn(sealed_contract)
        try:
            result = await self.backend.reap(handle)
        finally:
            if handle.status not in {"dead", "killed"}:
                await self.backend.kill(handle, "spawner cleanup after reap")

        ledger = build_run_ledger(
            contract=sealed_contract,
            handle=handle,
            result=result,
            created_at=created_at,
        )
        ledger_path = self.ledger_store.write(ledger)
        report = build_king_report(ledger=ledger, result=result)
        report_path = self.report_store.write(report)
        return WorkerRun(
            contract=sealed_contract,
            handle=handle,
            result=result,
            ledger=ledger,
            report=report,
            ledger_path=ledger_path,
            report_path=report_path,
        )

    def _seal_contract(self, contract: MissionContract) -> MissionContract:
        if contract.snapshot_id:
            return contract
        snapshot_id = self.snapshot_manager.create_snapshot(contract)
        return contract.model_copy(update={"snapshot_id": snapshot_id})


__all__ = ["WorkerRun", "WorkerSpawner"]
