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
AIOS = REPO_ROOT / "aios"

#: Constructions that carry authority to act and must therefore be haltable.
#:
#: WIDENED 2026-09-08, from three names to nine. Three was not a considered
#: scope -- it was simply the set that existed when the rule was written, and it
#: is why four LIVE production gaps passed CI: `deps.py` twice and the council
#: approve/reject routes twice all built a `MissionService` with no latch, and
#: no rule looked at `MissionService`.
#:
#: The scan reads `aios/` only, so widening this costs nothing in test churn and
#: buys the thing that actually prevents recurrence: a production construction
#: that forgets its stop fails CI at the construction site, rather than at
#: whichever runtime call happens to be exercised first.
_GOVERNED = {
    "Executor",
    "AutonomyLedger",
    "SelfApplyEngine",
    "CouncilOrchestrator",
    "MissionService",
    "MissionAuthority",
    "PromotionAuthority",
    "WorkerFoundry",
    "WorkerScheduler",
    "GovernedAutonomy",
}

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
    # The last-resort branch of `kernel._default_autonomy_ledger`, reached only
    # when no emergency stop can be obtained at all. A bare ledger now REFUSES
    # rather than grants -- `is_earned` treats an absent latch as a denial --
    # so failing closed here beats failing to construct the kernel. The marker
    # comment is required on the line so the exemption is argued at the site,
    # not merely listed here.
    ("AutonomyLedger", "refuses-when-unwired"),
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


