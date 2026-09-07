"""Match against code, not against the prose that describes it.

WHY THIS EXISTS. A test that asserts a marker appears in a module's source is a
common and useful shape here -- it pins WHICH function a decision calls, which
is something a behavioural test cannot see when two functions return the same
type. But `inspect.getsource` returns docstrings and comments too, so:

    assert "if _halt_requires_stop():" in inspect.getsource(pipeline)

passes when that string appears only in a comment explaining the rule, while
the code calls something else entirely. The test reports a control it never
verified.

That is not hypothetical. In one day it happened three times:

* an AST rule matched its own docstring;
* a kernel test matched the docstring quoting the bug it checks;
* the emergency-stop guard ratchet counted three comments DESCRIBING the defect
  as instances of it -- three units of silent slack in a mechanism whose own
  companion test says "a ratchet nobody lowers becomes a ceiling nobody
  notices".

The direction matters. A negative assertion (`"bad" not in source`) fails
loudly on a docstring mention: annoying, but safe. A positive assertion
(`"good" in source`) PASSES on a docstring mention -- a false pass on a test
whose purpose is to verify a control. Those are the dangerous ones.
"""

from __future__ import annotations

import ast
import inspect
import io
import textwrap
import tokenize
from typing import Any


def strip_prose(source: str) -> str:
    """Return *source* with comments and docstrings removed.

    Two passes, each using the tool that cannot be fooled:

    * comments come from ``tokenize``, which knows a ``#`` inside a string
      literal is not a comment -- and several markers this suite matches on
      legitimately contain one (``"# noqa"``, shell commands, URLs);
    * docstrings come from the ``ast``, which is the only thing that actually
      knows what a docstring is.

    The first draft used a heuristic instead -- "a string is a docstring if it
    is the first meaningful token after a ``:``" -- and it ate the values out of
    dict literals (``{"a": "b"}`` lost ``"b"``), then emitted source that no
    longer parsed when a blanked docstring had been a block's only statement.
    It manufactured four failures that looked exactly like real findings. A
    helper whose whole job is to make matching honest has to be right about what
    it removes, so the heuristic is gone.

    Blank lines are left where prose was, so line numbers still line up with the
    original when a failure is being read.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # An un-tokenisable fragment is returned unchanged rather than silently
        # emptied: an empty haystack makes every positive assertion fail and
        # every negative one pass, which is the worst possible failure mode for
        # a helper meant to make matching honest.
        return source

    drop: set[int] = set()
    replace: dict[int, str] = {}
    lines = source.splitlines()
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        row, col = tok.start
        if col == 0 or not lines[row - 1][:col].strip():
            drop.add(row)  # whole-line comment
        else:
            # A TRAILING comment: cut the comment off and keep the code.
            # Blanking the line instead silently deletes the statement --
            # which is how this helper first produced source that no longer
            # parsed, and it looked like a finding rather than a bug.
            replace[row] = lines[row - 1][:col].rstrip()

    # `inspect.getsource` of a method is indented, so it is not a module on its
    # own; dedent before parsing. Dedenting does not move line numbers.
    try:
        tree = ast.parse(textwrap.dedent(source))
    except (SyntaxError, ValueError):
        # Comment stripping alone still beats raw source, and is always safe.
        return _blank(source, drop, replace)

    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
            continue
        if not isinstance(first.value.value, str):
            continue
        for line in range(first.lineno, first.end_lineno + 1):
            drop.add(line)
        if len(node.body) == 1 and not isinstance(node, ast.Module):
            # Blanking a block's only statement leaves a header with no body,
            # and callers parse this result. Keep it syntactically whole.
            replace[first.lineno] = " " * first.col_offset + "pass"

    return _blank(source, drop, replace)


def _blank(source: str, drop: set[int], replace: dict[int, str]) -> str:
    """Blank the *drop* lines of *source*, substituting *replace* where given."""
    return "\n".join(
        replace.get(lineno, "" if lineno in drop else line)
        for lineno, line in enumerate(source.splitlines(), start=1)
    )


def executable_source(obj: Any) -> str:
    """The source of *obj* with its docstrings and comments stripped.

    Use this instead of `inspect.getsource` whenever the result is searched for
    a marker. What is being asserted is that the CODE does something; prose
    describing it is not evidence.
    """
    return strip_prose(inspect.getsource(obj))


def calls_function(obj: Any, name: str) -> bool:
    """True when *obj*'s code contains a call to *name*.

    Stronger than a substring search, and the reason this module exists at all:
    a string match cannot tell `foo()` from `# we no longer call foo()`, while
    an AST walk sees only what runs. Falls back to a stripped-source search when
    the fragment cannot be parsed alone (a method's source is not a valid module
    on its own at some indentation levels).
    """
    source = executable_source(obj)
    try:
        tree = ast.parse(source.strip().replace("\n    ", "\n"))
    except (SyntaxError, ValueError):
        return f"{name}(" in source

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if called == name:
                return True
    return False
