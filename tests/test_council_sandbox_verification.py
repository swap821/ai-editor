"""A council mission verified by the workshop's sandbox (2026-11-12).

Every frontend test command is RED at the security gateway, and the Planner
defers a mission without verification, so council missions could verify only
Python work. A mission may now declare the sandbox as its verification
(``aios.council.sandbox_spec``); the worker records the sandbox's verdict in
its run ledger (``sandbox_tests.ledger_entry``), and the Testing Queen and
organ 15 grade it by the runner that really ran, never better than it was.
"""

from __future__ import annotations

import pytest

from aios.council.queens.planner import CouncilMissionRequest, PlannerQueen
from aios.council.queens.security import SecurityQueen
from aios.council.queens.testing import TestingQueen
from aios.core.verification_strength import VerificationStrength
from aios.maintenance import sandbox_tests as sb
from aios.maintenance.sandbox_tests import SandboxVerdict

FILE = "frontend/src/superbrain/lib/tabStore.test.ts"


def _request(**kw) -> CouncilMissionRequest:
    base = {
        "mission_id": "goal-gt-1",
        "goal": "add a bound test",
        "workspace_root": ".",
        "allowed_files": [FILE],
        "allowed_tools": ["read_file", "write_file"],
        "metadata": {"sandbox_verification": {"files": [FILE]}},
    }
    return CouncilMissionRequest(**{**base, **kw})


def _contract(**kw):
    return PlannerQueen().draft(_request(**kw)).contract


class _Ledger:
    def __init__(self, *entries) -> None:
        self.verification = {"commands": list(entries)}


def _testing(entry):
    return TestingQueen().verify(contract=_contract(), ledger=_Ledger(entry))


# -- the planner ------------------------------------------------------------------


def test_a_declared_sandbox_is_a_verification_for_the_planner() -> None:
    draft = PlannerQueen().draft(_request())
    assert draft.verdict.verdict != "defer"


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"sandbox_verification": {"files": []}},
        {"sandbox_verification": {"files": "frontend/src/x.ts"}},
        {"sandbox_verification": ["frontend/src/x.ts"]},
        {"sandbox_verification": {"files": [""]}},
    ],
)
def test_no_or_a_malformed_sandbox_still_defers(metadata) -> None:
    assert PlannerQueen().draft(_request(metadata=metadata)).verdict.verdict == "defer"


# -- the security queen ----------------------------------------------------------


def test_a_sandbox_over_the_missions_own_files_passes_review() -> None:
    verdict = SecurityQueen().review(_contract())
    assert verdict.verdict != "deny", verdict.reason
    kinds = [c["kind"] for c in verdict.metadata["gateway_checks"]]
    assert "sandbox_verification" in kinds


@pytest.mark.parametrize(
    "files,why",
    [
        (["frontend/src/other.ts"], "outside the mission"),
        (["aios/security/gateway.py"], "outside the mission"),
        (["../outside.ts"], "outside the mission"),
        ([], "Malformed"),
    ],
)
def test_a_sandbox_outside_the_mission_is_denied(files, why) -> None:
    contract = _contract(metadata={"sandbox_verification": {"files": files}})
    verdict = SecurityQueen().review(contract)
    assert verdict.verdict == "deny"
    assert why in verdict.reason


# -- the ledger entry, graded honestly ---------------------------------------------


def _passed(**kw) -> SandboxVerdict:
    base = {
        "outcome": sb.PASSED,
        "summary": "12 tests in 1 files pass",
        "tests": (FILE,),
        "passed_count": 12,
    }
    return SandboxVerdict(**{**base, **kw})


def test_a_passed_frontend_sandbox_is_strong_under_vitests_own_command() -> None:
    entry = sb.ledger_entry(_passed(), rels=[FILE])
    assert entry["command"] == (
        "node node_modules/vitest/vitest.mjs related src/superbrain/lib/tabStore.test.ts --run"
    )
    assert entry["returncode"] == 0
    verdict = _testing(entry)
    assert verdict.verdict == "allow"
    assert verdict.metadata["verification_strength"] == VerificationStrength.STRONG.name


def test_failures_without_the_change_too_keep_it_below_strong() -> None:
    entry = sb.ledger_entry(
        _passed(failing_anyway=("a.test.ts::old",), failed_count=1), rels=[FILE]
    )
    verdict = _testing(entry)
    assert verdict.metadata["verification_strength"] == VerificationStrength.WEAK.name


@pytest.mark.parametrize(
    "outcome,exit_code",
    [
        (sb.BROKE, 1),
        (sb.UNTESTED, sb.UNTESTED_EXIT),
        (sb.UNAVAILABLE, sb.UNAVAILABLE_EXIT),
    ],
)
def test_anything_but_a_pass_is_not_a_pass(outcome, exit_code) -> None:
    entry = sb.ledger_entry(SandboxVerdict(outcome, "why", passed_count=0), rels=[FILE])
    assert entry["returncode"] == exit_code
    assert _testing(entry).verdict == "deny"


def test_a_python_change_is_recorded_under_pytest() -> None:
    entry = sb.ledger_entry(
        _passed(tests=("tests/test_x.py",)), rels=["aios/maintenance/daily_work.py"]
    )
    assert entry["command"] == "python -m pytest -q tests/test_x.py"
    assert _testing(entry).metadata["verification_strength"] == "STRONG"


def test_a_change_of_both_kinds_can_never_be_strong() -> None:
    entry = sb.ledger_entry(_passed(), rels=[FILE, "aios/maintenance/daily_work.py"])
    assert entry["command"].startswith("sandbox: ")
    assert _testing(entry).metadata["verification_strength"] == "WEAK"


def test_counts_survive_json_and_old_verdicts_still_load() -> None:
    verdict = _passed(failed_count=2)
    assert SandboxVerdict.from_json(verdict.to_json()) == verdict
    old = '{"outcome": "passed", "summary": "3 tests in 1 files pass", "tests": []}'
    assert SandboxVerdict.from_json(old).passed_count == 0
