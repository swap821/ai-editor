#!/usr/bin/env python3
"""Do the learning loop's guards bite? (plan Phase 7)

The question this answers
-------------------------
Every slice of the learning plan shipped with a mutation check: each guard it
added was broken on purpose and a named test had to fail. Those checks lived in
throwaway harnesses, one per slice, run once. This probe is the standing
version: ONE catalogue (``scripts/learning_mutation_catalogue.json``) of every
mutation that still applies to the code, re-run against the tree as it is now.

It reports two numbers, never one:

* **Kill score.** A mutation is killed only when its named tests FAIL (pytest
  exit 1). A collection error, a missing test or a crash is not a kill: those
  prove nothing about the guard, and the first spine probe scored a perfect
  4/4 on exactly such a path while running no detector at all.
* **Branch coverage of the guards it attacks.** For every function a mutation
  lands in, the probe enumerates the function's decision points -- each ``if``
  and ``while`` condition, each conditional expression, each comprehension
  filter -- and counts those a KILLED mutation attacks (its text overlaps the
  condition). A guard whose refusal branch nobody ever broke is reported by
  line, so "100% killed" can never hide an untested branch.

How it runs, and what it will not do
------------------------------------
Unlike the spine probe, which mutates ``aios/security/*`` in memory because
those files are frozen, the learning guards span stores, adapters and SQLite,
and other modules import them by name, so each mutation is applied to the file
on disk and restored in a ``finally``. To make that safe the probe REFUSES to
run if any target file has uncommitted changes, restores every file after each
mutation, and verifies at the end that every file is byte-identical to before.
Run it in a worktree you are not editing.

Usage
-----
    python scripts/learning_mutation_probe.py                # run all, report
    python scripts/learning_mutation_probe.py --only 4c,4c2  # some slices
    python scripts/learning_mutation_probe.py --check        # exit 1 on a survivor
    python scripts/learning_mutation_probe.py --json PATH    # write an evidence artifact
    python scripts/learning_mutation_probe.py --coverage     # coverage only, no runs
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = Path(__file__).with_name("learning_mutation_catalogue.json")
#: Batches of test node ids per pytest call (Windows caps a command line).
_NODE_BATCH = 40

#: Mutations known to change nothing a test could observe, each with the
#: reason. A survivor named here is reported INERT, never silently passed;
#: the catalogue keeps the entry.
INERT: dict[str, str] = {
    "gen:self_model_handler:SelfModelHandler.recall:117:never": (
        "recall(None) looks up a None key, and none is ever stored: __call__ "
        "returns before caching a turn that names no principal. The answer is "
        "None either way; the early return is defence in depth."
    ),
    "gen:tool_agent:ToolAgent._recall_taint:2044:never": (
        "with no taintable argument or no recalled memory, recall_envelope."
        "recall_taint finds nothing to match and returns [] -- the early return "
        "is a shortcut (checked directly: recall_taint('', m, o) == [] and "
        "recall_taint(c, '', o) == [])."
    ),
    "gen:tool_agent:ToolAgent._composition_capped:2004:never": (
        "a read carries no command, and the gateway refuses an empty one "
        "(_gateway_refuses({}) is True), so a read is never held at the cap "
        "even without the early return; the return states the rule."
    ),
    "gen:adapters:MistakeMemoryAdapter.promote:931:always": (
        "prior is read only for the attestation, and _attest returns at once "
        "when the adapter has no provenance writer: the value is never used."
    ),
    "gen:adapters:SemanticFactsAdapter._admitted_triples:396:never": (
        "an empty triple set joins nothing in json_each: the query returns no "
        "rows and the result is the same empty set; the return saves a query."
    ),
    "gen:adapters:SemanticFactsAdapter._admitted_triples:416:never": (
        "'the newest row decides': duplicate ACTIVE rows of one principal's "
        "triple cannot be written through the store (add_fact refuses them), "
        "and an older signed row of the same triple vouches for the same "
        "content (plan Phase 4c-3)."
    ),
    "gen:adapters:SemanticFactsAdapter.traverse_weighted:634:never": (
        "ungated, _admitted_triples admits every asked triple, and the store's "
        "walk returns only edges on paths from the start: sorted by depth, "
        "each edge's subject is already reached, so the filter keeps exactly "
        "the edges the shortcut returns."
    ),
    "gen:institutional_skills:InstitutionalSkillAdapter.record_reuse:715:never": (
        "forces the reason to 'verification' on a success too, and "
        "SkillLifecycleAuthority.apply_reuse_outcome reads the reason only on "
        "a failure (record_success takes none; demotion is skipped on success)."
    ),
    "gen:cerebellum:Cerebellum.match:749:never": (
        "a short-circuit: with no compiled playbook the loop adds no candidate "
        "and records no decision, so match returns None either way; the only "
        "work skipped is reading the library, and _activated swallows every "
        "error (it cannot raise)."
    ),
    "gen:cerebellum:Cerebellum._activated:562:always": (
        "the comprehension filter sits inside `if steps and all(step is not "
        "None for step in steps)`, so there every step is not None and the "
        "filter is already always true."
    ),
    "gen:reflex_contract:validated_version:161:always": (
        "a missing target is hashed through read_directory's deterministic "
        "refusal ('[ERROR] Not a directory: <target>', blocked) instead of "
        "'missing'. A version is only ever compared with one computed by the "
        "same function, so it stays a pure function of the target and its "
        "absence: staleness is unchanged."
    ),
    "gen:recall_envelope:model_visible:173:never": (
        "a short-circuit: _cloud_form('') is '' (the privacy filter leaves "
        "empty content empty, and on failure returns the text), so an empty "
        "text yields [text] either way."
    ),
    "gen:service:LearningService.activate_skill:381:always": (
        "stamp_for_activation returns the skill itself only when it changed "
        "nothing; saving that unchanged record is a no-op write "
        "SkillRepository.save allows in every activatable state (same state, "
        "no contract field rewritten)."
    ),
    "gen:service:LearningService.activate_skill:386:never": (
        "SkillRepository.transition_state returns the record in the target "
        "state or raises (KeyError, or check_transition's refusal); it never "
        "returns None or another state."
    ),
    "gen:turn_pipeline:_recall_memory:550:always": (
        "refine_context(query, []) is '' by its contract ('empty when there is "
        "no real content'), the value the guard yields."
    ),
    "gen:turn_pipeline:_recall_memory:561:always": (
        "trusted is never empty here: an empty one returned None at "
        "`if not hits` (hits = trusted), so the condition is already always "
        "true."
    ),
    "gen:turn_pipeline:_recall_memory:583:always": (
        "as _recall_memory:561 -- trusted is never empty at the plain block."
    ),
    # Plan Phase 0b (#372) made `unverified` the constant empty list: no
    # unverified memory is recalled into a prompt. The branches on it are dead
    # code kept for the CRAG block's shape; their ALWAYS mutations add an
    # empty unverified section and are killed by
    # test_no_recall_block_ever_carries_unverified_memory.
    "gen:turn_pipeline:_recall_memory:565:always": (
        "unverified is [] (Phase 0b), and refine_context(query, []) is ''."
    ),
    "gen:turn_pipeline:_recall_memory:565:never": (
        "unverified is [] (Phase 0b): the condition is already always false."
    ),
    "gen:turn_pipeline:_recall_memory:571:never": (
        "unverified_body is '' because unverified is [] (Phase 0b): the "
        "condition is already always false."
    ),
    "gen:turn_pipeline:_recall_memory:587:never": (
        "unverified is [] (Phase 0b): the condition is already always false."
    ),
    "gen:service:LearningService.activate_skill:391:never": (
        "as activate_skill:386 -- transition_state returns the record in the "
        "target state or raises."
    ),
}


class ProbeError(RuntimeError):
    """The probe could not run honestly. Never a silent pass."""


@dataclass
class Entry:
    id: str
    file: str
    old: str
    new: str
    tests: list[str]
    also: list[str] = field(default_factory=list)
    #: Why an entry differs from its slice's original (e.g. strengthened).
    note: str = ""

    @property
    def phase(self) -> str:
        return self.id.split(":", 1)[0]


@dataclass
class Result:
    id: str
    file: str
    applied: bool
    returncode: Optional[int] = None
    killed: bool = False
    survived: bool = False
    note: str = ""


def load(path: Path = CATALOGUE) -> list[Entry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Entry(**e) for e in data["entries"]]


def _normalised(path: Path) -> tuple[bytes, str, bool]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    return raw, text.replace("\r\n", "\n"), "\r\n" in text


def apply_mutation(text: str, entry: Entry) -> str:
    """The mutated text, or ProbeError if the anchor is not there exactly once
    (an ambiguous or missing anchor would mutate the wrong thing, or nothing)."""
    count = text.count(entry.old)
    if count != 1:
        raise ProbeError(f"anchor found {count} times in {entry.file}")
    return text.replace(entry.old, entry.new)


def killed(returncode: Optional[int]) -> bool:
    """Only a failing test is a kill (pytest exit 1). 2 is interrupted, 3
    internal error, 4 usage error, 5 nothing collected: none proves the
    guard was noticed."""
    return returncode == 1


# --------------------------------------------------------------------------- #
# Branch coverage
# --------------------------------------------------------------------------- #


@dataclass
class Decision:
    file: str
    function: str
    line: int
    source: str
    start: int
    end: int
    attacked_by: list[str] = field(default_factory=list)


def _offsets(text: str) -> list[int]:
    starts = [0]
    for line in text.split("\n"):
        starts.append(starts[-1] + len(line) + 1)
    return starts


def decisions_of(text: str, file: str) -> list[Decision]:
    """Every decision point inside every function of *text*: the conditions of
    ``if``/``while``, conditional expressions and comprehension filters. Each
    carries the character span of its CONDITION."""
    tree = ast.parse(text)
    starts = _offsets(text)
    lines = text.split("\n")
    out: list[Decision] = []

    def span(node: ast.AST) -> tuple[int, int]:
        return (
            starts[node.lineno - 1] + node.col_offset,  # type: ignore[attr-defined]
            starts[node.end_lineno - 1] + node.end_col_offset,  # type: ignore[attr-defined]
        )

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = function
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{function}.{child.name}" if function else child.name
            elif isinstance(child, ast.ClassDef):
                name = f"{function}.{child.name}" if function else child.name
            conditions: list[ast.AST] = []
            if isinstance(child, (ast.If, ast.While, ast.IfExp)):
                conditions.append(child.test)
            elif isinstance(child, ast.comprehension):
                conditions.extend(child.ifs)
            for condition in conditions:
                if function:
                    start, end = span(condition)
                    out.append(
                        Decision(
                            file=file,
                            function=function,
                            line=condition.lineno,  # type: ignore[attr-defined]
                            source=lines[condition.lineno - 1].strip()[:120],  # type: ignore[attr-defined]
                            start=start,
                            end=end,
                        )
                    )
            visit(child, name)

    visit(tree, "")
    return out


def function_at(text: str, offset: int) -> str:
    """The innermost function (qualified) containing *offset*, or ''."""
    tree = ast.parse(text)
    starts = _offsets(text)
    best = ("", -1)

    def visit(node: ast.AST, qual: str) -> None:
        nonlocal best
        for child in ast.iter_child_nodes(node):
            name = qual
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{qual}.{child.name}" if qual else child.name
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lo = starts[child.lineno - 1]
                    hi = starts[child.end_lineno - 1] + child.end_col_offset
                    if lo <= offset <= hi and lo > best[1]:
                        best = (name, lo)
            visit(child, name)

    visit(tree, "")
    return best[0]


def load_guards(path: Path = CATALOGUE) -> list[tuple[str, str]]:
    """The named guards: ``(file, qualified function)`` for every control the
    threat model lists (``guards`` in the catalogue, grouped by threat)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for names in data.get("guards", {}).values():
        for name in names:
            file, function = name.split("::", 1)
            out.append((file, function))
    return out


