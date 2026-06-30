"""Council Runtime worker spawner for deterministic Phase 1A missions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aios.runtime.backends import ControlledSubprocessBackend, WorkerBackend, WorkerHandle
from aios.runtime.concurrency import WORKER_POOL
from aios.runtime.contracts import KingReport, MissionContract, RunLedger, WorkerResult
from aios.runtime.king_report import KingReportStore, build_king_report
from aios.runtime.run_ledger import RunLedgerStore, build_run_ledger
from aios.runtime.snapshots import SnapshotManager


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MissionCollisionError(RuntimeError):
    """Raised when a mission_id already owns runtime artifacts on disk.

    Fail-closed: refusing to run prevents one mission from silently clobbering
    another run's ledger/report/worker artifacts under the same id.
    """


def claim_mission(runtime_root: str | Path, mission_id: str) -> Path:
    """Atomically claim a mission_id's runtime directory.

    The exclusive ``mkdir`` is the collision boundary for the whole mission, so
    a second run with the same id fails closed instead of overwriting the first.
    """
    mission_dir = Path(runtime_root) / "missions" / mission_id
    try:
        mission_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise MissionCollisionError(
            f"mission_id {mission_id!r} already has runtime artifacts; "
            "refusing to overwrite"
        ) from exc
    return mission_dir


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

    async def run(self, contract: MissionContract, *, claim: bool = True) -> WorkerRun:
        created_at = _utc_now()
        # claim=False when a prior phase (e.g. CouncilOrchestrator.deliberate)
        # already claimed the mission dir; re-claiming would falsely collide.
        if claim:
            claim_mission(self.runtime_root, contract.mission_id)
        sealed_contract = self._seal_contract(contract)
        # Global fail-closed cap: hold a worker slot for the subprocess lifetime so
        # a flood of approved missions cannot spawn unbounded subprocesses. At
        # capacity this raises WorkerCapacityError (the caller reports it).
        with WORKER_POOL.slot():
            handle = await self.backend.spawn(sealed_contract)
            try:
                result = await self.backend.reap(handle)
            finally:
                if handle.status not in {"dead", "killed"}:
                    await self.backend.kill(handle, "spawner cleanup after reap")

            if sealed_contract.snapshot_id and result.rollback_id is None:
                result = result.model_copy(
                    update={"rollback_id": sealed_contract.snapshot_id}
                )
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


__all__ = ["MissionCollisionError", "WorkerRun", "WorkerSpawner", "claim_mission"]
