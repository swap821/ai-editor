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
    verification_result: dict | None = None,
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
        verification_result=verification_result or {},
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
    report = _report(
        recommendation="approve",
        verdicts=[
            {
                "queen": "security",
                "verdict": "allow",
                "risk": "GREEN",
                "reason": "clean",
                "confidence": 0.9,
            },
        ],
    )
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
            {
                "queen": "security",
                "verdict": "allow",
                "risk": "GREEN",
                "reason": "clean",
                "confidence": 0.9,
            },
            {
                "queen": "testing",
                "verdict": "deny",
                "risk": "YELLOW",
                "reason": "flaky",
                "confidence": 0.6,
            },
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


# --------------------------------------------------------------------------- #
# Organ 39: King confidence must be MEASURED, not a fixed constant.
#
# It was `1.0 if blocking else 0.5` -- total certainty asserted for any block
# recommendation regardless of whether any evidence supported it.
# --------------------------------------------------------------------------- #


def test_king_confidence_tracks_real_verification_strength() -> None:
    from aios.council.deliberation_gather import _measured_king_confidence

    strong = _measured_king_confidence(
        _report(recommendation="reject", verification_result={"strength": "STRONG"})
    )
    weak = _measured_king_confidence(
        _report(recommendation="reject", verification_result={"strength": "WEAK"})
    )
    none = _measured_king_confidence(
        _report(recommendation="reject", verification_result={"strength": "NONE"})
    )

    assert strong > weak > none, (strong, weak, none)
    # The old behaviour asserted 1.0 for every one of these.
    assert strong < 1.0


def test_unknown_verification_evidence_fails_closed_to_the_weakest() -> None:
    """A missing or unparseable strength must LOWER confidence, not inherit a
    high default -- matching king_report.py's own fail-closed convention."""
    from aios.council.deliberation_gather import _measured_king_confidence

    unknown = _measured_king_confidence(_report(recommendation="reject"))
    explicit_none = _measured_king_confidence(
        _report(recommendation="reject", verification_result={"strength": "NONE"})
    )

    assert unknown == explicit_none


def test_evidence_below_the_promotion_floor_is_never_confident() -> None:
    from aios.council.deliberation_gather import _measured_king_confidence

    below = _measured_king_confidence(
        _report(
            recommendation="approve",
            verification_result={"strength": "STRONG", "meets_floor": False},
        )
    )

    assert below <= 0.45


def test_confidence_no_longer_depends_only_on_the_recommendation_tier() -> None:
    """The old formula returned 1.0 for every blocking recommendation and 0.5
    for every other, so two reports with identical evidence but different
    recommendations differed, while two with identical recommendations and
    wildly different evidence did not."""
    from aios.council.deliberation_gather import _measured_king_confidence

    reject_strong = _measured_king_confidence(
        _report(recommendation="reject", verification_result={"strength": "STRONG"})
    )
    approve_strong = _measured_king_confidence(
        _report(recommendation="approve", verification_result={"strength": "STRONG"})
    )
    reject_none = _measured_king_confidence(
        _report(recommendation="reject", verification_result={"strength": "NONE"})
    )

    assert reject_strong == approve_strong  # evidence, not tier
    assert reject_strong != reject_none  # and it actually varies with evidence
