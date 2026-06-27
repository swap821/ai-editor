"""Human-facing KingReport generation for Council Runtime v0.1."""
from __future__ import annotations

from pathlib import Path

from aios.runtime.contracts import (
    KingReport,
    MissionContract,
    QueenVerdict,
    RunLedger,
    WorkerResult,
)


def build_king_report(*, ledger: RunLedger, result: WorkerResult) -> KingReport:
    denied = [
        verdict
        for verdict in ledger.council_verdicts
        if verdict.verdict in {"deny", "defer"}
    ]
    if denied:
        status = "failed" if any(v.verdict == "deny" for v in denied) else "needs_revision"
        recommendation = (
            "reject"
            if any(v.queen == "security" and v.verdict == "deny" for v in denied)
            else "revise"
        )
        human_summary = (
            "Council blocked approval: "
            + "; ".join(f"{verdict.queen}: {verdict.reason}" for verdict in denied)
        )
    elif result.status == "completed":
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

    intelligence = _latest_intelligence(ledger)

    return KingReport(
        mission_id=ledger.mission_id,
        mission=ledger.mission,
        status=status,
        council_summary={
            "workers_created": ledger.workers_created,
            "blocked_attempts": len(ledger.blocked_attempts),
            "backend": result.evidence.get("backend", "controlled_subprocess"),
            "council_verdicts": [
                {
                    "queen": verdict.queen,
                    "verdict": verdict.verdict,
                    "risk": verdict.risk,
                    "reason": verdict.reason,
                    "confidence": verdict.confidence,
                }
                for verdict in ledger.council_verdicts
            ],
            "model_routing": intelligence,
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


def build_deliberation_report(
    *,
    contract: MissionContract,
    verdicts: list[QueenVerdict],
) -> KingReport:
    """Pre-execution report: the council has deliberated and the mission awaits
    King approval. No worker has run; nothing has been edited yet."""
    return KingReport(
        mission_id=contract.mission_id,
        mission=contract.goal,
        status="awaiting_approval",
        council_summary={
            "workers_created": [],
            "blocked_attempts": 0,
            "council_verdicts": [
                {
                    "queen": verdict.queen,
                    "verdict": verdict.verdict,
                    "risk": verdict.risk,
                    "reason": verdict.reason,
                    "confidence": verdict.confidence,
                }
                for verdict in verdicts
            ],
            "model_routing": {},
        },
        recommendation="approve" if contract.requires_approval else "observe",
        risk=contract.risk_level,
        files=list(contract.allowed_files),
        verification_result={},
        approval_needed=contract.requires_approval,
        rollback_available=False,
        evidence={"council": [v.model_dump() for v in verdicts]},
        human_summary=(
            "Council deliberation complete; awaiting King approval before the "
            "worker may act."
        ),
    )


def _latest_intelligence(ledger: RunLedger) -> dict:
    intelligence = ledger.evidence.get("intelligence", [])
    if not isinstance(intelligence, list) or not intelligence:
        return {}
    latest = intelligence[-1]
    if not isinstance(latest, dict):
        return {}
    return {
        "provider": latest.get("provider"),
        "model": latest.get("model"),
        "used_cloud": latest.get("used_cloud"),
        "cost_estimate": latest.get("cost_estimate"),
        "fallback_used": latest.get("fallback_used"),
    }


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


__all__ = ["KingReportStore", "build_deliberation_report", "build_king_report"]
