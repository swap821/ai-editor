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
#: Keyed on the path RELATIVE TO tests/, not the bare filename: matching
#: `path.name` exempted any file so named anywhere under tests/, so
#: `tests/adversarial/source_rules.py` bought a silent exemption. An
#: allowlist anyone can join by choosing a filename is not an allowlist.
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


def test_a_docstring_that_also_carries_a_trailing_comment_is_stripped() -> None:
    """REGRESSION, and the worst of the set.

    A docstring line may also end in a comment. The comment pass writes a
    `replace` entry holding "the code in front of the comment" -- which on a
    docstring line IS the docstring -- and `_blank` lets replace beat drop, so
    the prose survived verbatim. That restores the exact false pass this module
    exists to remove.

    Found by adversarial review of the branch, not by the tests beside it: none
    of them put a comment and a docstring on the same line.
    """
    stripped = strip_prose(
        "def f():\n"
        '    """calls MARKER_FN as documentation"""  # noqa: D401\n'
        "    return real()\n"
    )

    assert "MARKER_FN" not in stripped
    assert "return real()" in stripped


def test_a_multiline_docstring_closing_on_a_comment_does_not_swallow_the_rest() -> None:
    """REGRESSION. The same conflict, but it corrupted the whole fragment.

    With a trailing comment on the CLOSING line, the interior blanked while the
    bare triple-quote was restored -- a dangling quote that swallowed every
    following line into one string literal, hiding real calls from any later
    search or AST walk. `executable_source` is called on whole modules in this
    suite, so the swallowed code could be an unrelated function entirely.
    """
    stripped = strip_prose(
        "def f():\n"
        '    """\n'
        "    line MARKER\n"
        '    """  # note\n'
        "    return 1\n"
        "\n\n"
        "def other():\n"
        "    call_bad()\n"
    )

    ast.parse(stripped)
    assert "MARKER" not in stripped
    assert "call_bad()" in stripped, "a later function was swallowed by prose"


def test_pass_is_indented_to_the_original_not_the_dedented_source() -> None:
    """REGRESSION. `inspect.getsource` of a method is indented; the tree is not.

    The tree is parsed from a DEDENTED copy, so `col_offset` is 0 for a method
    whose real body sits deeper. Splicing that into the undedented source put
    `pass` at the same indent as its own `def`, and the result would not parse
    -- for every `executable_source(SomeClass.method)` call site in the suite.
    """
    source = '    def m(self):\n        """only a docstring"""\n'

    stripped = strip_prose(source)

    ast.parse(textwrap.dedent(stripped))
    assert "        pass" in stripped


def raw_source_uses(paths: list[Path]) -> list[tuple[str, int]]:
    """Every call to `inspect.getsource` in *paths*, as (file, line).

    Walks the AST, which is immune by construction to the defect it polices: a
    docstring naming `inspect.getsource` is a string constant, never a Call. A
    grep-based version of this rule would count its own explanation.
    """
    found: list[tuple[str, int]] = []
    for path in paths:
        try:
            relative = path.resolve().relative_to(REPO_ROOT / "tests").as_posix()
        except ValueError:
            relative = ""  # outside tests/: a planted file, never exempt
        if relative in _MAY_USE_RAW_SOURCE:
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
            # `inspect.getsource(x)` is an Attribute call, but a bare
            # `from inspect import getsource` makes a Name call and
            # `getattr(inspect, "getsource")(x)` hides the name in a
            # string. Matching only Attribute left both as free bypasses.
            if isinstance(func, ast.Attribute) and func.attr == "getsource":
                found.append((path.name, node.lineno))
            elif isinstance(func, ast.Name) and func.id == "getsource":
                found.append((path.name, node.lineno))
            elif isinstance(func, ast.Name) and func.id == "getattr":
                literals = [
                    a.value
                    for a in node.args
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                ]
                if "getsource" in literals:
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


def test_the_ratchet_sees_every_way_of_reaching_getsource(tmp_path) -> None:
    """REGRESSION. Matching only `X.getsource(...)` left two free bypasses.

    A bare import makes a Name call and `getattr` hides the name in a string;
    neither is an `ast.Attribute`, so both walked straight past the rule.
    """
    forms = {
        "attribute": "import inspect\ndef t():\n    inspect.getsource(open)\n",
        "aliased": "import inspect as i\ndef t():\n    i.getsource(open)\n",
        "bare": "from inspect import getsource\ndef t():\n    getsource(open)\n",
        "getattr": "import inspect\ndef t():\n    getattr(inspect, 'getsource')(open)\n",
    }

    for name, body in forms.items():
        planted = tmp_path / f"test_{name}.py"
        planted.write_text(body, encoding="utf-8")
        assert raw_source_uses([planted]), f"{name} form slipped past the ratchet"


def test_the_allowlist_cannot_be_joined_by_choosing_a_filename(tmp_path) -> None:
    """REGRESSION. It keyed on `path.name`, so any directory would do.

    `tests/adversarial/source_rules.py` was silently exempt from the scan.
    """
    impostor = tmp_path / "source_rules.py"
    impostor.write_text(
        "import inspect\ndef t():\n    inspect.getsource(open)\n", encoding="utf-8"
    )

    assert raw_source_uses([impostor])


def test_no_test_matches_raw_source() -> None:
    """BUDGET ZERO, and deliberately not a ratchet with slack.

    Unlike the optional-guard count -- where 15 real instances span ten governed
    subsystems and cannot be converted in one pass -- this one reached zero, so
    it is pinned there. `executable_source` is a drop-in; there is no cost to
    using it and no honest reason to add a raw one back.
    """
    offenders = raw_source_uses(sorted(REPO_ROOT.joinpath("tests").rglob("*.py")))

    assert not offenders, f"use executable_source() instead: {offenders}"
