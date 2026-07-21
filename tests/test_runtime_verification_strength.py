"""Slice A1 — the King approves on TYPED verification.

The verification-strength gate already protects what the system LEARNS; these
tests pin that it now also reaches what the human APPROVES on: the RunLedger and
KingReport carry the verification STRENGTH, and a positive recommendation that
rests on below-floor (weak/hollow) evidence is visibly flagged. Fail-closed:
missing/failed/empty verification reads NONE, never STRONG.
"""
from __future__ import annotations

from types import SimpleNamespace

from aios.runtime.contracts import MissionContract, WorkerResult
from aios.runtime.king_report import build_king_report
from aios.runtime.run_ledger import build_run_ledger

_HANDLE = SimpleNamespace(worker_id="worker-1")
_CREATED = "2026-06-28T00:00:00+00:00"

STRONG_V = [{"command": ["pytest", "-q"], "returncode": 0, "stdout": "3 passed", "stderr": ""}]
WEAK_V = [{"command": ["echo", "done"], "returncode": 0, "stdout": "done", "stderr": ""}]
FAILED_V = [{"command": ["pytest", "-q"], "returncode": 1, "stdout": "1 failed", "stderr": ""}]
# A strong AND a weak check: weakest-link wins (one strong cannot launder a weak).
MIXED_V = STRONG_V + WEAK_V


def _contract(*, requires_approval: bool = True) -> MissionContract:
    return MissionContract(
        mission_id="m1",
        goal="thread strength into governance",
        worker_type="deterministic_worker",
        created_by="planner",
        workspace_root="/tmp/ws",
        requires_approval=requires_approval,
        verification_commands=["pytest -q"],
    )


def _result(verification: list, *, status: str = "completed") -> WorkerResult:
    return WorkerResult(
        mission_id="m1",
        worker_id="worker-1",
        status=status,
        risk_after="YELLOW",
        started_at=_CREATED,
        ended_at=_CREATED,
        evidence={"verification": verification},
    )


def _ledger(verification: list, *, status: str = "completed", requires_approval: bool = True):
    return build_run_ledger(
        contract=_contract(requires_approval=requires_approval),
        handle=_HANDLE,
        result=_result(verification, status=status),
        created_at=_CREATED,
    )


# --- ledger carries typed strength (weakest-link, fail-closed) ----------------

def test_run_ledger_strong_verification_is_strong() -> None:
    assert _ledger(STRONG_V).verification["strength"] == "STRONG"


def test_run_ledger_weak_verification_is_weak() -> None:
    assert _ledger(WEAK_V).verification["strength"] == "WEAK"


def test_run_ledger_failed_verification_is_none() -> None:
    assert _ledger(FAILED_V, status="failed").verification["strength"] == "NONE"


def test_run_ledger_empty_verification_is_none() -> None:
    assert _ledger([]).verification["strength"] == "NONE"


def test_run_ledger_mixed_strength_takes_the_weakest() -> None:
    # One STRONG check cannot launder a WEAK sibling.
    assert _ledger(MIXED_V).verification["strength"] == "WEAK"


def test_run_ledger_preserves_the_command_evidence() -> None:
    ledger = _ledger(STRONG_V)
    assert ledger.verification["commands"] == STRONG_V  # existing evidence untouched


# --- King report flags below-floor approvals (the acceptance) -----------------

def test_king_report_flags_approve_on_weak_evidence() -> None:
    report = build_king_report(ledger=_ledger(WEAK_V), result=_result(WEAK_V))
    assert report.recommendation == "approve"
    assert report.verification_result["strength"] == "WEAK"
    assert report.verification_result["meets_floor"] is False
    assert "below_floor_warning" in report.verification_result
    assert "weak verification" in report.human_summary.lower()


def test_king_report_does_not_flag_approve_on_strong_evidence() -> None:
    report = build_king_report(ledger=_ledger(STRONG_V), result=_result(STRONG_V))
    assert report.recommendation == "approve"
    assert report.verification_result["strength"] == "STRONG"
    assert report.verification_result["meets_floor"] is True
    assert "below_floor_warning" not in report.verification_result


def test_king_report_flags_weak_auto_observe() -> None:
    # A weak AUTO-proceed (no approval needed) is as dishonest as a weak approve.
    ledger = _ledger(WEAK_V, requires_approval=False)
    report = build_king_report(ledger=ledger, result=_result(WEAK_V))
    assert report.recommendation == "observe"
    assert report.verification_result["meets_floor"] is False
    assert "below_floor_warning" in report.verification_result
