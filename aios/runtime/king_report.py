"""Human-facing KingReport generation for Council Runtime v0.1."""
from __future__ import annotations

from pathlib import Path

from aios.core.verification_strength import (
    VerificationStrength,
    meets_promotion_floor,
    promotion_floor,
    strength_from_name,
)
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
        if any(v.queen == "security" and v.verdict == "deny" for v in denied):
            recommendation = "reject"
        elif ledger.rollback_id and ledger.files_touched:
            recommendation = "rollback"
        else:
            recommendation = "revise"
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
        recommendation = "rollback" if ledger.rollback_id and ledger.files_touched else "revise"
        human_summary = f"Worker ended with status {result.status}: {result.summary}"

    intelligence = _latest_intelligence(ledger)

    # Slice A1 — the King approves on TYPED evidence. Surface the verification
    # strength and FLAG a positive recommendation that rests on below-floor (weak/
    # hollow) evidence. Fail-closed: a missing/unparseable strength reads NONE
    # (strength_from_name defaults to STRONG, so NONE must be passed explicitly),
    # so weak/unknown evidence is flagged, never waved through.
    verification_result = dict(ledger.verification)
    strength = strength_from_name(
        verification_result.get("strength"), VerificationStrength.NONE
    )
    meets_floor = meets_promotion_floor(strength)
    verification_result["meets_floor"] = meets_floor
    if recommendation in {"approve", "observe"} and not meets_floor:
        floor = promotion_floor().name
        verification_result["below_floor_warning"] = (
            f"verification strength {strength.name} is below the {floor} floor — this "
            "recommendation rests on weak evidence; review before approving"
        )
        human_summary = (
            f"⚠ Weak verification ({strength.name} < {floor} floor). " + human_summary
        )

    royal_decree = ledger.contract.metadata.get("royal_decree")
    ganglia_synthesis = ledger.contract.metadata.get("ganglia_synthesis")
    ganglia_signals = ledger.contract.metadata.get("ganglia_signals")
    council_summary = {
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
    }
    if isinstance(royal_decree, dict):
        council_summary["royal_decree"] = royal_decree
    if isinstance(ganglia_synthesis, dict):
        council_summary["ganglia_synthesis"] = ganglia_synthesis
    if isinstance(ganglia_signals, list):
        council_summary["ganglia_signals"] = ganglia_signals

    return KingReport(
        mission_id=ledger.mission_id,
        mission=ledger.mission,
        status=status,
        council_summary=council_summary,
        recommendation=recommendation,
        risk=ledger.risk_after,
        files=list(ledger.files_touched),
        verification_result=verification_result,
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
    royal_decree = contract.metadata.get("royal_decree")
    ganglia_synthesis = contract.metadata.get("ganglia_synthesis")
    ganglia_signals = contract.metadata.get("ganglia_signals")
    council_summary = {
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
    }
    if isinstance(royal_decree, dict):
        council_summary["royal_decree"] = royal_decree
    if isinstance(ganglia_synthesis, dict):
        council_summary["ganglia_synthesis"] = ganglia_synthesis
    if isinstance(ganglia_signals, list):
        council_summary["ganglia_signals"] = ganglia_signals

    return KingReport(
        mission_id=contract.mission_id,
        mission=contract.goal,
        status="awaiting_approval",
        council_summary=council_summary,
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
        from aios.runtime import _safe_resolve
        self.runtime_root = _safe_resolve(runtime_root)

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
