#!/usr/bin/env python3
"""Grade a reverse-engineering task, without letting the agent grade itself.

THE TASK SHAPE
--------------
"Read ``<module>.<function>`` and write a test that pins what it actually
does." Learning by reverse-engineering the system's own source, which is the
operator's chosen starting point: the code is already written and already
correct, so unlike "write code and write its tests", the agent cannot satisfy
its grader by bending the thing under test.

THE HOLE THAT LEAVES, AND THE CONTROL THAT CLOSES IT
----------------------------------------------------
``def test_x(): assert True`` passes. So does a test that imports the module
and asserts nothing about it. A green pytest run therefore proves the agent
wrote *a passing test*, not that it understood anything — and rewarding that
would teach the system to write vacuous tests, which is worse than teaching it
nothing.

The control is the one this repo already trusts (the prover's
``probe.broken-code-fails`` step): **a test that pins behaviour must FAIL when
that behaviour is broken.** So the target function's body is replaced with
``raise NotImplementedError`` and the new test is run again. If it still
passes, it never touched the target, and the task is scored a failure no matter
how green the first run was.

Four things must all hold, and each is reported separately so a failure says
which one broke:

1. the new test passes against unmodified source;
2. it fails when the target is mutated  (it actually exercises the target);
3. the source outside ``tests/`` is unchanged (no "fix the code to match");
4. the pre-existing suite selection still passes  (nothing else broke).
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from aios.core.verification_strength import VerificationStrength
from tools.self_corpus import Corpus, CorpusError, run_suite

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aios.memory.skills import SkillMemory


@dataclass(frozen=True)
class Mutation:
    """A reversible break in one function, used as a negative control."""

    path: Path
    function: str
    original: str


def mutate_function(path: Path, function: str) -> Mutation:
    """Replace *function*'s body with ``raise NotImplementedError``.

    The signature, decorators and docstring position are left alone and only
    the statements are replaced, so the module still imports and the mutation
    is felt exactly when the function is CALLED. A mutation that broke the
    import instead would be failed by any test that so much as imports the
    module, which would make the control pass for the wrong reason.

    Nested definitions are not searched: the target is named by the caller, and
    silently mutating a different function of the same name one scope down
    would mean the control measured something nobody asked about.
    """
    original = path.read_text(encoding="utf-8")
    tree = ast.parse(original)
    node = next(
        (
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == function
        ),
        None,
    )
    if node is None:
        # Also allow `Class.method` targets, one level in.
        for top in tree.body:
            if isinstance(top, ast.ClassDef):
                node = next(
                    (
                        n
                        for n in top.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and n.name == function
                    ),
                    None,
                )
                if node is not None:
                    break
    if node is None:
        raise CorpusError(
            f"no function named {function!r} at module or class level in {path}"
        )

    lines = original.splitlines(keepends=True)
    first_stmt = node.body[0]
    start = first_stmt.lineno - 1
    end = node.body[-1].end_lineno
    indent = " " * (first_stmt.col_offset)
    mutated = (
        lines[:start]
        + [f'{indent}raise NotImplementedError("self-corpus negative control")\n']
        + lines[end:]
    )
    path.write_text("".join(mutated), encoding="utf-8")
    return Mutation(path=path, function=function, original=original)


def restore(mutation: Mutation) -> None:
    """Put the original bytes back. Always called from a ``finally``."""
    mutation.path.write_text(mutation.original, encoding="utf-8")


def source_is_untouched(corpus: Corpus) -> tuple[bool, str]:
    """True when the agent changed nothing outside ``tests/``.

    A reverse-engineering task is graded on the test the agent wrote, against
    the code as it stands. Editing the code to match a wrong belief about it is
    not a pass, it is the failure mode — and it would otherwise be invisible,
    because both runs would be green.
    """
    status = subprocess.run(
        ["git", "-C", str(corpus.root), "status", "--porcelain=v1", "-uall"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    offenders = []
    for line in status.splitlines():
        path = line[3:].strip().strip('"')
        if not path or path.startswith("tests/"):
            continue
        if _is_build_artefact(path):
            continue
        offenders.append(line)
    return (not offenders), "\n".join(offenders)


#: Paths that RUNNING the suite creates. Excluded because the check would
#: otherwise flag its own measurement: the clean run compiles the corpus,
#: `__pycache__` appears, and a perfectly honest attempt is scored as having
#: edited the source. Kept deliberately narrow — anything not on this list is
#: an offender, including files a broader "ignore generated stuff" rule would
#: have waved through.
_ARTEFACT_SUFFIXES = (".pyc", ".pyo")
_ARTEFACT_PARTS = ("__pycache__", ".pytest_cache")


def _is_build_artefact(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    return (
        path.endswith(_ARTEFACT_SUFFIXES)
        or any(part in _ARTEFACT_PARTS for part in parts)
        or parts[-1] == ".coverage"
    )


@dataclass
class PinVerdict:
    """Why a reverse-engineering attempt passed or failed. Never a bare bool."""

    passes_clean: bool = False
    fails_when_mutated: bool = False
    source_untouched: bool = False
    suite_still_green: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def earned(self) -> bool:
        return (
            self.passes_clean
            and self.fails_when_mutated
            and self.source_untouched
            and self.suite_still_green
        )


def _refuse_hollow(result, what: str) -> None:
    """Stop the run when a pytest invocation produced nothing at all.

    Raising rather than returning a flag, for the same reason
    `require_green_baseline` raises: once the instrument has stopped
    reporting, every number after it is unattributable, and a verdict about a
    MODEL is the one thing this run must never invent. An aborted run is
    visible in the trail and costs a re-run; a fabricated failure is invisible
    and costs the fleet's record.
    """
    if result.hollow:
        raise CorpusError(
            f"the suite run for {what} produced no output at all "
            f"(rc={result.returncode}, 0 passed / 0 failed / 0 errors). pytest "
            "always says something, so this is the runner dying rather than a "
            "test result -- typically memory pressure on this machine. Scoring "
            "it would record the laptop's failure as the model's."
        )


def grade_pin_test(
    corpus: Corpus,
    *,
    new_test: list[str],
    target_module: str,
    target_function: str,
    guard_selection: list[str],
) -> PinVerdict:
    """Run the four checks and report each one.

    The order matters: the cheap structural check (did the agent edit source?)
    runs before the expensive guard suite, and the mutation control runs even
    when the clean run failed — knowing *both* "it does not pass" and "it would
    not have caught anything anyway" is more useful than stopping at the first
    red.
    """
    verdict = PinVerdict()

    clean = run_suite(corpus, new_test)
    _refuse_hollow(clean, "the agent's new test")
    verdict.passes_clean = clean.green
    if not clean.green:
        verdict.notes.append(f"clean run not green: {clean.tail}")

    untouched, offenders = source_is_untouched(corpus)
    verdict.source_untouched = untouched
    if not untouched:
        verdict.notes.append(
            "source outside tests/ was modified — a pin test is graded against "
            f"the code as it stands, not code bent to fit it:\n{offenders}"
        )

    module_path = corpus.root / Path(target_module)
    mutation = mutate_function(module_path, target_function)
    try:
        mutated = run_suite(corpus, new_test)
        # Checked INSIDE the try so `restore()` still runs: leaving the corpus
        # mutated would break every later attempt in the run.
        _refuse_hollow(mutated, "the mutated negative control")
        verdict.fails_when_mutated = not mutated.green
        if mutated.green:
            verdict.notes.append(
                f"NEGATIVE CONTROL FAILED: the test still passes with "
                f"{target_function}() replaced by `raise NotImplementedError`, so it "
                "does not exercise the target at all. A test that cannot fail is "
                "not evidence of understanding."
            )
    finally:
        restore(mutation)

    guard = run_suite(corpus, guard_selection)
    _refuse_hollow(guard, "the pre-existing guard suite")
    verdict.suite_still_green = guard.green
    if not guard.green:
        verdict.notes.append(f"pre-existing suite no longer green: {guard.tail}")

    return verdict


#: ``skill_signature_v2`` keys an arc on the first 12 SORTED goal tokens and
#: silently drops the rest. Two goals differing only in a dropped token are ONE
#: arc -- which is precisely the per-tier collapse :func:`pin_goal` exists to
#: prevent, reintroduced quietly. So the budget is checked rather than assumed.
_GOAL_TOKEN_BUDGET = 12


def pin_goal(target_label: str, model: str) -> str:
    """The learning arc for *target_label* **as attempted by** *model*.

    WHY THE MODEL BELONGS IN THE IDENTITY
    -------------------------------------
    The ladder asks several tiers the same question and stops at the first that
    answers it. Recording one outcome per TARGET throws away the only thing
    that run measured: *which tier could do it*. Worse, it makes the number
    dishonest in both directions — a frontier model's success is credited to an
    arc the 7B failed four times, and the 7B's failures drag the success rate
    of work it never completed. With four tiers and one earning, the arc reads
    25% and no skill can ever clear the 80% promotion rate, however reliable
    any individual tier is.

    Split by tier and both halves become answerable: a tier that reliably earns
    a target verifies, a tier that reliably fails it stays ``candidate``. That
    is the actual question the local-clerk-vs-cloud-frontier design is asking.

    The model spec is folded to a single token (``:`` is a token boundary in
    ``relevance._TOKEN``, ``.``/``/``/``-`` are not) so a tier costs one slot
    of the signature budget rather than an unpredictable several.
    """
    from aios.memory.relevance import tokens

    tier = "-".join(model.split()).replace(":", "-").strip("-").lower()
    if not tier:
        raise CorpusError("a pin outcome must name the model that attempted it")
    goal = f"pin the behaviour of {target_label} via {tier}"
    if len(tokens(goal)) > _GOAL_TOKEN_BUDGET:
        raise CorpusError(
            f"goal has {len(tokens(goal))} tokens, over the {_GOAL_TOKEN_BUDGET} "
            "the arc signature keeps; the tier could be the token dropped, "
            f"silently merging this attempt into another model's record: {goal}"
        )
    return goal


def content_digest(source: str) -> str:
    """The digest a `create_file` step carries. One derivation, several callers."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def pin_steps(target_module: str, test_rel: str, content_sha256: str) -> list[str]:
    """The workflow steps for a pin attempt, in the shape PRODUCTION records.

    The self-corpus used to record `create_file: <name>`, and the cerebellum's
    `_parse_step` requires `create_file: filepath=..., content_sha256=<64 hex>`
    — a step it cannot parse makes the WHOLE arc uncompilable, so every skill
    the self-corpus ever earned was barred from becoming a reflex. Nothing
    reported it: the arc verified, the compiler silently skipped it, and the
    chain simply stopped one link early.

    Two shapes of the same thing is the defect; this emits the one the turn
    path emits (`turn_pipeline._workflow_step`), so a skill learned from the
    self-corpus and a skill learned from a chat turn are the same kind of
    object. `tests/test_self_corpus_steps_are_compilable.py` pins that with a
    differential check rather than trusting this docstring.

    The digest matters beyond parsing: a replay may only CONFIRM a
    `create_file`, never perform it, and it confirms by comparing the file's
    bytes to this hash. Recording the digest is what lets the reflex verify
    the world still matches what it learned.
    """
    return [
        f"read_file: filepath={target_module}",
        f"create_file: filepath={test_rel}, content_sha256={content_sha256}",
        f"verify: command={_pin_verify_command(test_rel)}",
    ]


