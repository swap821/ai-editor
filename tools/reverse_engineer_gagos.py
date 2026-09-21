#!/usr/bin/env python3
"""Close the learning chain on GAGOS's own source — organically, or not at all.

WHAT THIS IS FOR
----------------
Every structural blocker in the learning path is now unblocked, and the chain
has still never closed on organic data: `.aios/audit/learning-loop-runs.jsonl`
records one staged 19/19 day in July and nothing since. Plumbing that has never
carried water is a claim, not a capability.

So this drives the loop for real, against the one corpus on this machine with a
green test suite: GAGOS itself. A local model is shown one function's source and
asked to write a test that pins what it actually does. The test is then graded
by `self_corpus_grading` — it must pass clean, FAIL when the target's body is
replaced with `raise NotImplementedError`, leave the source untouched, and not
break the existing suite. Only an earned verdict records a success.

WHAT MAKES THIS HONEST RATHER THAN A DEMO
-----------------------------------------
* Targets come from a written rule (`self_corpus_targets`), not a hand-picked
  list that was going to work.
* The work happens in a throwaway git worktree with `AIOS_SCOPE_ROOTS` pointed
  at it and nothing else; the live tree is fingerprinted before and after and a
  difference raises.
* A failed attempt is recorded as a FAILURE, not skipped and not softened into a
  weak success — a weak success would reset the streak that gates reflex
  compilation, so a vacuous attempt would actively help.
* Every attempt appends an audit row whatever the outcome, so a run that earned
  nothing is as visible as one that earned something. A tool that only writes
  when it succeeds is how "we ran it" becomes indistinguishable from "it worked".

    python tools/reverse_engineer_gagos.py --targets 3
    python tools/reverse_engineer_gagos.py --targets 5 --model qwen2.5-coder:7b
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from aios.core.llm import LLMError, OllamaClient  # noqa: E402
from aios.memory.db import init_memory_db  # noqa: E402
from aios.memory.skills import SkillMemory  # noqa: E402
from tools.self_corpus import CorpusError, self_corpus  # noqa: E402
from tools.self_corpus_grading import grade_pin_test, record_pin_outcome  # noqa: E402
from tools.self_corpus_targets import Target, collect_targets  # noqa: E402

TRAIL = REPO_ROOT / ".aios" / "audit" / "reverse-engineering-runs.jsonl"
WORKTREE = REPO_ROOT.parent / "ai-editor-selfcorpus"

#: A cheap, dependency-free suite that must still pass after the agent writes.
#: Its job is to catch collateral damage, not to re-prove the repository.
GUARD_SELECTION = ["tests/test_code_chunking.py"]

_CODE_FENCE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)

SYSTEM = (
    "You write pytest tests. You are given one Python function's exact source. "
    "Write a test that pins what the function ACTUALLY does, derived only from "
    "the code you were shown. Output ONE python code block and nothing else."
)

PROMPT = """\
Module path: {module}
Import it as: from {import_path} import {function}

Here is the complete source of the function:

```python
{source}
```

Write a pytest test file that pins this function's real behaviour.

Requirements:
- Import the function exactly as shown above.
- Call it with concrete literal arguments you construct yourself.
- Assert the exact value it returns for those arguments.
- The test MUST fail if the function's body is replaced by `raise NotImplementedError`.
  A test that would still pass then is worthless here.
