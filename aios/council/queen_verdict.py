"""Helpers for working with Council Runtime queen verdicts."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aios.runtime.contracts import QueenVerdict, RiskLevel

_RISK_RANK: dict[str, int] = {"GREEN": 0, "YELLOW": 1, "RED": 2}


def highest_risk(risks: Iterable[RiskLevel | str]) -> RiskLevel:
    """Return the highest Council risk in *risks*."""

    highest: RiskLevel = "GREEN"
    for risk in risks:
        risk_text = str(risk)
        candidate: RiskLevel = risk_text if risk_text in _RISK_RANK else "RED"  # type: ignore[assignment]
        if _RISK_RANK[candidate] > _RISK_RANK[highest]:
            highest = candidate
    return highest


def has_blocking_verdict(verdicts: Iterable[QueenVerdict]) -> bool:
    """Whether any queen verdict stops worker execution."""

    return any(verdict.verdict in {"deny", "defer"} for verdict in verdicts)


def verdicts_as_metadata(verdicts: Iterable[QueenVerdict]) -> list[dict[str, Any]]:
    """Return JSON-safe verdict summaries for reports and MissionContract metadata."""

    return [
        {
            "queen": verdict.queen,
            "verdict": verdict.verdict,
            "risk": verdict.risk,
            "reason": verdict.reason,
            "constraints": list(verdict.constraints),
            "confidence": verdict.confidence,
            "metadata": dict(verdict.metadata),
        }
        for verdict in verdicts
    ]


__all__ = ["has_blocking_verdict", "highest_risk", "verdicts_as_metadata"]
