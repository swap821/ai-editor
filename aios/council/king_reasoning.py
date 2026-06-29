"""Reasoning King — opt-in LLM deliberation over the council's verdicts.

The King reads the mission, the Queen verdicts, and the result and proposes a
recommendation + rationale. SAFETY INVARIANT: a STRENGTHEN-ONLY caution clamp — the
King's proposal is accepted only if it is AS cautious or MORE than the deterministic
baseline. It can NEVER flip a block (revise/rollback/reject) into a go (approve/
observe), never soften a reject, and any LLM/parse error fails closed to the
deterministic recommendation. The rationale is advisory (always surfaced); the
DECISION is clamped. Mirrors reasoning.py's narrow-only plan clamp.
"""
from __future__ import annotations

import re
from typing import Callable, Sequence

from aios.runtime.contracts import KingReport, MissionContract, QueenVerdict

# Caution ranking: higher = more restrictive. The King may only move TOWARD more
# caution. approve/observe are both "go" (rank 0); a block is rank >= 1, so the
# clamp can never turn a block into a go.
_CAUTION_RANK = {
    "approve": 0,
    "observe": 0,
    "revise": 1,
    "rollback": 2,
    "reject": 3,
}
_VALID = set(_CAUTION_RANK)

_REC_RE = re.compile(r"RECOMMENDATION\s*:\s*([a-z_]+)", re.IGNORECASE)
_RATIONALE_RE = re.compile(r"RATIONALE\s*:\s*(.+)", re.IGNORECASE | re.DOTALL)


def clamp_recommendation(baseline: str, proposed: str) -> str:
    """Return ``proposed`` only if it is AS cautious or MORE than ``baseline``;
    otherwise keep ``baseline``. Unknown/invalid ``proposed`` → baseline (fail-closed)."""
    p = (proposed or "").strip().lower()
    if p not in _VALID:
        return baseline
    return p if _CAUTION_RANK[p] >= _CAUTION_RANK.get(baseline, 0) else baseline


def _build_prompt(
    report: KingReport,
    contract: MissionContract,
    verdicts: Sequence[QueenVerdict],
) -> str:
    lines = [
        "You are the King of an AI council reviewing a completed mission.",
        f"Goal: {contract.goal}",
        f"Result status: {report.status}",
        f"Verification strength: {report.verification_result.get('strength', 'unknown')}",
        f"Deterministic recommendation: {report.recommendation}",
        "Queen verdicts:",
    ]
    for v in verdicts:
        lines.append(f"  - {v.queen}: {v.verdict} ({v.confidence:.2f}) — {v.reason}")
    lines += [
        "",
        "You may only MAINTAIN or INCREASE caution — you cannot approve what a Queen "
        "denied. Reply EXACTLY in this form:",
        "RECOMMENDATION: <approve|observe|revise|rollback|reject>",
        "RATIONALE: <one or two sentences>",
    ]
    return "\n".join(lines)


def reason_king(
    report: KingReport,
    *,
    contract: MissionContract,
    verdicts: Sequence[QueenVerdict],
    complete: Callable[[str], str] | None,
) -> KingReport:
    """Enrich the King report with clamped LLM reasoning. Fail-closed: returns the
    report unchanged on any error or unparseable output."""
    if complete is None:
        return report
    try:
        raw = complete(_build_prompt(report, contract, verdicts))
    except Exception:
        return report
    if not raw:
        return report
    rec_match = _REC_RE.search(raw)
    if not rec_match:
        return report  # no parseable recommendation → baseline holds
    final = clamp_recommendation(report.recommendation, rec_match.group(1))
    rationale_match = _RATIONALE_RE.search(raw)
    rationale = ""
    if rationale_match:
        first = rationale_match.group(1).strip().splitlines()
        rationale = first[0].strip() if first else ""
    if not rationale:
        if final == report.recommendation:
            return report
        return report.model_copy(update={"recommendation": final})
    summary = f"King: {rationale} — " + report.human_summary
    return report.model_copy(update={"recommendation": final, "human_summary": summary})


__all__ = ["clamp_recommendation", "reason_king"]
