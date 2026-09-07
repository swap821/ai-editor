"""The prose/code helper must be right about what it removes -- and stay used.

WHY THIS EXISTS. `assert "X" in inspect.getsource(f)` passes when `X` appears
only in a comment or docstring while the code does something else. It is a false
pass on a test whose entire purpose is to verify a control, and it happened three
times in one day here: an AST rule matched its own docstring, a kernel test
matched the docstring quoting the bug it checks, and the emergency-stop ratchet
counted three comments DESCRIBING the defect as instances of it.

Two things are pinned below. First that `strip_prose` removes prose and nothing
else -- the first draft was a heuristic and it was wrong twice, in ways that
looked exactly like real findings (see the two regression tests). Second that
the suite keeps routing through it, because a helper nobody calls is not a
control.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

from tests.source_rules import calls_function, executable_source, strip_prose

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Raw `inspect.getsource` is legitimate here only: the helper implements it,
#: and this module needs it to demonstrate the contrast it exists to remove.
_MAY_USE_RAW_SOURCE = {"source_rules.py", "test_source_rules.py"}


def _decoy() -> bool:
    """Mentions the marker `if _halt_requires_stop():` without calling it."""
    # A comment can say `if _halt_requires_stop():` too.
    return True


def test_a_marker_that_lives_only_in_prose_no_longer_passes() -> None:
    """THE POINT, demonstrated rather than asserted.

    `_decoy` names the marker twice -- once in its docstring, once in a comment
    -- and never runs it. Raw source cannot tell the difference. That gap is the
    defect class, and it must be visible in one assertion.
    """
    marker = "if _halt_requires_stop():"

    assert marker in inspect.getsource(_decoy), "the decoy no longer decoys"
    assert marker not in executable_source(_decoy)
    assert not calls_function(_decoy, "_halt_requires_stop")


def test_dict_values_are_not_prose() -> None:
    """REGRESSION. The first draft ate them.

    It treated "first string after a colon" as a docstring, so `{"a": "b"}` lost
    `"b"`. Three suites failed with what looked exactly like genuine findings.
    """
    assert "kept" in strip_prose('x = {"a": "kept"}')


def test_a_trailing_comment_does_not_delete_its_line() -> None:
    """REGRESSION. The second draft deleted the code, not just the comment.

    Blanking the whole line where a comment STARTS removes any statement in
    front of it. That emptied blocks, so the stripped source no longer parsed --
    and the crash surfaced as a failing test rather than as a bug in here.
    """
    stripped = strip_prose("value = compute()  # explanatory note")

    assert "value = compute()" in stripped
    assert "explanatory note" not in stripped


def test_output_still_parses_when_a_docstring_was_the_only_statement() -> None:
    """Callers feed this to `ast.parse`; a body cannot be left empty."""
    for source in ('def f():\n    """only"""\n', 'class C:\n    """only"""\n'):
        ast.parse(textwrap.dedent(strip_prose(source)))


def test_unparseable_source_is_returned_unchanged() -> None:
    """Fail towards the old behaviour, never towards an empty haystack.

    An empty string makes every positive assertion fail and every negative one
    pass -- silently inverting the suite this helper is meant to protect.
    """
    fragment = "    if x:\n        return  # dangling fragment\n"

    assert strip_prose("def (((") == "def ((("
    assert "if x:" in strip_prose(fragment)


def raw_source_uses(paths: list[Path]) -> list[tuple[str, int]]:
    """Every call to `inspect.getsource` in *paths*, as (file, line).

    Walks the AST, which is immune by construction to the defect it polices: a
    docstring naming `inspect.getsource` is a string constant, never a Call. A
    grep-based version of this rule would count its own explanation.
    """
    found: list[tuple[str, int]] = []
    for path in paths:
        if path.name in _MAY_USE_RAW_SOURCE:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (
            SyntaxError
        ):  # pragma: no cover - a broken test file fails louder elsewhere
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "getsource":
                found.append((path.name, node.lineno))
    return found


def test_the_ratchet_refuses_a_newly_added_raw_source_assertion(tmp_path) -> None:
    """A ratchet is only worth having if it is shown to bite.

    This is the exact line someone would write next month, and the rule has to
    catch it in a file it has never seen.
    """
    planted = tmp_path / "test_planted.py"
    planted.write_text(
        "import inspect\n"
        "def test_x():\n"
        "    assert 'marker' in inspect.getsource(open)\n",
        encoding="utf-8",
    )

    assert raw_source_uses([planted]) == [("test_planted.py", 3)]


def test_no_test_matches_raw_source() -> None:
    """BUDGET ZERO, and deliberately not a ratchet with slack.

    Unlike the optional-guard count -- where 15 real instances span ten governed
    subsystems and cannot be converted in one pass -- this one reached zero, so
    it is pinned there. `executable_source` is a drop-in; there is no cost to
    using it and no honest reason to add a raw one back.
    """
    offenders = raw_source_uses(sorted(REPO_ROOT.joinpath("tests").rglob("*.py")))

    assert not offenders, f"use executable_source() instead: {offenders}"