def test_every_governed_construction_names_a_stop() -> None:
    """THE RULE the reviewer asked for, and the one that was missing.

    REPO-WIDE since 2026-09-07, and the reason is a defect this rule missed.

    It scanned `deps.py` only. `aios/policy/kernel.py` built bare stopless
    autonomy ledgers as fallbacks -- and `is_earned` skipped its latch check
    when none was wired -- so an engaged emergency stop did not deny COMMAND
    autonomy. Fourth appearance of the shape, in a file the rule never looked
    at.

    A rule scoped to one file only proves things about that file. An omission
    must fail a test wherever it is written, not wait for someone to read the
    diff carefully.
    """
    unguarded = []
    for path in sorted(AIOS.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for name, line, has_stop, segment in _governed_calls(source):
            if has_stop:
                continue
            if any(name == jname and jhint in segment for jname, jhint in _JUSTIFIED):
                continue
            unguarded.append(f"{name} at {rel}:{line}")

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

#: Measured 2026-09-07: 15 actual `if ... is not None:` guards.
#:
#: Was 18 while the census counted docstring mentions as guards -- three
#: units of slack in a ratchet whose whole purpose is to have none. Then 15,
#: where it sat pinned-but-unconverted.
#:
#: NOW DESCENDING. The conversion is under way, one subsystem per commit, and
#: `test_the_budget_is_not_stale` forces this number down with each: a slice
#: that flips a guard and leaves the budget alone fails its own suite.
#:
#: 15 -> 13: `GovernedAutonomy.evaluate` converted to `stop_permits_autonomy`,
#: and `aios/api/deps.py`'s singleton fast path recognised as never having been
#: a guard at all (see `_NOT_A_GUARD`). The target is 0, and because that one
#: coincidence is exempted rather than tolerated, 0 will mean it.
#:
#: 13 -> 10: all three `intelligence/gateway.py` guards converted to
#: `require_wired`. Three rather than one because the two anonymous
#: compatibility entrances do NOT pass through `_validate_and_compile`, so
#: fixing the shared guard alone would have left them open.
#:
#: 10 -> 9: `IntelligenceHiringService.complete`. It was the one instance
#: carrying a written justification, and that justification was circular -- it
#: called gateway.py's pattern "established" while gateway.py's three were
#: themselves undocumented holes on this same list. Converting them expired the
#: reason, so the last "deliberate" optional guard is gone too.
#: 9 -> 8: `activate_amendment`. Slice 27 had NAMED this a required
#: emergency-stop boundary, and the guard written to satisfy that requirement
#: skipped itself whenever nothing was wired -- the boundary existed only for
#: callers that already had a latch.
#: 8 -> 6: the worker pair. One slice for two guards because they are one
#: path -- `WorkerFoundry` builds its own `WorkerScheduler` and hands its stop
#: down, so converting either alone leaves the pair half-governed. Neither had
#: ANY engaged-stop test at its own layer before this.
#: 6 -> 2: the council cluster, converted together because it is not
#: separable. `CouncilOrchestrator` builds a `MissionService`, a
#: `WorkerFoundry` (which builds a `WorkerScheduler`) and a
#: `PromotionAuthority`, threading its own stop into each. Declaring the
#: fixture opt-out at the council made its children choke on the sentinel
#: string, so converting one at a time could not leave the tree green. Four
#: LIVE production gaps were closed with it -- deps.py x2 and the council
#: approve/reject routes x2 all built MissionService with no latch at all.
#:
#: Only aios/core/executor.py remains.
#: 2 -> 0. `aios/core/executor.py`, both entrances. This is the guard the whole
#: effort started from: `replay_writes.py`'s docstring names it as the known,
#: unfixed instance of the shape, and `require_wired`'s docstring argued it
#: should stay because that file was "FOUNDATION_LOCK'd" -- a claim AGENTS.md
#: SVIII does not support and which the operator ruled stale.
#:
#: ZERO, and it means zero: the one line that matches this text without being a
#: guard is exempted by name in `_NOT_A_GUARD` with its reason, rather than
#: being left as a unit of permanent slack.
_OPTIONAL_GUARD_BUDGET = 0


#: Lines that MATCH the guard text but are not governance guards, with counts.
#:
#: The census is a text scan, so it cannot tell a gate from a coincidence. There
#: is exactly one coincidence: `get_emergency_stop()` in `aios/api/deps.py` is
#: the stop's OWN constructor, and its `if _emergency_stop is not None:` is the
#: fast path of a double-checked lock. It decides whether a lock is taken, not
#: whether a privileged action proceeds; deleting it would cost a lock
#: acquisition and change no behaviour.
#:
#: Exempting it is what lets the budget reach a truthful ZERO instead of
#: flooring at 1 on a line that was never the defect. It is spelled out here,
#: with its reason, rather than absorbed as permanent slack -- the same standard
#: `_JUSTIFIED` applies to construction sites.
_NOT_A_GUARD = {"aios/api/deps.py": 1}


def _guard_census() -> dict[str, int]:
    """Count the GUARDS, not the prose that discusses them.

    The first version of this counted every occurrence of the string, including
    three docstring and comment mentions explaining the defect. The budget was
    therefore three units too high -- silent slack that would have absorbed the
    next real omission without anyone noticing, which is exactly what
    `test_the_budget_is_not_stale` below exists to prevent. Counting prose as
    if it were code is the same mistake this file catches elsewhere.
    """
    census: dict[str, int] = {}
    for path in sorted((REPO_ROOT / "aios").rglob("*.py")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        count = sum(
            1
            for ln in lines
            if "emergency_stop is not None" in ln and ln.strip().startswith("if ")
        )
        relative = path.relative_to(REPO_ROOT).as_posix()
        # Clamped at zero. `count` went NEGATIVE when the exempted line was
        # removed, and `if count:` treats -1 as truthy -- so the census
        # recorded -1, and `test_the_budget_is_not_stale` demanded the
        # budget be lowered to -1. A legitimate refactor would have been
        # blocked by a nonsense number.
        count = max(0, count - _NOT_A_GUARD.get(relative, 0))
        if count:
            census[relative] = count
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


# --------------------------------------------------------------------------- #
# The AST census
#
# WHY A SECOND ONE. `_guard_census` above is a TEXT scan, and a text scan can
# only refuse the exact spelling it was taught. Probed on 2026-09-12 with nine
# ways of writing the same fail-open guard, it caught two:
#
#     if self.emergency_stop is not None:          CAUGHT
#     if self.emergency_stop is not None and x:    CAUGHT
#     if None is not self.emergency_stop:          evades
#     if self.emergency_stop:                      evades
#     if getattr(self, "emergency_stop", None):    evades
#     stop = self.emergency_stop; if stop:         evades
#     if (\n    self.emergency_stop is not None\n) evades
#     ... if self.emergency_stop is not None else  evades
#     if self.emergency_stop is None: return       evades
#
# Most of those are not adversarial. A local alias, an early return and a
# wrapped condition are what someone writes by accident, which makes a ratchet
# that misses them a ratchet in name only. This one works on the tree, so
# spelling, line breaks and variable names do not matter.
# --------------------------------------------------------------------------- #

#: Names that refer to an emergency stop, however they are spelled.
_STOP_NAMES = ("emergency_stop", "_emergency_stop")


def _mentions_stop(node: ast.AST, aliases: set[str]) -> bool:
    """Does this expression read an emergency stop, directly or via an alias?"""
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr in _STOP_NAMES:
            return True
        if isinstance(child, ast.Name) and (
            child.id in _STOP_NAMES or child.id in aliases
        ):
            return True
        # getattr(self, "emergency_stop", None) -- the absence is baked into the
        # call, which is the most deniable spelling of all.
        if isinstance(child, ast.Call) and getattr(child.func, "id", None) == "getattr":
            for arg in child.args:
                if isinstance(arg, ast.Constant) and arg.value in _STOP_NAMES:
                    return True
    return False


def _checks_the_stop(node: ast.AST) -> bool:
    """Does this block actually perform the stop check?"""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = getattr(child.func, "attr", None) or getattr(child.func, "id", None)
            if name in ("assert_operational", "require_stop_wired", "require_wired"):
                return True
    return False


def _stop_aliases(fn: ast.AST) -> set[str]:
    """Locals bound to an emergency stop: `stop = self.emergency_stop`."""
    aliases: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if value is None or not _mentions_stop(value, set()):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                aliases.add(target.id)
    return aliases


def _fail_open_guards(source: str) -> list[tuple[int, str]]:
    """Every conditional that makes the stop check SKIPPABLE.

    Two shapes, both of which mean "if no latch is wired, do not check":

    * a conditional on the stop's presence whose body contains the check and
      which has no `else` -- so an absent latch falls straight through;
    * an early `return` when the stop is absent, which skips whatever check
      follows. A `raise` there is fail-CLOSED and is deliberately not flagged.
    """
    try:
        tree = ast.parse(source)
    except (
        SyntaxError
    ):  # pragma: no cover - a broken source file fails louder elsewhere
        return []

    # Deduplicated by line: `ast.walk` reaches the same `If` once per enclosing
    # scope (module AND function), so a single guard was counted twice and the
    # budget read 2 for one site.
    found: dict[int, str] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            continue
        aliases = _stop_aliases(fn)
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            if not _mentions_stop(node.test, aliases):
                continue

            if _checks_the_stop(node) and not node.orelse:
                found[node.lineno] = (
                    "stop check sits inside a presence test with no else"
                )
                continue

            # `if stop is None: return` -- absence skips whatever follows.
            #
            # Only a BARE return (or pass) counts. `return False` and
            # `return None` are how the fail-CLOSED helpers themselves answer
            # -- `stop_permits_autonomy` denies with False, `require_stop_wired`
            # acknowledges the sentinel with None -- and an earlier draft of
            # this rule flagged all three canonical helpers as defects. A rule
            # that cries wolf on the fix is worse than no rule.
            skips = any(
                (isinstance(stmt, ast.Return) and stmt.value is None)
                or isinstance(stmt, (ast.Pass, ast.Continue))
                for stmt in node.body
            )
            tests_absence = any(
                isinstance(cmp_node, ast.Compare)
                and any(isinstance(op, ast.Is) for op in cmp_node.ops)
                and any(
                    isinstance(c, ast.Constant) and c.value is None
                    for c in cmp_node.comparators
                )
                for cmp_node in ast.walk(node.test)
            )
            if skips and tests_absence:
                found[node.lineno] = "absent stop returns early, skipping the check"
    return sorted(found.items())


#: The one fail-open site the AST census knows about and has NOT converted.
#:
#: `EmergencyStopHardWiringAuthority.assert_operational` is lenient BY DESIGN --
#: `if emergency_stop is None: return` -- and 13 runtime boundaries call it:
#: aios/api/main.py x2, api/routes/actions.py, api/routes/council.py x3,
#: application/governance/emergency_stop.py, application/learning/service.py,
#: application/maintenance/service.py, operations/recovery.py,
#: runtime/intelligence_gateway.py, and twice inside authority.py itself.
#:
#: So the guard SHAPE reached zero while the PROPERTY did not: at those
#: thirteen boundaries an absent latch is still no question asked. The 2026-09-08
#: conversion fixed the `if X is not None:` spelling and never saw this one,
#: because the text census could not.
#:
#: Recorded as a counted budget rather than an exemption so it cannot quietly
#: grow, and so the number is readable by anyone who asks whether the job is
#: done. Its stated reason -- "hundreds of unit fixtures construct governed
#: objects without a latch" -- has largely expired now that ~220 of them declare
#: UNGOVERNED_FIXTURE explicitly.
#: CONVERTED 2026-09-12, same day it was found. `assert_operational` now
#: delegates to `require_stop_wired`, so all thirteen boundaries refuse an
#: absent latch and the three entrances to the rule are one implementation.
#:
#: ZERO in BOTH censuses now -- the shape and the property.
_LENIENT_FAIL_OPEN_BUDGET = 0


def _fail_open_census() -> dict[str, list[tuple[int, str]]]:
    census: dict[str, list[tuple[int, str]]] = {}
    for path in sorted((REPO_ROOT / "aios").rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits = _fail_open_guards(source)
        if hits:
            census[path.relative_to(REPO_ROOT).as_posix()] = hits
    return census


def test_no_fail_open_stop_guard_survives_in_any_spelling() -> None:
    """BUDGET ZERO, on the tree rather than on the text.

    The text census is kept beside this one because the two fail differently:
    text catches a marker the tree cannot see, and the tree catches every
    spelling text cannot. Neither alone is the rule.
    """
    census = _fail_open_census()
    total = sum(len(hits) for hits in census.values())

    assert total <= _LENIENT_FAIL_OPEN_BUDGET, (
        "fail-open emergency-stop guards found: "
        f"{census}\nAn absent latch is not a passed check. Use "
        "require_stop_wired() to refuse, or stop_permits_autonomy() where the "
        "caller must return a value rather than raise."
    )


def test_the_ast_census_catches_what_the_text_census_misses() -> None:
    """A rule is worth having only if it is shown to refuse something.

    Each of these is the SAME defect written a different way, and seven of the
    nine slipped past the text scan. This pins that the tree-based rule does not
    care how it is spelled.
    """
    variants = {
        "canonical": "if self.emergency_stop is not None:\n    self.emergency_stop.assert_operational()",
        "compound": "if self.emergency_stop is not None and ready:\n    self.emergency_stop.assert_operational()",
        "reversed": "if None is not self.emergency_stop:\n    self.emergency_stop.assert_operational()",
        "truthiness": "if self.emergency_stop:\n    self.emergency_stop.assert_operational()",
        "getattr": 'if getattr(self, "emergency_stop", None):\n    self.emergency_stop.assert_operational()',
        "local_alias": "stop = self.emergency_stop\nif stop is not None:\n    stop.assert_operational()",
        "wrapped": "if (\n    self.emergency_stop is not None\n):\n    self.emergency_stop.assert_operational()",
        "early_return": "if self.emergency_stop is None:\n    return\nself.emergency_stop.assert_operational()",
    }

    missed = [name for name, src in variants.items() if not _fail_open_guards(src)]

    assert not missed, f"these spellings of the fail-open guard are invisible: {missed}"


def test_the_ast_census_does_not_flag_the_converted_shape() -> None:
    """A rule that cries wolf on the fix is worse than no rule.

    `raise` on an absent stop is fail-CLOSED and must not be confused with the
    `return` that skips the check.
    """
    converted = {
        "require_stop_wired": 'require_stop_wired(self.emergency_stop, boundary="x")',
        "boolean_form": "if not stop_permits_autonomy(self.emergency_stop):\n    return BLOCKED",
        "raise_on_absence": 'if self.emergency_stop is None:\n    raise RuntimeError("no stop")\nself.emergency_stop.assert_operational()',
    }

    flagged = {name: _fail_open_guards(src) for name, src in converted.items()}
    flagged = {name: hits for name, hits in flagged.items() if hits}

    assert not flagged, f"the converted, fail-closed shape was flagged: {flagged}"
