"""Human-facing KingReport generation for Council Runtime v0.1."""
from __future__ import annotations

from pathlib import Path

from aios.runtime.contracts import KingReport, RunLedger, WorkerResult


def build_king_report(*, ledger: RunLedger, result: WorkerResult) -> KingReport:
    if result.status == "completed":
        status = "completed"
        recommendation = "approve" if ledger.contract.requires_approval else "observe"
        human_summary = (
            "Worker completed the mission under its MissionContract. "
            f"{len(ledger.blocked_attempts)} blocked attempt(s) were recorded."
        )
    elif result.status == "awaiting_approval":
        status = "awaiting_approval"
        recommendation = "observe"
        human_summary = "Worker is paused awaiting King approval."
    elif result.status == "killed":
        status = "failed"
        recommendation = "rollback"
        human_summary = "Worker was killed before successful completion."
    else:
        status = "failed"
        recommendation = "revise"
        human_summary = f"Worker ended with status {result.status}: {result.summary}"

    return KingReport(
        mission_id=ledger.mission_id,
        mission=ledger.mission,
        status=status,
        council_summary={
            "workers_created": ledger.workers_created,
            "blocked_attempts": len(ledger.blocked_attempts),
            "backend": result.evidence.get("backend", "controlled_subprocess"),
        },
        recommendation=recommendation,
        risk=ledger.risk_after,
        files=list(ledger.files_touched),
        verification_result=dict(ledger.verification),
        approval_needed=ledger.contract.requires_approval,
        rollback_available=bool(ledger.rollback_id),
        rollback_id=ledger.rollback_id,
        evidence=ledger.evidence,
        human_summary=human_summary,
    )


class KingReportStore:
    """Persist one KingReport per mission under the runtime root."""

    def __init__(self, runtime_root: str | Path) -> None:
        self.runtime_root = Path(runtime_root).resolve()

    def path_for(self, mission_id: str) -> Path:
        return self.runtime_root / "missions" / mission_id / "king_report.json"

    def write(self, report: KingReport) -> Path:
        path = self.path_for(report.mission_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return path

    def read(self, mission_id: str) -> KingReport:
        return KingReport.model_validate_json(
            self.path_for(mission_id).read_text(encoding="utf-8")
        )


__all__ = ["KingReportStore", "build_king_report"]
