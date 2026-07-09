"""Typed advisory signal layer for Council verdicts.

Ganglia convert existing Queen verdicts into inspectable gradients. They do not
replace verdict authority: security remains deterministic, and every synthesized
result is proposal/evidence only.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aios.council.queen_verdict import highest_risk
from aios.runtime.contracts import QueenVerdict, RiskLevel

SignalPolarity = Literal["support", "caution", "block"]
SignalAuthority = Literal["deterministic", "strengthen_only", "advisory"]
SynthesisStatus = Literal["supported", "caution", "blocked"]


class GanglionSignal(BaseModel):
    """One typed gradient derived from an existing QueenVerdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    verdict: str
    risk: RiskLevel
    polarity: SignalPolarity
    strength: float = Field(ge=0.0, le=1.0)
    reason: str
    constraints: list[str] = Field(default_factory=list)
    authority: SignalAuthority
    can_veto: bool = False
    can_authorize: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class SignalSynthesis(BaseModel):
    """Advisory synthesis of ganglion signals for reports and memory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SynthesisStatus
    risk: RiskLevel
    reason: str
    security_veto: bool = False
    advisory_only: bool = True
    authority: Literal["proposal/evidence"] = "proposal/evidence"
    can_authorize: bool = False
    constraints: list[str] = Field(default_factory=list)


def signal_from_verdict(verdict: QueenVerdict) -> GanglionSignal:
    """Translate one QueenVerdict into a typed, non-authorizing signal."""

    queen = verdict.queen.lower()
    is_security = queen == "security"
    polarity = _polarity_for(verdict)
    return GanglionSignal(
        source=verdict.queen,
        verdict=verdict.verdict,
        risk=verdict.risk,
        polarity=polarity,
        strength=_clamp_confidence(verdict.confidence),
        reason=verdict.reason,
        constraints=list(verdict.constraints),
        authority="deterministic" if is_security else _non_security_authority(queen),
        can_veto=is_security and polarity == "block",
        can_authorize=False,
        metadata=dict(verdict.metadata),
    )


def signals_from_verdicts(verdicts: Iterable[QueenVerdict]) -> list[GanglionSignal]:
    return [signal_from_verdict(verdict) for verdict in verdicts]


def synthesize_signals(signals: Iterable[GanglionSignal]) -> SignalSynthesis:
    """Synthesize signals with deterministic security veto strongest."""

    signal_list = list(signals)
    risks = [signal.risk for signal in signal_list] or ["GREEN"]
    constraints = [
        constraint
        for signal in signal_list
        for constraint in signal.constraints
    ]
    security_blocks = [
        signal
        for signal in signal_list
        if signal.source.lower() == "security" and signal.can_veto
    ]
    if security_blocks:
        return SignalSynthesis(
            status="blocked",
            risk="RED",
            reason=f"Security veto: {security_blocks[0].reason}",
            security_veto=True,
            constraints=constraints,
        )

    blocking = [signal for signal in signal_list if signal.polarity == "block"]
    if blocking:
        return SignalSynthesis(
            status="blocked",
            risk=highest_risk(risks),
            reason=f"{blocking[0].source} requested block/defer: {blocking[0].reason}",
            constraints=constraints,
        )

    cautions = [
        signal
        for signal in signal_list
        if signal.polarity == "caution" or signal.risk == "YELLOW"
    ]
    if cautions:
        return SignalSynthesis(
            status="caution",
            risk=highest_risk(risks),
            reason=f"{len(cautions)} caution signal(s) require review.",
            constraints=constraints,
        )

    return SignalSynthesis(
        status="supported",
        risk=highest_risk(risks),
        reason="No blocking or cautionary ganglia signals.",
        constraints=constraints,
    )


def _polarity_for(verdict: QueenVerdict) -> SignalPolarity:
    if verdict.verdict in {"deny", "defer"}:
        return "block"
    if verdict.verdict == "allow_with_approval" or verdict.risk == "YELLOW":
        return "caution"
    return "support"


def _non_security_authority(queen: str) -> SignalAuthority:
    if queen in {"memory", "planner", "critique", "testing"}:
        return "strengthen_only"
    return "advisory"


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


__all__ = [
    "GanglionSignal",
    "SignalSynthesis",
    "signal_from_verdict",
    "signals_from_verdicts",
    "synthesize_signals",
]