- No mocks, no fixtures, no network, no filesystem.
- Output one ```python code block containing the whole file.
"""


@dataclass
class Attempt:
    """One target, one verdict — recorded whatever happened."""

    target: str
    outcome: str
    earned: bool = False
    passes_clean: bool = False
    fails_when_mutated: bool = False
    source_untouched: bool = False
    suite_still_green: bool = False
    attempt: int = 1
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)


#: A pin test written by hand, known correct, over a target the selection rule
#: always produces. It is the POSITIVE CONTROL: if the grader cannot earn with
#: this, then a run reporting "0 earned" is measuring the harness and blaming
#: the model. Every vacuous result this repository has chased had that shape --
#: a score that looked like a verdict on the subject and was really a verdict on
#: the apparatus. Checking costs one pytest invocation.
_CONTROL_TARGET_MODULE = "aios/agents/tool_agent.py"
_CONTROL_TARGET_FUNCTION = "build_auto_verify_command"
_CONTROL_TEST = """from aios import config
from aios.agents.tool_agent import build_auto_verify_command


def test_it_wraps_the_arg_and_empties_inherited_addopts():
    out = build_auto_verify_command("training_ground/test_x.py")
    assert out == f'{config.VERIFY_RUNNER} -o addopts= "training_ground/test_x.py" -q'
"""


def run_self_check(corpus) -> tuple[bool, str]:
    """Prove the grader can EARN before any model is asked to try.

    Returns ``(ok, detail)``. A failure here is not a bad score, it is an
    invalid instrument, and the run must stop rather than produce a number.
    """
    rel = "tests/test_pin_self_check.py"
    path = corpus.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CONTROL_TEST, encoding="utf-8")
    try:
        verdict = grade_pin_test(
            corpus,
            new_test=[rel],
            target_module=_CONTROL_TARGET_MODULE,
            target_function=_CONTROL_TARGET_FUNCTION,
            guard_selection=GUARD_SELECTION,
        )
    finally:
        path.unlink(missing_ok=True)
    if verdict.earned:
        return True, "grader earns on a known-correct test"
    return False, " | ".join(verdict.notes)[:600] or "control did not earn"


def _extract_code(reply: str) -> str | None:
    match = _CODE_FENCE.search(reply or "")
    if match:
        return match.group(1).strip() or None
    # A model that forgot the fence but clearly wrote a test is still usable;
    # one that wrote prose is not, and guessing would manufacture a failure that
    # is really a parsing bug.
    stripped = (reply or "").strip()
    if stripped.startswith(("import ", "from ")) and "def test" in stripped:
        return stripped
    return None


def _import_path(module: str) -> str:
    return module[: -len(".py")].replace("/", ".")


def _test_filename(target: Target) -> str:
    stem = _import_path(target.module).replace(".", "_")
    return f"tests/test_pin_{stem}_{target.function}.py"


def _attempt_one(
    corpus, client: OllamaClient, target: Target, *, attempt: int, extra: str = ""
) -> Attempt:
    started = time.monotonic()
    record = Attempt(target=target.label, outcome="unknown", attempt=attempt)

    prompt = PROMPT.format(
        module=target.module,
        import_path=_import_path(target.module),
        function=target.function,
        source=target.source.rstrip(),
    )
    if extra:
        prompt += f"\nYour previous attempt was rejected. Fix exactly this:\n{extra}\n"

    try:
        reply = client.complete(prompt, system=SYSTEM)
    except LLMError as exc:
        record.outcome = "model_error"
        record.notes.append(str(exc)[:300])
        record.seconds = time.monotonic() - started
        return record

    code = _extract_code(reply)
    if not code:
        record.outcome = "no_code_block"
        record.notes.append(f"reply began: {(reply or '')[:160]!r}")
        record.seconds = time.monotonic() - started
        return record

    rel = _test_filename(target)
    path = corpus.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code + "\n", encoding="utf-8")

    verdict = grade_pin_test(
        corpus,
        new_test=[rel],
        target_module=target.module,
        target_function=target.function,
        guard_selection=GUARD_SELECTION,
    )
    record.passes_clean = verdict.passes_clean
    record.fails_when_mutated = verdict.fails_when_mutated
    record.source_untouched = verdict.source_untouched
    record.suite_still_green = verdict.suite_still_green
    record.earned = verdict.earned
    record.notes.extend(n[:300] for n in verdict.notes)
    record.outcome = (
        "earned"
        if verdict.earned
        else "vacuous"
        if verdict.passes_clean and not verdict.fails_when_mutated
        else "rejected"
    )
    record.seconds = time.monotonic() - started
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=int, default=3)
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument(
        "--model-timeout",
        type=int,
        default=420,
        help="seconds to wait for one completion",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="re-prompts per target, with the rejection reason fed back",
    )
    args = parser.parse_args(argv)

    if WORKTREE.exists():
        print(f"FAIL  {WORKTREE} already exists — remove it before running")
        return 1

    targets = collect_targets(REPO_ROOT, limit=args.targets)
    if not targets:
        print("no targets matched the selection rule")
        return 1

    # A 7B writing a whole test file routinely needs more than the chat default.
    client = OllamaClient(model=args.model, timeout_s=args.model_timeout)
    db = REPO_ROOT / "data" / "aios_memory.db"
    init_memory_db(db)
    skills = SkillMemory(db_path=db)

    print(f"model   : {args.model}")
    print(f"targets : {len(targets)}")
    for t in targets:
        print(f"          {t.label}")
    print()

    attempts: list[Attempt] = []
    try:
        with self_corpus(REPO_ROOT, WORKTREE) as corpus:
            print(f"corpus  : {corpus.root} @ {corpus.sha[:12]}")
            ok, detail = run_self_check(corpus)
            print(f"control : {'PASS' if ok else 'FAIL'} — {detail[:110]}\n")
            if not ok:
                # Refuse to produce a score from an instrument that cannot
                # register a success. "0 earned" from a broken grader and "0
                # earned" from a weak model are the same number and opposite
                # findings, and only this check tells them apart.
                raise CorpusError(
                    "self-check FAILED: the grader could not earn on a "
                    "known-correct pin test, so no score from this run would "
                    f"mean anything. {detail}"
                )
            for target in targets:
                feedback = ""
                for n in range(1, args.retries + 2):
                    record = _attempt_one(
                        corpus, client, target, attempt=n, extra=feedback
                    )
                    attempts.append(record)
                    flag = "EARNED " if record.earned else "       "
                    print(
                        f"  {flag}{record.outcome:<14} {target.label}  "
                        f"(try {n}, {record.seconds:.0f}s)"
                    )
                    for note in record.notes[:1]:
                        print(f"          {note[:150]}")
                    if record.earned:
                        break
                    feedback = " | ".join(record.notes)[:600]

                best = max(
                    (a for a in attempts if a.target == target.label),
                    key=lambda a: a.earned,
                )
                # The GRADER decides, not pytest: a vacuous test passes pytest and
                # must still be recorded as a failed attempt at the task.
                record_pin_outcome(
                    skills,
                    _verdict_of(best),
                    goal=f"pin the behaviour of {target.label}",
                    steps=[
                        f"read_file: {target.module}",
                        f"create_file: {_test_filename(target)}",
                        "verify: pytest",
                    ],
                )
    except CorpusError as exc:
        print(f"\nFAIL  {exc}")
        _write_trail(args, attempts, error=str(exc))
        return 1

    _write_trail(args, attempts)
    earned = [a for a in attempts if a.earned]
    print(f"\n{len(earned)} earned / {len({a.target for a in attempts})} target(s)")
    print(f"trail: {TRAIL.relative_to(REPO_ROOT).as_posix()}")
    if not earned:
        print(
            "\nNothing was earned. That is a result, not an error: the attempts "
            "are recorded as failures and the scoreboard will show it."
        )
    return 0


class _V:
    """Adapt an :class:`Attempt` back to what `record_pin_outcome` expects."""

    def __init__(self, a: Attempt) -> None:
        self.earned = a.earned


def _verdict_of(a: Attempt) -> _V:
    return _V(a)


def _write_trail(args, attempts: list[Attempt], *, error: str | None = None) -> None:
    TRAIL.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": args.model,
        "targets": args.targets,
        "retries": args.retries,
        "attempts": [asdict(a) for a in attempts],
        "earned": sum(1 for a in attempts if a.earned),
    }
    if error:
        row["error"] = error
    with TRAIL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
