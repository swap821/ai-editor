"""Tests for aios.council.deliberation_gather (organ 39: the real,
independent-second-opinion gather step Slice 34's pure functions never had
a production caller for)."""

from __future__ import annotations

import json

from aios.council.deliberation_gather import maybe_deliberate
from aios.runtime.contracts import KingReport


def _report(
    *,
    recommendation: str = "approve",
    verdicts: list[dict] | None = None,
    summary: str = "Worker completed the mission.",
) -> KingReport:
    return KingReport(
        mission_id="mission-1",
        mission="add aria-labels to the login form",
        status="completed",
        recommendation=recommendation,
        risk="GREEN",
        approval_needed=False,
        rollback_available=False,
        human_summary=summary,
        council_summary={"council_verdicts": verdicts or []},
    )


def _dissent(payload: dict):
    def complete(prompt: str) -> str:
        return json.dumps(payload)
    return complete


def test_no_dissent_client_means_no_deliberation():
    report = _report(recommendation="reject")
    record = maybe_deliberate(
        report,
        mission_id="mission-1",
        king_provider="ollama",
        king_exact_model_id="qwen2.5-coder:7b",
        dissent_complete=None,
        dissent_provider="gemini",
        dissent_exact_model_id="gemini-2.5-flash",
    )
    assert record is None


def test_approve_with_no_disagreement_does_not_trigger():
    """should_trigger_deliberation is never fired for a trivial approve."""
    report = _report(recommendation="approve", verdicts=[
        {"queen": "security", "verdict": "allow", "risk": "GREEN", "reason": "clean", "confidence": 0.9},
    ])
    record = maybe_deliberate(
        report,
        mission_id="mission-1",
        king_provider="ollama",
        king_exact_model_id="qwen2.5-coder:7b",
        dissent_complete=_dissent({"answer": "approve", "confidence": 0.8}),
        dissent_provider="gemini",
        dissent_exact_model_id="gemini-2.5-flash",
    )
    assert record is None


def test_block_tier_recommendation_triggers_and_synthesizes_a_real_record():
    report = _report(recommendation="reject")
    record = maybe_deliberate(
        report,
        mission_id="mission-1",
        king_provider="ollama",
        king_exact_model_id="qwen2.5-coder:7b",
        dissent_complete=_dissent(
            {
                "answer": "reject",
                "confidence": 0.7,
                "security_concerns": ["unvalidated user input"],
            }
        ),
        dissent_provider="gemini",
        dissent_exact_model_id="gemini-2.5-flash",
    )
    assert record is not None
    assert record.mission_id == "mission-1"
    assert len(record.positions) == 2
    assert {p.provider for p in record.positions} == {"ollama", "gemini"}
    assert record.final_disposition == "reject"
    assert record.unresolved_minority_concerns == ("unvalidated user input",)


def test_conflicting_queen_verdicts_trigger_even_on_approve():
    report = _report(
        recommendation="approve",
        verdicts=[
            {"queen": "security", "verdict": "allow", "risk": "GREEN", "reason": "clean", "confidence": 0.9},
            {"queen": "testing", "verdict": "deny", "risk": "YELLOW", "reason": "flaky", "confidence": 0.6},
        ],
    )
    record = maybe_deliberate(
        report,
        mission_id="mission-1",
        king_provider="ollama",
        king_exact_model_id="qwen2.5-coder:7b",
        dissent_complete=_dissent({"answer": "observe", "confidence": 0.5}),
        dissent_provider="gemini",
        dissent_exact_model_id="gemini-2.5-flash",
    )
    assert record is not None
    assert "conflicting_evidence" in record.trigger_reasons


def test_dissent_call_raising_degrades_to_none_not_an_exception():
    report = _report(recommendation="reject")

    def flaky(prompt: str) -> str:
        raise RuntimeError("provider outage")

    record = maybe_deliberate(
        report,
        mission_id="mission-1",
        king_provider="ollama",
        king_exact_model_id="qwen2.5-coder:7b",
        dissent_complete=flaky,
        dissent_provider="gemini",
        dissent_exact_model_id="gemini-2.5-flash",
    )
    assert record is None


def test_unparseable_dissent_reply_degrades_to_none():
    report = _report(recommendation="reject")
    record = maybe_deliberate(
        report,
        mission_id="mission-1",
        king_provider="ollama",
        king_exact_model_id="qwen2.5-coder:7b",
        dissent_complete=lambda prompt: "I refuse to answer in JSON.",
        dissent_provider="gemini",
        dissent_exact_model_id="gemini-2.5-flash",
    )
    assert record is None


def test_dissent_missing_confidence_degrades_to_none():
    report = _report(recommendation="reject")
    record = maybe_deliberate(
        report,
        mission_id="mission-1",
        king_provider="ollama",
        king_exact_model_id="qwen2.5-coder:7b",
        dissent_complete=_dissent({"answer": "reject"}),
        dissent_provider="gemini",
        dissent_exact_model_id="gemini-2.5-flash",
    )
    assert record is None


def test_confidence_out_of_range_is_clamped_not_rejected():
    report = _report(recommendation="reject")
    record = maybe_deliberate(
        report,
        mission_id="mission-1",
        king_provider="ollama",
        king_exact_model_id="qwen2.5-coder:7b",
        dissent_complete=_dissent({"answer": "reject", "confidence": 5.0}),
        dissent_provider="gemini",
        dissent_exact_model_id="gemini-2.5-flash",
    )
    assert record is not None
    dissent_position = next(p for p in record.positions if p.provider == "gemini")
    assert dissent_position.confidence == 1.0


def test_same_provider_for_king_and_dissent_violates_independence():
    """verify_independence() must actually be consulted -- a same-provider
    'dissent' is not real independence and must not synthesize a record."""
    report = _report(recommendation="reject")
    record = maybe_deliberate(
        report,
        mission_id="mission-1",
        king_provider="ollama",
        king_exact_model_id="qwen2.5-coder:7b",
        dissent_complete=_dissent({"answer": "reject", "confidence": 0.7}),
        dissent_provider="ollama",
        dissent_exact_model_id="qwen2.5:7b",
    )
    assert record is None
