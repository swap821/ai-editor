"""Run ledger construction and persistence for Council Runtime v0.1."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios.runtime.backends import WorkerHandle
from aios.runtime.contracts import MissionContract, RunLedger, WorkerResult


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_run_ledger(
    *,
    contract: MissionContract,
    handle: WorkerHandle,
    result: WorkerResult,
    created_at: str,
) -> RunLedger:
    evidence: dict[str, Any] = dict(result.evidence)
    return RunLedger(
        mission_id=contract.mission_id,
        mission=contract.goal,
        risk_before=contract.risk_level,
        risk_after=result.risk_after,
        contract=contract,
        workers_created=[handle.worker_id],
        files_allowed=list(contract.allowed_files),
        files_touched=list(result.files_touched),
        blocked_attempts=list(evidence.get("blocked_attempts", [])),
        tool_calls=list(result.tool_calls),
        verification={"commands": evidence.get("verification", [])},
        snapshot_id=contract.snapshot_id,
        rollback_id=result.rollback_id,
        status=result.status,
        created_at=created_at,
        completed_at=result.ended_at or _utc_now(),
        evidence=evidence,
    )


class RunLedgerStore:
    """Persist one run ledger per mission under the runtime root."""

    def __init__(self, runtime_root: str | Path) -> None:
        self.runtime_root = Path(runtime_root).resolve()

    def path_for(self, mission_id: str) -> Path:
        return self.runtime_root / "missions" / mission_id / "run_ledger.json"

    def write(self, ledger: RunLedger) -> Path:
        path = self.path_for(ledger.mission_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ledger.model_dump_json(indent=2), encoding="utf-8")
        return path

    def read(self, mission_id: str) -> RunLedger:
        return RunLedger.model_validate_json(
            self.path_for(mission_id).read_text(encoding="utf-8")
        )


__all__ = ["RunLedgerStore", "build_run_ledger"]