def coverage(
    entries: Sequence[Entry],
    killed_ids: Iterable[str],
    guards: Sequence[tuple[str, str]],
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """The decision points of every NAMED guard, and which a KILLED mutation
    attacks (its anchor overlaps the condition). A guard no mutation touches
    counts with all its decisions unattacked; a guard that no longer exists is
    reported missing, never skipped."""
    killed_set = set(killed_ids)
    texts: dict[str, str] = {}

    def text_of(file: str) -> str:
        if file not in texts:
            texts[file] = _normalised(root / file)[1]
        return texts[file]

    decisions: dict[tuple[str, str], list[Decision]] = {}
    missing: list[str] = []
    for file, function in guards:
        if not (root / file).is_file():
            missing.append(f"{file}::{function}")
            continue
        text = text_of(file)
        found = [d for d in decisions_of(text, file) if d.function == function]
        if not found and f"def {function.rsplit('.', 1)[-1]}(" not in text:
            missing.append(f"{file}::{function}")
            continue
        decisions[(file, function)] = found
    for entry in entries:
        if entry.id not in killed_set or not (root / entry.file).is_file():
            continue
        text = text_of(entry.file)
        at = text.find(entry.old)
        if at < 0:
            continue
        lo, hi = at, at + len(entry.old)
        for (file, _function), found in decisions.items():
            if file != entry.file:
                continue
            for decision in found:
                if lo < decision.end and decision.start < hi:
                    decision.attacked_by.append(entry.id)
    total = sum(len(ds) for ds in decisions.values())
    attacked = sum(1 for ds in decisions.values() for d in ds if d.attacked_by)
    unattacked = [
        {"file": d.file, "function": d.function, "line": d.line, "source": d.source}
        for ds in decisions.values()
        for d in ds
        if not d.attacked_by
    ]
    return {
        "guard_functions": len(decisions),
        "decision_points": total,
        "attacked": attacked,
        "unattacked": unattacked,
        "missing_guards": missing,
    }


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #


def _pytest(nodes: Sequence[str], python: str) -> int:
    return subprocess.run(
        [
            python,
            "-m",
            "pytest",
            *nodes,
            "-q",
            "-x",
            "-p",
            "no:cacheprovider",
            "--no-cov",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
    ).returncode


def _dirty(files: Iterable[str]) -> list[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--", *sorted(set(files))],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line[3:] for line in out.splitlines() if line.strip()]


def _journal() -> Path:
    """Where an in-flight mutation is recorded, with the file's original bytes,
    BEFORE the file is written: a run killed mid-mutation (a timeout, a closed
    terminal -- on Windows no handler runs) is restored by the next start."""
    return REPO_ROOT / ".aios" / "tmp" / "learning_probe_inflight.json"


def recover() -> Optional[str]:
    """Restore a mutation a killed run left on disk; the file restored, or None."""
    journal = _journal()
    if not journal.is_file():
        return None
    record = json.loads(journal.read_text(encoding="utf-8"))
    path = REPO_ROOT / record["file"]
    original = base64.b64decode(record["original"])
    if path.read_bytes() != original:
        path.write_bytes(original)
    journal.unlink()
    return str(record["file"])


def run(
    entries: Sequence[Entry],
    *,
    python: str = sys.executable,
    runner: Optional[Callable[[Sequence[str]], int]] = None,
    on_result: Optional[Callable[[Result], None]] = None,
    baseline: bool = True,
    deadline: Optional[float] = None,
) -> list[Result]:
    """Apply each mutation, run its tests, restore. *baseline* False is only
    for a caller that ran (and recorded) the baseline itself -- the ledger.
    With a *deadline* (``time.monotonic()``), no mutation STARTS after it, so a
    run never has to be killed mid-mutation to stop."""
    run_tests = runner or (lambda nodes: _pytest(nodes, python))
    restored = recover()
    if restored is not None:
        raise ProbeError(
            f"a previous run was killed mid-mutation; {restored} has been restored. "
            "Its results are void: re-run."
        )
    # EVERY catalogue target, not just this batch's: a file another run left
    # mutated would otherwise skew the tests this batch runs.
    targets = {e.file for e in entries}
    try:
        targets |= {e.file for e in load()}
    except FileNotFoundError:
        pass
    dirty = _dirty(targets)
    if dirty:
        raise ProbeError(
            f"refusing to mutate files with uncommitted changes: {dirty[:5]}"
        )
    if baseline:
        _baseline(sorted({t for e in entries for t in e.tests}), run_tests)
    before = {
        e.file: hashlib.sha256((REPO_ROOT / e.file).read_bytes()).hexdigest()
        for e in entries
    }
    results: list[Result] = []
    for entry in entries:
        if deadline is not None and time.monotonic() >= deadline:
            break
        path = REPO_ROOT / entry.file
        original, text, crlf = _normalised(path)
        result = Result(entry.id, entry.file, applied=False)
        try:
            mutated = apply_mutation(text, entry)
        except ProbeError as exc:
            result.survived = True
            result.note = f"not applied: {exc}; proves nothing"
            results.append(result)
            if on_result:
                on_result(result)
            continue
        if crlf:
            mutated = mutated.replace("\n", "\r\n")
        journal = _journal()
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text(
            json.dumps(
                {
                    "file": entry.file,
                    "id": entry.id,
                    "original": base64.b64encode(original).decode("ascii"),
                }
            ),
            encoding="utf-8",
        )
        try:
            path.write_bytes(mutated.encode("utf-8"))
            result.applied = True
            result.returncode = run_tests(entry.tests)
        finally:
            path.write_bytes(original)
            journal.unlink(missing_ok=True)
        result.killed = killed(result.returncode)
        if not result.killed and entry.id in INERT:
            result.note = f"INERT -- {INERT[entry.id]}"
        else:
            result.survived = not result.killed
        results.append(result)
        if on_result:
            on_result(result)
    after = {
        f: hashlib.sha256((REPO_ROOT / f).read_bytes()).hexdigest() for f in before
    }
    changed = [f for f in before if before[f] != after[f]]
    if changed:
        raise ProbeError(f"files were not restored byte-identically: {changed}")
    return results


def _baseline(nodes: Sequence[str], run_tests: Callable[[Sequence[str]], int]) -> None:
    for start in range(0, len(nodes), _NODE_BATCH):
        batch = list(nodes[start : start + _NODE_BATCH])
        code = run_tests(batch)
        if code != 0:
            raise ProbeError(
                f"baseline failed (pytest exit {code}) for {batch[:3]}...: a test "
                "that fails unmutated cannot score a kill"
            )


# -- the ledger: one run, resumed across processes ----------------------- #

LEDGER_SCHEMA = "learning-mutation-ledger/1"
#: Everything a probe run reads: the code it mutates, the tests that judge it,
#: the catalogue and this probe (with its INERT reasons), and pytest's config.
TREE_PATHS = ("aios", "tests", "scripts", "tools", "pyproject.toml", "pytest.ini")


def tree_identity() -> str:
    """The committed state a ledger's results belong to, which must also be
    the state on disk: results from two trees never mix in one score."""
    dirty = _dirty(TREE_PATHS)
    if dirty:
        raise ProbeError(f"a ledger needs a clean tree; uncommitted: {dirty[:5]}")
    out = subprocess.run(
        ["git", "rev-parse", *(f"HEAD:{p}" for p in TREE_PATHS)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return hashlib.sha256(out.encode("ascii")).hexdigest()


def _save_ledger(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run_ledger(
    entries: Sequence[Entry],
    ledger: Path,
    *,
    budget: float,
    python: str = sys.executable,
    runner: Optional[Callable[[Sequence[str]], int]] = None,
    on_result: Optional[Callable[[Result], None]] = None,
    identity: Optional[Callable[[], str]] = None,
) -> dict:
    """Run what *ledger* has not recorded yet, for at most *budget* seconds.

    A full probe outlives any one process on a machine that reaps long runs,
    so the run is resumable -- and bound: the ledger names the tree it was
    started on, and a ledger from another tree is refused, never extended. The
    baseline runs once per ledger (each passing test recorded); each result is
    written the moment it lands; no mutation starts after the budget, so no
    run is killed mid-mutation to stop.
    """
    tree = (identity or tree_identity)()
    if ledger.exists():
        state = json.loads(ledger.read_text(encoding="utf-8"))
        if state.get("schema") != LEDGER_SCHEMA or state.get("tree") != tree:
            raise ProbeError(
                f"{ledger} holds results for tree {state.get('tree')!r}, not this "
                f"tree {tree!r}: start a new ledger"
            )
    else:
        state = {"schema": LEDGER_SCHEMA, "tree": tree, "baseline": [], "results": {}}
        _save_ledger(ledger, state)  # bound to its tree from the first moment
    deadline = time.monotonic() + budget
    run_tests = runner or (lambda nodes: _pytest(nodes, python))
    passed = set(state["baseline"])
    missing = sorted({t for e in entries for t in e.tests} - passed)
    for start in range(0, len(missing), _NODE_BATCH):
        if time.monotonic() >= deadline:
            return state
        batch = missing[start : start + _NODE_BATCH]
        _baseline(batch, run_tests)
        state["baseline"] = sorted(passed.union(batch))
        passed = set(state["baseline"])
        _save_ledger(ledger, state)

    def record(result: Result) -> None:
        state["results"][result.id] = asdict(result)
        _save_ledger(ledger, state)
        if on_result:
            on_result(result)

    pending = [e for e in entries if e.id not in state["results"]]
    run(
        pending,
        python=python,
        runner=runner,
        on_result=record,
        baseline=False,
        deadline=deadline,
    )
    return state


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--only", help="comma-separated slices (the id prefix, e.g. 4c,5b)"
    )
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if any mutation survived"
    )
    parser.add_argument("--match", help="only entries whose id contains this text")
    parser.add_argument("--json", type=Path, help="write an evidence artifact to PATH")
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="report coverage as if every entry were killed",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        help="resume the run recorded in PATH (bound to this tree); exit 3 "
        "until every selected entry has a result",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=480.0,
        help="with --ledger: start no mutation after this many seconds",
    )
    args = parser.parse_args(argv)

    entries = load()
    if args.only:
        wanted = {p.strip() for p in args.only.split(",") if p.strip()}
        entries = [e for e in entries if e.phase in wanted]
    if args.match:
        entries = [e for e in entries if args.match in e.id]
    if args.coverage:
        report = coverage(entries, [e.id for e in entries], load_guards())
        print(json.dumps({k: v for k, v in report.items() if k != "unattacked"}))
        for m in report["missing_guards"]:
            print(f"  MISSING guard {m}")
        for u in report["unattacked"]:
            print(
                f"  unattacked {u['file']}:{u['line']} {u['function']}: {u['source']}"
            )
        return 0

    def show(r: Result) -> None:
        status = (
            "killed"
            if r.killed
            else ("INERT" if r.note.startswith("INERT") else "SURVIVED")
        )
        print(f"[{status:8}] {r.id}  (exit {r.returncode}) {r.note}", flush=True)

    if args.ledger:
        state = run_ledger(entries, args.ledger, budget=args.budget, on_result=show)
        done = state["results"]
        if any(e.id not in done for e in entries):
            print(
                f"\n{sum(e.id in done for e in entries)}/{len(entries)} recorded in "
                f"{args.ledger}; run again to continue"
            )
            return 3
        results = [Result(**done[e.id]) for e in entries]
    else:
        results = run(entries, on_result=show)
    survivors = [r for r in results if r.survived]
    report = coverage(entries, [r.id for r in results if r.killed], load_guards())
    print()
    print(f"{sum(r.killed for r in results)}/{len(results)} mutations killed")
    print(
        f"guard branch coverage: {report['attacked']}/{report['decision_points']} decision "
        f"points in {report['guard_functions']} guard functions attacked by a killed mutation"
    )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "schema": "learning-mutation-probe/1",
                    "commit": subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=REPO_ROOT,
                        capture_output=True,
                        text=True,
                    ).stdout.strip(),
                    "only": args.only,
                    "tree": tree_identity() if args.ledger else None,
                    "mutations_total": len(results),
                    "mutations_killed": sum(r.killed for r in results),
                    "survivors": [r.id for r in survivors],
                    "coverage": report,
                    "results": [asdict(r) for r in results],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}")
    if survivors and args.check:
        print(
            "\nA survivor means a guard was broken and no test noticed. Add a test that"
        )
        print(
            "catches it, or document in INERT why the mutation is inert. Never delete"
        )
        print("it from the catalogue.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
