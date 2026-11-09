#!/usr/bin/env python3
"""Measure GAGOS's cross-system consistency against its register.

The operator, 2026-11-04: "I want u to make my cross-system consistency of my
project 10/10 honestly 100%."

Why this exists
---------------
On 2026-11-03 alone, four defects had one shape: two parts of GAGOS each
derived the same fact and disagreed. The failover's list of cloud providers
lacked ``anthropic`` for weeks; the Codex sealing flags existed twice; the
counter could not reach the brains the workshop used; the privacy filter and
the sandbox's report disagreed about a test's name. None of them was a bug in
one place. Each was two places that nobody had made agree.

What is measured
----------------
``.aios/state/CONSISTENCY_REGISTER.json`` lists the facts that two or more
parts of GAGOS rely on, every place each one is derived, and its state:

* ``single``: one source; the other places import it, and a guard test fails
  when a second derivation appears;
* ``agreed``: derived in several places on purpose (a frontend and a backend,
  say); a guard test fails when they disagree;
* ``open``: neither, yet. It counts against the score.

A row is only as good as its claims, so this script checks each one: every
place's file exists and still names its symbol, and every guard test exists.
A row that claims a guard which is not there is an error, never a point.

The score is the share of rows that are ``single`` or ``agreed``. 100% means
every REGISTERED fact is guarded. A fact nobody registered is not measured,
and the report says so rather than claiming more.

The register is the authority and the doc's status region is generated from
it, the split ``scripts/build_organ_ledger_doc.py`` made for the organs:
history is prose, current status is generated.

Usage
-----
    python scripts/consistency_audit.py            # the score and the open rows
    python scripts/consistency_audit.py --write    # regenerate the doc's region
    python scripts/consistency_audit.py --check    # CI: a false claim or a stale doc fails
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / ".aios" / "state" / "CONSISTENCY_REGISTER.json"
DOC = ROOT / "docs" / "architecture" / "CONSISTENCY_REGISTER.md"
BEGIN = "<!-- BEGIN GENERATED: consistency-register -->"
END = "<!-- END GENERATED: consistency-register -->"

STATES = ("single", "agreed", "open")
COVERED = ("single", "agreed")

#: Where a hand-written list of provider names is looked for.
SCANNED = ("aios", "tools")


@dataclass(frozen=True)
class Row:
    id: str
    fact: str
    state: str
    places: tuple[str, ...]
    guards: tuple[str, ...]
    source: str | None
    note: str


@dataclass
class Audit:
    rows: list[Row]
    errors: list[str] = field(default_factory=list)

    @property
    def covered(self) -> list[Row]:
        return [r for r in self.rows if r.state in COVERED]

    @property
    def open(self) -> list[Row]:
        return [r for r in self.rows if r.state == "open"]

    @property
    def score(self) -> float:
        return 100.0 * len(self.covered) / len(self.rows) if self.rows else 0.0


def _split(ref: str) -> tuple[str, str | None]:
    path, _, symbol = ref.partition("::")
    return path, (symbol or None)


def _names(path: Path, symbol: str) -> bool:
    return (
        re.search(rf"\b{re.escape(symbol)}\b", path.read_text(encoding="utf-8"))
        is not None
    )


def _has_test(path: Path, name: str) -> bool:
    """A pytest function named *name*, or a vitest ``it``/``test`` titled *name*."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        pattern = rf"^\s*(async\s+)?def {re.escape(name)}\("
    else:
        pattern = rf"\b(it|test)\(\s*(['\"`]){re.escape(name)}\2"
    return re.search(pattern, text, re.M) is not None


def check_place(ref: str, root: Path = ROOT) -> str | None:
    """Why *ref* (``path`` or ``path::symbol``) does not hold, or None."""
    rel, symbol = _split(ref)
    path = root / rel
    if not path.is_file():
        return f"{rel} does not exist"
    if symbol and not _names(path, symbol):
        return f"{rel} no longer names {symbol}"
    return None


def check_guard(ref: str, root: Path = ROOT) -> str | None:
    """Why *ref* (``tests/x.py::test_name``) is not a real test, or None."""
    rel, name = _split(ref)
    path = root / rel
    if not path.is_file():
        return f"guard {rel} does not exist"
    if not name:
        return f"guard {rel} names no test"
    if not _has_test(path, name):
        return f"guard {rel} has no test {name}"
    return None


def load(register: Path = REGISTER) -> list[Row]:
    data = json.loads(register.read_text(encoding="utf-8"))
    return [
        Row(
            id=r["id"],
            fact=r["fact"],
            state=r["state"],
            places=tuple(r.get("places", ())),
            guards=tuple(r.get("guards", ())),
            source=r.get("source"),
            note=r.get("note", ""),
        )
        for r in data["rows"]
    ]


def audit(rows: list[Row], root: Path = ROOT) -> Audit:
    result = Audit(rows)
    seen: set[str] = set()
    for row in rows:
        where = f"row {row.id}"
        if row.id in seen:
            result.errors.append(f"{where}: the id is used twice")
        seen.add(row.id)
        if row.state not in STATES:
            result.errors.append(f"{where}: state {row.state!r} is not one of {STATES}")
        if len(row.places) < 2 and row.state != "single":
            result.errors.append(f"{where}: a shared fact names two places or more")
        for ref in row.places:
            problem = check_place(ref, root)
            if problem:
                result.errors.append(f"{where}: {problem}")
        if row.state in COVERED and not row.guards:
            result.errors.append(f"{where}: {row.state} claims a guard and names none")
        for ref in row.guards:
            problem = check_guard(ref, root)
            if problem:
                result.errors.append(f"{where}: {problem}")
        if row.state == "single":
            if not row.source:
                result.errors.append(f"{where}: single names no source")
            elif row.source not in row.places:
                result.errors.append(f"{where}: its source is not one of its places")
    return result


def provider_names() -> frozenset[str]:
    """The provider names the router knows, read from its own constants."""
    sys.path.insert(0, str(ROOT))
    from aios.core import router

    return frozenset(
        value
        for key, value in vars(router).items()
        if key.startswith("PROVIDER_") and isinstance(value, str)
    )


def provider_lists(root: Path = ROOT, names: frozenset[str] | None = None) -> list[str]:
    """``file:line`` of every hand-written collection naming two providers or more.

    A tuple, list, set or dict literal whose string elements (or keys) include
    two of the router's provider names is a second copy of "which brains
    exist": the shape every 2026-11-03 drift had. Measured here; the guards
    that drive it to the one registry come with the registry itself.
    """
    names = names if names is not None else provider_names()
    found: list[str] = []
    for top in SCANNED:
        for path in sorted((root / top).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = path.relative_to(root).as_posix()
            lines = sorted(
                {
                    node.lineno
                    for node in ast.walk(tree)
                    if len(_named(node) & names) >= 2
                    or (rel != ROUTER and _copies_a_constant(node, names))
                }
            )
            found += [f"{rel}:{line}" for line in lines]
    return found


#: The one module whose ``PROVIDER_*`` constants are the names themselves.
ROUTER = "aios/core/router.py"


def _strings(nodes: list[ast.expr]) -> set[str]:
    return {
        n.value
        for n in nodes
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def _named(node: ast.AST) -> set[str]:
    """The strings a collection literal names: its elements, or its keys, or
    the first element of each pair in a tuple of pairs."""
    if isinstance(node, ast.Dict):
        return _strings([k for k in node.keys if k is not None])
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return set()
    firsts = [e.elts[0] for e in node.elts if isinstance(e, ast.Tuple) and e.elts]
    return _strings(node.elts) | _strings(firsts)


def _copies_a_constant(node: ast.AST, names: frozenset[str]) -> bool:
    """``PROVIDER_X = "bedrock"`` anywhere but the router: a copied constant."""
    return (
        isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id.startswith("PROVIDER_")
            for t in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and node.value.value in names
    )


def render(result: Audit, lists: list[str]) -> str:
    lines = [
        BEGIN,
        "",
        f"**Score: {len(result.covered)} of {len(result.rows)} registered facts "
        f"guarded ({result.score:.0f}%).** Generated by "
        "`python scripts/consistency_audit.py --write` from "
        "`.aios/state/CONSISTENCY_REGISTER.json`; do not edit by hand.",
        "",
        f"Hand-written lists of provider names in `aios/` and `tools/`: **{len(lists)}**.",
        "",
        "| Fact | State | Places | Guard |",
        "|---|---|---|---|",
    ]
    for row in sorted(result.rows, key=lambda r: (STATES.index(r.state), r.id)):
        places = "<br>".join(f"`{p}`" for p in row.places)
        guards = "<br>".join(f"`{g}`" for g in row.guards) or "none yet"
        fact = row.fact + (f" *{row.note}*" if row.note else "")
        lines.append(f"| **{row.id}**: {fact} | {row.state} | {places} | {guards} |")
    lines += ["", END]
    return "\n".join(lines)


def splice(doc_text: str, region: str) -> str:
    start, end = doc_text.find(BEGIN), doc_text.find(END)
    if start < 0 or end < start:
        raise SystemExit(f"{DOC.relative_to(ROOT)} has no generated region")
    return doc_text[:start] + region + doc_text[end + len(END) :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help="regenerate the doc's region"
    )
    mode.add_argument(
        "--check", action="store_true", help="fail on a false claim or a stale doc"
    )
    args = parser.parse_args(argv)

    result = audit(load())
    lists = provider_lists()
    for error in result.errors:
        print(f"ERROR {error}")
    print(
        f"consistency: {len(result.covered)} of {len(result.rows)} registered facts "
        f"guarded ({result.score:.0f}%); {len(result.open)} open"
    )
    for row in result.open:
        print(f"  open  {row.id}: {row.fact}")
    print(f"hand-written provider lists: {len(lists)}")
    for site in lists:
        print(f"  {site}")
    print("(a fact nobody registered is not measured)")

    doc_text = DOC.read_text(encoding="utf-8")
    current = splice(doc_text, render(result, lists))
    if args.write:
        DOC.write_text(current, encoding="utf-8", newline="\n")
        print(f"wrote {DOC.relative_to(ROOT)}")
    if args.check and current != doc_text:
        print(f"ERROR {DOC.relative_to(ROOT)} is stale: run with --write")
        return 1
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