def _pin_verify_command(test_rel: str) -> str:
    """The verify command a pin attempt runs, as one derivation.

    It appears in three places that must agree — the recorded step, the lesson
    a failure is keyed to, and the success that confirms that lesson. If they
    disagree by so much as a flag, the lesson can never be promoted, which is
    the failure mode that left every lesson in the live pool unpromotable.
    """
    return f"pytest {test_rel}"


def record_pin_outcome(
    skills: "SkillMemory",
    verdict: PinVerdict,
    *,
    target_label: str,
    model: str,
    steps: list[str],
) -> int:
    """Turn a graded reverse-engineering attempt into learning evidence.

    One call is one TIER's verdict on one target — see :func:`pin_goal` for why
    the tier is part of the arc identity rather than a detail of the run.

    THE GRADER IS THE AUTHORITY HERE, NOT THE STRENGTH. A vacuous
    ``assert True`` test run under pytest produces ``passed_count > 0`` and
    ``failed_count == 0`` from a recognized runner at the program position, so
    ``derive_strength`` calls it STRONG — correctly, by its own definition,
    which is about the KIND of evidence and not about whether the test means
    anything. The strength taxonomy cannot tell a real pin test from a test
    that pins nothing; only the mutation control can.

    So an attempt that did not EARN the task is recorded as a FAILURE, not as a
    weak success. That distinction matters for what the system learns: a weak
    success still resets `consecutive_failures` and still says "this arc ran
    cleanly", which is exactly the wrong lesson to draw from an agent that
    wrote a test incapable of failing.
    """
    return skills.record_attempt(
        pin_goal(target_label, model),
        steps,
        success=verdict.earned,
        strength=(
            VerificationStrength.STRONG if verdict.earned else VerificationStrength.NONE
        ),
    )
