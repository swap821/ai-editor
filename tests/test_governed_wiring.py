"""Every governed construction must name its emergency stop.

WHY THIS FILE EXISTS. The same defect has now been built three times:

    executor.py       `if self.emergency_stop is not None:`   (found by review)
    deps.py:1079      verify executor built with no stop      (found by an agent)
    replay_writes.py  the stop check skipped when absent      (found by review)

The third was written *after* `EmergencyStopHardWiringAuthority.require_wired`
existed to prevent exactly it, and after a docstring claiming it made "the
omission impossible to repeat". It did not, because `require_wired` had one
call site and nothing required its use.

A convention does not survive new code. These tests are the difference between
a rule and a habit: they fail on the next omission rather than waiting for a
reviewer to find it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPS = REPO_ROOT / "aios" / "api" / "deps.py"

#: Constructions that carry authority to act and must therefore be haltable.
_GOVERNED = {"Executor", "AutonomyLedger", "SelfApplyEngine"}

#: Constructions that legitimately do NOT name a stop, each with the reason.
#:
#: An allowlist rather than a blanket exemption: an exception has to be argued
#: in the diff, which is the whole difference between a decision and an
#: omission. Keyed by (name, line-independent justification) so a NEW omission
#: cannot hide behind an old one.
_JUSTIFIED = {
    # The stop's own revoker. `AutonomyLedger().revoke_all` is wired INTO the
    # emergency stop as the thing it calls when engaged; requiring it to hold a
    # stop would be circular. It only revokes -- it can never grant.
    ("AutonomyLedger", "revoke_all"),
    # Receives an already-wired executor. `SelfApplyEngine(verifier=Verifier(
    # verify_executor))` inherits governance from that executor, which is
    # itself built through `require_wired`.
    ("SelfApplyEngine", "verifier"),
}


def _governed_calls(source: str) -> list[tuple[str, int, bool, str]]:
    """Every governed construction, with the source line it sits on.

    The justification hint is matched against the LINE rather than against the
    AST, because the thing that justifies an exception is often not inside the
    call: `AutonomyLedger().revoke_all` is an attribute access ON the result,
    and `SelfApplyEngine(verifier=Verifier(executor))` is justified by what it
    is handed. Reading the line keeps the check honest about what it can see.
    """
    lines = source.splitlines()
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name not in _GOVERNED:
            continue
        kwargs = {k.arg for k in node.keywords if k.arg}
        start = max(node.lineno - 1, 0)
        end = min(getattr(node, "end_lineno", node.lineno), len(lines))
        segment = " ".join(lines[start:end])
        out.append((name, node.lineno, "emergency_stop" in kwargs, segment))
    return out


def test_every_governed_construction_in_deps_names_a_stop() -> None:
    """THE RULE the reviewer asked for, and the one that was missing.

    `deps.py` is where production wiring happens, so a forgotten stop here is a
    forgotten stop in the running system. An omission must fail a test, not
    wait for someone to read the diff carefully.
    """
    unguarded = []
    for name, line, has_stop, segment in _governed_calls(
        DEPS.read_text(encoding="utf-8")
    ):
        if has_stop:
            continue
        if any(name == jname and jhint in segment for jname, jhint in _JUSTIFIED):
            continue
        unguarded.append(f"{name} at deps.py:{line}")

    assert not unguarded, (
        "governed constructions with no emergency stop and no stated "
        f"justification: {unguarded}. Either wire it through "
        "EmergencyStopHardWiringAuthority.require_wired, or add it to "
        "_JUSTIFIED with the reason."
    )


def test_the_rule_catches_a_planted_omission() -> None:
    """A rule that has never refused anything is indistinguishable from a comment.

    `require_wired`'s docstring claimed it made the omission "impossible to
    repeat" while nothing enforced it. This asserts the check can actually fail,
    against a construction it has never seen.
    """
    planted = "def get_thing():\n    return Executor(runner=r, timeout_s=1)\n"

    offenders = [
        (name, line)
        for name, line, has_stop, _ in _governed_calls(planted)
        if not has_stop
    ]

    assert offenders, "the AST rule cannot detect a governed construction"


def test_a_justified_exception_is_still_recognised() -> None:
    """The allowlist must work, or the rule gets deleted the first time it bites."""
    ok = "AutonomyLedger().revoke_all\n"

    for name, _line, has_stop, segment in _governed_calls(ok):
        if has_stop:
            continue
        assert any(name == jname and jhint in segment for jname, jhint in _JUSTIFIED), (
            "the stop's own revoker is no longer recognised as justified"
        )


# --------------------------------------------------------------------------- #
# The ratchet
# --------------------------------------------------------------------------- #

#: Measured 2026-09-07, after the replay fix removed two.
#:
#: These are NOT all defects -- several are legitimately optional in their own
#: context -- and rewriting eighteen call sites across ten governed subsystems
#: is its own change with its own blast radius. What this pins is that the
#: SHAPE cannot grow: a nineteenth has to be argued rather than merely typed.
_OPTIONAL_GUARD_BUDGET = 18


def _guard_census() -> dict[str, int]:
    census: dict[str, int] = {}
    for path in sorted((REPO_ROOT / "aios").rglob("*.py")):
        count = path.read_text(encoding="utf-8").count("emergency_stop is not None")
        if count:
            census[path.relative_to(REPO_ROOT).as_posix()] = count
    return census


def test_the_optional_guard_shape_does_not_grow() -> None:
    """`if emergency_stop is not None:` treats an absent latch as a satisfied check.

    That is the shape behind all three defects. The budget is a ratchet, not an
    endorsement: it may fall freely, and it may not rise without someone
    deciding to raise it in this file.
    """
    census = _guard_census()
    total = sum(census.values())

    assert total <= _OPTIONAL_GUARD_BUDGET, (
        f"optional emergency-stop guards rose to {total} "
        f"(budget {_OPTIONAL_GUARD_BUDGET}).\n"
        "An absent latch is not a passed check. Require the stop, or take the "
        "explicit fixture opt-out.\n"
        f"census: {census}"
    )


def test_the_budget_is_not_stale() -> None:
    """A ratchet nobody lowers becomes a ceiling nobody notices.

    If the count has fallen, the budget should follow it down -- otherwise the
    slack silently permits the next omission.
    """
    total = sum(_guard_census().values())

    if total < _OPTIONAL_GUARD_BUDGET:
        pytest.fail(
            f"only {total} optional guards remain but the budget is "
            f"{_OPTIONAL_GUARD_BUDGET}; lower it to {total} so the slack cannot "
            "absorb a new one"
        )
