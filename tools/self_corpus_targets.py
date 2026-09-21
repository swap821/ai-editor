#!/usr/bin/env python3
"""Choose what GAGOS should reverse-engineer about itself — by a stated rule.

WHY A RULE AND NOT A LIST
-------------------------
The first temptation in a "let it learn from its own code" run is to hand-pick
targets that will obviously succeed. That produces a number and teaches nothing,
because the selection has done the work the agent was supposed to do. So the
rule is written down here, applied uniformly, and the ranking it produces is
reproducible: run it twice, get the same list.

WHAT MAKES A GOOD TARGET
------------------------
A function the agent can pin with a test that FAILS when the function breaks.
That rules out more than it sounds like:

* it must be importable without side effects — a module that opens a database or
  starts a client at import time cannot be exercised in a throwaway worktree;
* it must be callable with values a reader can construct from the signature
  alone — no fixtures, no live services, no `self` with state;
* it must actually RETURN something, because a test that pins a return value is
  the only kind the mutation control can verify (a function whose whole job is a
  side effect passes `raise NotImplementedError` detection only by accident);
* it must be reachable by `mutate_function` — module level, or one level into a
  class — or the negative control cannot be applied at all.

These are deliberately conservative. The point of the first organic run is a
signal that means something, not the widest possible net.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

#: Modules whose import does work rather than defining work. Excluded because a
#: throwaway worktree importing them would create databases, open sockets, or
#: read the operator's environment — and because a test over them is measuring
#: the fixture, not the function.
_EXCLUDED_PARTS = (
    "__pycache__",
    "migrations",
)
_EXCLUDED_PREFIXES = (
    # Frozen: proposals only, never edits, and never a training target.
    "aios/security/",
    # Import-time side effects: clients, sessions, DB handles.
    "aios/api/",
    "aios/infrastructure/",
)

#: Parameters whose presence means the caller needs context this rule cannot
#: guarantee a reader could construct.
_CONTEXTUAL_PARAMS = frozenset(
    {
        "self",
        "cls",
        "conn",
        "connection",
        "db",
        "db_path",
        "client",
        "session",
        "request",
        "app",
        "runtime",
        "ctx",
        "bus",
        "kernel",
        "authority",
    }
)


@dataclass(frozen=True)
class Target:
    """One function the agent will be asked to describe with a test."""

    module: str  # repo-relative path, posix
    function: str
    lineno: int
    params: tuple[str, ...]
    doc: str
    source: str

    @property
    def label(self) -> str:
        return f"{self.module}::{self.function}"


def _is_candidate_module(rel: str) -> bool:
    if any(part in rel for part in _EXCLUDED_PARTS):
        return False
    if any(rel.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
        return False
    return rel.startswith("aios/") and rel.endswith(".py")


def _module_has_import_time_work(tree: ast.Module) -> bool:
    """True when the module DOES something at import, not just defines things.

    Assignments, imports, docstrings, and simple constants are fine. A bare call
    at module level (``DATA_DIR.mkdir(...)``, ``load_dotenv(...)``) is not: in a
    throwaway worktree that call runs before a single test does.
    """
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return True
        if isinstance(node, (ast.For, ast.While, ast.With, ast.Try)):
            return True
    return False


def _returns_something(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when some path returns a value.

    A bare ``return`` or no return at all means the function's contract is a
    side effect, and the mutation control cannot distinguish a test that pins it
    from one that merely calls it.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value is not None:
            return True
    return False


def _params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    args = node.args
    names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    return tuple(names)


def collect_targets(root: Path, *, limit: int | None = None) -> list[Target]:
    """Every function in GAGOS that passes the rule, ranked reproducibly.

    Ranked by (fewest parameters, has a docstring, path, name) among functions
    that take at least one: a two-argument documented function is a better first
    target than a six-argument undocumented one, and the tie-breaks are
    lexicographic so the order never depends on filesystem iteration or a clock.
    """
    found: list[Target] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if not _is_candidate_module(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue
        if _module_has_import_time_work(tree):
            continue
        lines = text.splitlines(keepends=True)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(node, ast.AsyncFunctionDef):
                continue  # an async pin test needs a runner the grader does not set up
            if node.name.startswith("_"):
                continue  # private helpers are not the system's described behaviour
            params = _params(node)
            if set(params) & _CONTEXTUAL_PARAMS:
                continue
            if not params:
                # A zero-argument function's result is a function of GLOBAL
                # state -- a singleton accessor, a config read, a process
                # cache. A test over it pins the environment, not behaviour,
                # and the mutation control would be measuring whether the
                # module imported. The first pass ranked these highest purely
                # because "fewest parameters" sounded like "simplest"; they are
                # the opposite of what this needs.
                continue
            if not _returns_something(node):
                continue
            if node.decorator_list:
                continue  # a decorator can change the callable out from under the test
            source = "".join(lines[node.lineno - 1 : node.end_lineno])
            found.append(
                Target(
                    module=rel,
                    function=node.name,
                    lineno=node.lineno,
                    params=params,
                    doc=(ast.get_docstring(node) or "").strip(),
                    source=source,
                )
            )
    found.sort(key=lambda t: (len(t.params), not bool(t.doc), t.module, t.function))
    return found[:limit] if limit else found


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="List reverse-engineering targets.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()

    targets = collect_targets(args.root, limit=args.limit)
    print(f"{len(targets)} target(s), best first:\n")
    for t in targets:
        doc = (t.doc.splitlines()[0] if t.doc else "(undocumented)")[:60]
        print(f"  {t.label:<62} ({len(t.params)} param) {doc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
