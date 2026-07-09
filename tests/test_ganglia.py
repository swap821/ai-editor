from __future__ import annotations

from aios.council.ganglia import signals_from_verdicts, synthesize_signals
from aios.runtime.contracts import QueenVerdict


def _verdict(
    queen: str,
    verdict: str,
    risk: str,
    *,
    confidence: float = 0.8,
) -> QueenVerdict:
    return QueenVerdict(
        queen=queen,
        verdict=verdict,  # type: ignore[arg-type]
        risk=risk,  # type: ignore[arg-type]
        reason=f"{queen} says {verdict}",
        confidence=confidence,
    )


def test_security_veto_wins_over_positive_advisory_signals() -> None:
    signals = signals_from_verdicts(
        [
            _verdict("planner", "allow", "GREEN"),
            _verdict("memory", "allow", "GREEN"),
            _verdict("security", "deny", "RED", confidence=0.95),
        ]
    )

    synthesis = synthesize_signals(signals)

    assert synthesis.status == "blocked"
    assert synthesis.risk == "RED"
    assert synthesis.security_veto is True
    assert synthesis.authority == "proposal/evidence"
    assert synthesis.advisory_only is True
    assert synthesis.can_authorize is False
    assert "security" in synthesis.reason.lower()


def test_memory_signal_is_strengthen_only_and_cannot_authorize() -> None:
    signal = signals_from_verdicts([_verdict("memory", "allow", "GREEN")])[0]

    assert signal.authority == "strengthen_only"
    assert signal.can_authorize is False
    assert signal.can_veto is False
