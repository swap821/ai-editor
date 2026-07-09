from __future__ import annotations

from pathlib import Path

from aios.council.council_memory import CouncilMemory
from aios.council.ganglia import signals_from_verdicts, synthesize_signals
from aios.runtime.contracts import QueenVerdict


def _verdict(queen: str = "security", verdict: str = "allow", risk: str = "GREEN") -> QueenVerdict:
    return QueenVerdict(
        queen=queen,
        verdict=verdict,  # type: ignore[arg-type]
        risk=risk,  # type: ignore[arg-type]
        reason="test verdict",
        confidence=0.9,
    )


def test_council_memory_records_deliberation_as_advisory_evidence(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "council_state.db"
    verdicts = [_verdict()]
    signals = signals_from_verdicts(verdicts)
    synthesis = synthesize_signals(signals)

    CouncilMemory(db_path=db_path).record_deliberation(
        mission_id="m1",
        verdicts=verdicts,
        signals=signals,
        synthesis=synthesis,
    )

    reloaded = CouncilMemory(db_path=db_path)
    rows = reloaded.deliberations_for("m1")

    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["authority"] == "proposal/evidence"
    assert payload["can_authorize"] is False
    assert payload["synthesis"]["status"] == "supported"
    assert payload["signals"][0]["source"] == "security"


def test_council_memory_is_append_only(tmp_path: Path) -> None:
    memory = CouncilMemory(db_path=tmp_path / "council_state.db")
    verdicts = [_verdict()]
    signals = signals_from_verdicts(verdicts)
    synthesis = synthesize_signals(signals)

    memory.record_deliberation(
        mission_id="m1",
        verdicts=verdicts,
        signals=signals,
        synthesis=synthesis,
    )
    memory.record_deliberation(
        mission_id="m1",
        verdicts=verdicts,
        signals=signals,
        synthesis=synthesis,
    )

    assert len(memory.deliberations_for("m1")) == 2
