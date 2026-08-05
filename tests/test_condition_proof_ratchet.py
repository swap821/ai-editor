"""C3/C4/C5 must point at something real, and the gap may only shrink.

Until this landed, the only mechanical check on C3 ("durable state survives
process restart"), C4 ("tamper-evidence / integrity chain") and C5 ("fail-safe
reporting: unavailable rather than a plausible zero") was ``len(text) >= 8``.
Those are the three conditions a hostile reviewer cares about most, and the
three that nothing enforced.

Enforcing them outright would demote all 46 greens on day one, so the gate
ratchets instead -- the same shape as the repo's existing monotonic frontend
warning budget. These tests hold that ratchet honest: the recorded budget can
never exceed its historical high-water mark, and the live gap can never exceed
the recorded budget.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from aios.application.governance.organ_ledger import load_ledger
from aios.domain.governance.contracts import OrganRecord

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
BUDGET_PATH = REPO_ROOT / ".aios" / "state" / "condition_proof_budget.json"

#: The number of greens lacking a C3/C4/C5 proof on the day the check landed.
#: The budget file may never record a number above this. Lowering this constant
#: is the deliberate act of ratcheting; raising it should never pass review.
_HIGH_WATER_MARK = 46

_spec = importlib.util.spec_from_file_location(
    "verify_organ_twelve_conditions",
    REPO_ROOT / "scripts" / "verify_organ_twelve_conditions.py",
)
v12 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(v12)


def _live_gap() -> dict[int, list[tuple[str, str]]]:
    """Greens with at least one C3/C4/C5 that names no referent at all.

    ``require_execution=False`` asks only "did this verdict name a referent",
    independent of any test run, so this test needs no pytest run of its own. A
    verdict that names a test still counts as a gap in the gate's REAL run if
    that test did not pass -- so this is a LOWER bound, the safe direction for a
    ratchet.

    That was always the stated intent. Until 2026-08-05 it passed ``results={}``
    instead, and the predicate scored a named-but-unexecuted proof as a failure.
    Since C5 has no N/A-BY-DESIGN clause, every organ must cite a test and every
    citation scored "did not execute" -- so no organ could ever be gap-free,
    ``len(gap)`` was identically the green count, and the ratchet's assertion
    reduced to ``greens <= 46``. It was a green-count cap wearing a proof
    ratchet's clothes, passing by the coincidence that 46 == 46, and no amount of
    proof work could ever move it. See test_the_measure_can_reach_zero below.
    """
    records = [r for r in load_ledger(LEDGER_PATH) if r.status == "green"]
    gaps = {
        r.organ_id: v12._condition_proof_failures(r, {}, require_execution=False)
        for r in records
    }
    return {k: v for k, v in gaps.items() if v}


def test_recorded_budget_never_exceeds_the_high_water_mark() -> None:
    budget = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    recorded = int(budget["greens_without_condition_proofs"])

    assert recorded <= _HIGH_WATER_MARK, (
        f"the C3/C4/C5 proof budget was raised to {recorded}, above the "
        f"{_HIGH_WATER_MARK} recorded when the check landed. The budget exists "
        "to shrink; raising it converts a real gate back into prose."
    )


def test_live_gap_does_not_exceed_the_recorded_budget() -> None:
    budget = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    recorded = int(budget["greens_without_condition_proofs"])
    gap = _live_gap()

    assert len(gap) <= recorded, (
        f"{len(gap)} greens now lack a C3/C4/C5 mechanical proof, above the "
        f"recorded budget of {recorded}. Either a green lost its proof, or a "
        f"new green landed without one: {sorted(gap)}"
    )


def test_c5_cannot_be_discharged_by_an_na_by_design_claim() -> None:
    """C5's definition carries no N/A-BY-DESIGN clause, unlike C3 and C4.

    This is the one place the three conditions genuinely differ, and it is
    worth pinning: granting C5 an escape hatch the contract never wrote would
    be exactly the quiet-loosening this gate exists to prevent.
    """
    record = OrganRecord(
        organ_id=1,
        name="Test",
        status="green",
        authority_owner="NobodyAuthority",
        condition_verdicts={
            "C3": "N/A-BY-DESIGN — aios/security/gateway.py::RateLimiter",
            "C4": "N/A-BY-DESIGN — aios/security/gateway.py::RateLimiter",
            "C5": "N/A-BY-DESIGN — aios/security/gateway.py::RateLimiter",
        },
    )

    failures = v12._condition_proof_failures(record, {})
    failed_conditions = {cond for cond, _ in failures}

    assert failed_conditions == {"C5"}, (
        f"C3/C4 may discharge with a cite and C5 may not; got {failures}"
    )


def test_a_named_proof_must_actually_have_passed() -> None:
    """Naming a test is not enough -- it must have run and passed.

    A file-level "no failures" would not catch a verdict citing a test that
    does not exist or that skipped, which is the whole reason the JUnit parser
    now records per-test names rather than counts alone.
    """
    record = OrganRecord(
        organ_id=1,
        name="Test",
        status="green",
        authority_owner="NobodyAuthority",
        condition_verdicts={
            "C3": "PASS — tests/test_thing.py::test_survives_restart",
            "C4": "N/A-BY-DESIGN — aios/security/gateway.py::RateLimiter",
            "C5": "PASS — tests/test_thing.py::test_reports_unavailable",
        },
    )

    # The file ran and had no failures, but neither named test is among the
    # tests that actually passed.
    results = {
        "tests/test_thing.py": {
            "passed": 3,
            "failed": 0,
            "skipped": 0,
            "passed_names": {"test_something_else"},
        }
    }

    failures = v12._condition_proof_failures(record, results)
    failed_conditions = {cond for cond, _ in failures}

    assert failed_conditions == {"C3", "C5"}, failures
    assert all("did not run and pass" in reason for _, reason in failures), failures


def test_a_named_proof_that_passed_satisfies_the_condition() -> None:
    record = OrganRecord(
        organ_id=1,
        name="Test",
        status="green",
        authority_owner="NobodyAuthority",
        condition_verdicts={
            "C3": "PASS — tests/test_thing.py::test_survives_restart",
            "C4": "N/A-BY-DESIGN — aios/security/gateway.py::RateLimiter",
            "C5": "PASS — tests/test_thing.py::test_reports_unavailable",
        },
    )
    results = {
        "tests/test_thing.py": {
            "passed": 2,
            "failed": 0,
            "skipped": 0,
            "passed_names": {"test_survives_restart", "test_reports_unavailable"},
        }
    }

    assert v12._condition_proof_failures(record, results) == []


# --------------------------------------------------------------------------- #
# The 2026-08-05 convergence fix. A ratchet that cannot reach zero is not a
# ratchet -- it is a cap on the thing it happens to be counting.
# --------------------------------------------------------------------------- #


def test_the_measure_can_reach_zero() -> None:
    """An organ that names every referent must be gap-free.

    This is THE assertion that proves the fix is real. Before it, no organ in the
    repository could ever be gap-free under the ratchet's own measurement: C5 has
    no N/A-BY-DESIGN clause, so every organ had to cite a test, and every citation
    scored "did not execute in this run" because the ratchet supplies no results.
    The live gap was therefore identically the green count, forever.
    """
    record = OrganRecord(
        organ_id=1,
        name="Fully proven",
        status="green",
        authority_owner="NobodyAuthority",
        condition_verdicts={
            "C3": "PASS — tests/test_thing.py::test_survives_restart",
            "C4": "N/A-BY-DESIGN — aios/security/gateway.py::RateLimiter",
            "C5": "PASS — tests/test_thing.py::test_reports_unavailable",
        },
    )
    assert v12._condition_proof_failures(record, {}, require_execution=False) == []


def test_a_well_proven_new_green_does_not_raise_the_live_gap() -> None:
    """The behaviour the ratchet was supposed to have all along.

    Adding a green organ that carries real referents must not consume budget.
    Under the old measurement it consumed one unit regardless of proof quality,
    which is why proof work could never lower the number and any new green broke
    the gate.
    """
    proven = OrganRecord(
        organ_id=54,  # OrganRecord validates 1..54; this row is synthetic
        name="Newly proven",
        status="green",
        authority_owner="NobodyAuthority",
        condition_verdicts={
            "C3": "PASS — tests/test_thing.py::test_survives_restart",
            "C4": "N/A-BY-DESIGN — aios/security/gateway.py::RateLimiter",
            "C5": "PASS — tests/test_thing.py::test_reports_unavailable",
        },
    )
    before = len(_live_gap())
    gaps = v12._condition_proof_failures(proven, {}, require_execution=False)
    assert gaps == []
    assert before == len(_live_gap()), "measuring must not mutate the live gap"


def test_the_ratchet_still_bites_on_a_missing_referent() -> None:
    """Loosening the execution check must not loosen the naming check."""
    record = OrganRecord(
        organ_id=1,
        name="Prose only",
        status="green",
        authority_owner="NobodyAuthority",
        condition_verdicts={
            "C3": "PASS — durable state survives restart",
            "C4": "N/A-BY-DESIGN — no journal to chain",
            "C5": "PASS — reports unavailable rather than a plausible zero",
        },
    )
    failures = v12._condition_proof_failures(record, {}, require_execution=False)
    failed = {cond for cond, _ in failures}
    assert failed == {"C3", "C4", "C5"}, failures


def test_the_real_gate_is_unchanged_and_still_requires_execution() -> None:
    """require_execution defaults True, so verify_organ_contracts is untouched.

    A verdict naming a test that did not run must still fail the real gate. If
    this ever passes, the fix leaked into the gate it was supposed to leave alone.
    """
    record = OrganRecord(
        organ_id=1,
        name="Cited but unrun",
        status="green",
        authority_owner="NobodyAuthority",
        condition_verdicts={
            "C3": "PASS — tests/test_thing.py::test_survives_restart",
            "C4": "N/A-BY-DESIGN — aios/security/gateway.py::RateLimiter",
            "C5": "PASS — tests/test_thing.py::test_reports_unavailable",
        },
    )
    failures = v12._condition_proof_failures(record, {})
    assert {cond for cond, _ in failures} == {"C3", "C5"}
    assert all("did not execute" in why for _, why in failures), failures
