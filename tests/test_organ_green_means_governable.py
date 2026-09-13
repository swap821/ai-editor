"""Green must mean the organ can actually be halted, and actually runs.

WHY THIS FILE EXISTS. Three PRs this week found live ungoverned production
objects inside organs the ledger called green. The sharpest case: organ 26's
authority owner is `EmergencyStopHardWiringAuthority`, and its own declared
`production_entrypoints` are -- exactly -- the eight files whose stop check
returned silently when no latch was wired. It declared C1-C12 PASS over thirteen
boundaries that could not be halted.

Nothing in C1-C12 asked the question that mattered. Every condition was
structural or citational: a class exists in a named file (C1), a test list is
non-empty (C2), cited files exist and their tests pass (C6/C7), an artifact
matches its own stamped commit (C10), a sha is an ancestor of HEAD (C11/C12).

Two conditions are strengthened here:

* **C2 as WRITTEN.** Its prose -- "a real API/mission/runtime path invokes the
  owner (not construct-in-test alone)" -- named the exact failure mode, while
  enforcing only that `focused_tests` was non-empty.
* **C5 extended to governability.** An organ cannot be green over a boundary an
  absent latch walks straight through.

BOTH FIND NOTHING TODAY -- measured 0 of 55 each. That is the honest result and
they are still worth having: they refuse the regression that just happened. The
crater in this pass comes entirely from the staleness rule (46 of 55), which
lives in tests/test_organ_attestation_currency.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "_verify_governable", REPO_ROOT / "scripts" / "verify_organ_twelve_conditions.py"
)
_verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)

_FAIL_OPEN = (
    "class Thing:\n"
    "    def act(self):\n"
    "        if self.emergency_stop is not None:\n"
    "            self.emergency_stop.assert_operational()\n"
    "        return self._do_the_privileged_thing()\n"
)

_FAIL_CLOSED = (
    "class Thing:\n"
    "    def act(self):\n"
    '        require_stop_wired(self.emergency_stop, boundary="thing")\n'
    "        return self._do_the_privileged_thing()\n"
)


def _record(**kwargs):
    base = dict(
        organ_id=999,
        name="probe",
        authority_owner="ProbeAuthority",
        production_entrypoints=[],
        last_verified_sha=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# C5 -- governability
# --------------------------------------------------------------------------- #


def test_an_organ_cannot_be_green_over_a_fail_open_boundary(tmp_path) -> None:
    """THE BAR. This is organ 26's situation, reproduced.

    An organ declares an entrypoint; that entrypoint contains a guard an absent
    latch walks straight through. Before this rule, every one of C1-C12 passed.
    """
    entry = tmp_path / "aios" / "thing.py"
    entry.parent.mkdir(parents=True)
    entry.write_text(_FAIL_OPEN, encoding="utf-8")

    failures = _verify._governability_failures(
        _record(production_entrypoints=["aios/thing.py"]), tmp_path
    )

    assert failures, "a fail-open boundary inside a declared entrypoint was allowed"
    condition, message = failures[0]
    assert condition == "C5"
    assert "fail-open" in message
    assert "aios/thing.py" in message


def test_the_converted_shape_is_not_flagged(tmp_path) -> None:
    """A rule that cries wolf on the fix is worse than no rule."""
    entry = tmp_path / "aios" / "thing.py"
    entry.parent.mkdir(parents=True)
    entry.write_text(_FAIL_CLOSED, encoding="utf-8")

    assert not _verify._governability_failures(
        _record(production_entrypoints=["aios/thing.py"]), tmp_path
    )


def test_a_missing_entrypoint_is_left_to_the_other_conditions(tmp_path) -> None:
    """Scoped deliberately -- C1 and C6 own a path that does not resolve."""
    assert not _verify._governability_failures(
        _record(production_entrypoints=["aios/does_not_exist.py"]), tmp_path
    )


# --------------------------------------------------------------------------- #
# C2 -- the owner must actually be reached by production code
# --------------------------------------------------------------------------- #


def test_an_owner_that_exists_only_in_tests_is_refused(tmp_path) -> None:
    """Exactly what C2's prose forbids, and what its enforcement permitted.

    The owner is defined and called -- but only inside a test file. The old
    enforcement (`focused_tests` non-empty) passed this without looking.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_probe.py").write_text(
        "class OnlyInTestsAuthority:\n    pass\n\n"
        "def test_it():\n    OnlyInTestsAuthority()\n",
        encoding="utf-8",
    )
    for base in ("aios", "scripts", "tools"):
        (tmp_path / base).mkdir(parents=True, exist_ok=True)
    _verify._production_symbols._cache = None

    failures = _verify._owner_reachability_failures(
        _record(authority_owner="OnlyInTestsAuthority"), tmp_path
    )
    _verify._production_symbols._cache = None

    assert failures, "an owner that exists only in tests satisfied C2"
    condition, message = failures[0]
    assert condition == "C2"
    assert "construct-in-test alone" in message


def test_an_owner_defined_in_production_is_accepted(tmp_path) -> None:
    """The counterpart: a real production definition must satisfy C2."""
    aios_dir = tmp_path / "aios"
    aios_dir.mkdir(parents=True)
    (aios_dir / "real.py").write_text(
        "class RealAuthority:\n    pass\n", encoding="utf-8"
    )
    for base in ("scripts", "tools"):
        (tmp_path / base).mkdir(parents=True, exist_ok=True)
    _verify._production_symbols._cache = None

    failures = _verify._owner_reachability_failures(
        _record(authority_owner="RealAuthority"), tmp_path
    )
    _verify._production_symbols._cache = None

    assert not failures


# --------------------------------------------------------------------------- #
# The shipped ledger
# --------------------------------------------------------------------------- #


def test_no_shipped_organ_fails_either_new_condition() -> None:
    """Both rules find NOTHING today. Reported as measured.

    A rule that finds nothing on its first run is usually a rule that does not
    work -- which is why the four tests above plant violations and watch these
    two refuse them. The production surface is polyglot: five organs are owned by
    frontend surfaces and three by runner scripts, so an earlier draft scoped to
    `aios/` alone reported eight false failures. Scope was corrected before the
    rule was written, not after it fired.
    """
    from aios.application.governance.organ_ledger import load_ledger

    ledger = load_ledger(REPO_ROOT / ".aios/state/ORGAN_GREEN_LEDGER.json")

    unreachable = [
        (r.organ_id, _verify._owner_reachability_failures(r, REPO_ROOT))
        for r in ledger
        if _verify._owner_reachability_failures(r, REPO_ROOT)
    ]
    ungovernable = [
        (r.organ_id, _verify._governability_failures(r, REPO_ROOT))
        for r in ledger
        if _verify._governability_failures(r, REPO_ROOT)
    ]

    assert not unreachable, (
        f"authority owners unreachable from production: {unreachable}"
    )
    assert not ungovernable, f"organs green over a fail-open boundary: {ungovernable}"
