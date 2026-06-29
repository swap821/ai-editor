"""Reasoning King — an opt-in LLM that reasons over the Queens' verdicts and the
result to produce a richer recommendation + rationale.

The safety invariant is a STRENGTHEN-ONLY caution clamp: the King's LLM proposal is
accepted only if it is AS cautious or MORE than the deterministic baseline. It can
NEVER flip a block (revise/rollback/reject) into a go (approve/observe), never soften
a reject, and any LLM/parse error fails closed to the deterministic recommendation.
The LLM's rationale is advisory (always surfaced); the DECISION is clamped.
"""
from __future__ import annotations

from aios.council.king_reasoning import clamp_recommendation, reason_king
from aios.runtime.contracts import KingReport, MissionContract, QueenVerdict


# ── the clamp: the safety core ───────────────────────────────────────────────

def test_clamp_never_downgrades_a_block_to_a_go() -> None:
    # The critical invariant: a block can never become a go.
    assert clamp_recommendation("reject", "approve") == "reject"
    assert clamp_recommendation("reject", "observe") == "reject"
    assert clamp_recommendation("revise", "approve") == "revise"
    assert clamp_recommendation("rollback", "approve") == "rollback"


def test_clamp_never_softens_a_reject() -> None:
    # reject is maximal caution — not even softenable to revise/rollback.
    assert clamp_recommendation("reject", "revise") == "reject"
    assert clamp_recommendation("reject", "rollback") == "reject"


def test_clamp_allows_more_caution() -> None:
    assert clamp_recommendation("approve", "revise") == "revise"
    assert clamp_recommendation("approve", "reject") == "reject"
    assert clamp_recommendation("revise", "rollback") == "rollback"
    assert clamp_recommendation("revise", "reject") == "reject"


def test_clamp_equal_and_unknown_failsafe() -> None:
    assert clamp_recommendation("approve", "approve") == "approve"
    # unknown / garbage proposal → baseline holds (fail-closed)
    assert clamp_recommendation("approve", "banana") == "approve"
    assert clamp_recommendation("reject", "") == "reject"


# ── reason_king: clamp + advisory rationale + fail-closed ────────────────────

def _contract() -> MissionContract:
    return MissionContract(
        mission_id="m1", goal="g", worker_type="editor", created_by="t", workspace_root="/ws"
    )


def _report(rec: str, summary: str = "baseline summary", status: str = "completed") -> KingReport:
    return KingReport(
        mission_id="m1",
        mission="g",
        status=status,
        recommendation=rec,
        risk="GREEN",
        approval_needed=False,
        rollback_available=False,
        human_summary=summary,
    )


def _verdicts() -> list[QueenVerdict]:
    return [QueenVerdict(queen="security", verdict="allow", risk="GREEN", reason="clean")]


def test_reason_king_clamps_unsafe_upgrade_but_surfaces_rationale() -> None:
    base = _report("reject", "Council blocked approval.", status="failed")
    out = reason_king(
        base,
        contract=_contract(),
        verdicts=_verdicts(),
        complete=lambda _p: "RECOMMENDATION: approve\nRATIONALE: looks fine to me",
    )
    assert out.recommendation == "reject"  # the LLM CANNOT override the block
    assert "fine" in out.human_summary.lower()  # ...but its reasoning is shown


def test_reason_king_accepts_added_caution() -> None:
    base = _report("approve", "Worker completed.")
    out = reason_king(
        base,
        contract=_contract(),
        verdicts=_verdicts(),
        complete=lambda _p: "RECOMMENDATION: revise\nRATIONALE: the verification was thin",
    )
    assert out.recommendation == "revise"
    assert "thin" in out.human_summary.lower()


def test_reason_king_fails_closed_on_llm_error() -> None:
    base = _report("approve", "Worker completed.")

    def boom(_p: str) -> str:
        raise RuntimeError("llm unreachable")

    out = reason_king(base, contract=_contract(), verdicts=_verdicts(), complete=boom)
    assert out.recommendation == "approve"  # unchanged
    assert out.human_summary == "Worker completed."  # untouched on failure


def test_orchestrator_stores_injected_king_complete(tmp_path) -> None:
    from aios.council.council_orchestrator import CouncilOrchestrator

    fn = lambda _p: "RECOMMENDATION: reject\nRATIONALE: nope"
    assert CouncilOrchestrator(runtime_root=tmp_path, king_complete=fn).king_complete is fn
    assert CouncilOrchestrator(runtime_root=tmp_path).king_complete is None


def test_reason_king_fails_closed_on_unparseable_output() -> None:
    base = _report("approve", "Worker completed.")
    out = reason_king(
        base,
        contract=_contract(),
        verdicts=_verdicts(),
        complete=lambda _p: "I have no idea, here are some thoughts with no verdict.",
    )
    assert out.recommendation == "approve"  # no parseable rec → baseline holds
