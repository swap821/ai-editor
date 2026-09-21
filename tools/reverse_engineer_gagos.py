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
    python tools/reverse_engineer_gagos.py --targets 5 --model bedrock.some-frontier-id
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


def _bootstrap_provider_env() -> None:
    """Load `--env-file` and RE-EXEC before `aios.config` is ever imported.

    `BEDROCK_ENABLED` is derived at import time from `AIOS_BEDROCK_REGION`, and
    every `aios` import below freezes it. Loading the file inside `main()` was
    therefore too late by the length of this module's import block: the ladder
    printed "mistral-large-3-675b UNUSABLE -- Bedrock is not configured" and
    silently fell back to local-only, with real credentials sitting in the
    environment two frames away.

    This is the SAME import-order trap already documented for `.env` and the
    frozen guardrails (`tests/test_guardrails_ignore_dotenv.py`) -- knowing
    about it did not stop me writing it again, which is the argument for
    re-exec rather than for care. The marker variable makes the restart happen
    exactly once.
    """
    import os

    if os.environ.get("_AIOS_RE_ENV_LOADED") == "1":
        return
    argv = sys.argv[1:]
    if "--env-file" not in argv:
        return
    value = (
        argv[argv.index("--env-file") + 1]
        if len(argv) > argv.index("--env-file") + 1
        else ""
    )
    path = Path(value)
    if not path.is_file():
        return  # main() reports it properly; bootstrapping must not swallow errors
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ[key.strip()] = val.strip().strip("<>").strip()
    os.environ["_AIOS_RE_ENV_LOADED"] = "1"
    # `-u` explicitly: the re-exec drops the original interpreter flags, and a
    # buffered restart produced a run whose console output was EMPTY while the
    # work happened normally. The audit trail saved that diagnosis; the screen
    # should not have needed saving.
    os.execv(sys.executable, [sys.executable, "-u", *sys.argv])


_bootstrap_provider_env()

from aios.core.llm import LLMError  # noqa: E402
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
- Assert what it returns for those arguments.
- If the function's result depends on a CONSTANT OR CONFIG VALUE it reads
  (for example `config.SOMETHING`), import that same symbol and build your
  expected value from it. Do not guess what the value contains: the test must
  pin the function, not your guess about its dependencies.
- Your test must genuinely exercise the function, so that breaking the function
  would break your test. Do NOT write `pytest.raises(...)` unless the real
  function actually raises for the input you chose.
- No mocks, no fixtures, no network, no filesystem.
- Output one ```python code block containing the whole file.
"""


@dataclass
class Attempt:
    """One target, one verdict — recorded whatever happened."""

    target: str
    outcome: str
    model: str = ""
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


def load_provider_env(path: Path) -> list[str]:
    """Put provider credentials from *path* into this process's environment.

    Returns the variable NAMES loaded, never the values. Nothing is printed,
    written, or logged -- the file is the operator's, it stays gitignored, and
    this only bridges it into the environment that `aios.config` reads at
    import. Values are stripped of `<` `>` because placeholder brackets copied
    in with a secret have caused 401s against a healthy endpoint here before.

    Loaded BEFORE `aios.config` is imported by anything that matters, since
    `BEDROCK_ENABLED` is derived at import from `AIOS_BEDROCK_REGION`.
    """
    import os

    if not path.is_file():
        raise CorpusError(f"no provider env file at {path}")
    names: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        os.environ[key] = value.strip().strip("<>").strip()
        names.append(key)
    return sorted(set(names))


def resolve_client(model_id: str, *, timeout_s: int):
    """The client for *model_id*, using the product's own prefix dispatch.

    `ollama.x` / `gemini.x` / `openai.x` / `anthropic.x` / `vertexmaas.x`, and a
    bare id falls through to Bedrock -- exactly the rules `router_wiring` applies
    to an explicit model, so this tool cannot reach a provider the product
    would not.

    Hardcoding Ollama here would have quietly capped the whole exercise at
    whatever is installed locally, and reported a 7B's limits as the system's.
    The reason the first runs used `qwen2.5-coder:7b` is narrower than that and
    worth stating: this process has NO cloud credentials in its environment --
    no AWS, Gemini, OpenAI, Anthropic or xAI variable is set -- so Ollama was
    the only provider that could answer at all.
    """
    from aios.api import deps

    # No "a bare id looks local" shortcut. I wrote one -- `"." not in
    # model_id.split(":")[0]` -- and it sent `qwen2.5-coder:7b` to Bedrock,
    # because the "2.5" in the family name is a dot. Inventing a second rule
    # alongside the product's is the exact defect this session keeps removing;
    # a local model is spelled `ollama.<tag>` here for the same reason it is
    # spelled that way everywhere else.
    if model_id.startswith("ollama."):
        from aios.core.llm import OllamaClient

        tag = model_id[len("ollama.") :]
        return OllamaClient(model=tag, timeout_s=timeout_s), tag

    prefixes = {
        "gemini.": deps.get_gemini_client,
        "openai.": deps.get_openai_client,
        "anthropic.": deps.get_anthropic_client,
        "vertexmaas.": deps.get_vertex_maas_client,
    }
    for prefix, getter in prefixes.items():
        if model_id.startswith(prefix):
            client = getter()
            if client is None:
                raise CorpusError(
                    f"{prefix.rstrip('.')} selected but not configured -- the "
                    "credentials for it are absent from this process environment"
                )
            return client, model_id[len(prefix) :]

    if deps.get_bedrock_client() is None:
        raise CorpusError(
            f"model {model_id!r} routes to Bedrock, which is not configured "
            "(BEDROCK_ENABLED is false or AWS credentials are absent here)"
        )
    # BOUND to the requested model, not the shared default client.
    #
    # `get_bedrock_client()` returns a client constructed with
    # `config.BEDROCK_MODEL`. Returning it alongside the requested id looked
    # right and was not: `complete_via` calls `.chat(messages)` with no model
    # argument, so every call went to `amazon.nova-lite-v1:0` whatever the
    # ladder said. Thirty attempts across three models produced thirty
    # IDENTICAL errors -- nova-lite needs an inference profile -- and the run
    # reported "0 earned" for models it never once asked.
    #
    # Uniform failure across models that differ by two orders of magnitude in
    # size is the signature of a harness bug, and it is the only reason this was
    # caught rather than filed as a verdict on the fleet.
    from aios.core.bedrock import BedrockClient

    from aios import config as _config

    return BedrockClient(model=model_id, region=_config.BEDROCK_REGION), model_id


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


def complete_via(client, prompt: str, *, system: str) -> str:
    """One completion from ANY provider client, over the interface they share.

    `.complete()` exists on the Ollama and OpenAI-compatible clients and NOT on
    Bedrock or Gemini, which expose only `.chat(messages)`. Assuming
    `.complete()` is why the first Bedrock probe died with AttributeError on
    three models in a row and looked like a credential problem. `.chat` is the
    one method all four share, so it is the one this depends on.
    """
    if hasattr(client, "complete"):
        return client.complete(prompt, system=system)
    joined = system + "\n\n" + prompt
    messages = [{"role": "user", "content": joined}]
    reply = client.chat(messages)
    if isinstance(reply, dict):
        content = reply.get("content")
        if isinstance(content, list):  # Converse-shaped content blocks
            return "".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        return str(content or "")
    return str(reply or "")


#: An opening fence with no closing one. A reply cut off at the token limit ends
#: mid-file, and a reasoning model spends its budget thinking before it writes.
_OPEN_FENCE = re.compile(r"```(?:python)?[^\n]*\n(.*)", re.DOTALL)


def _extract_code(reply: str) -> str | None:
    """The python file inside a reply, however the model chose to wrap it.

    THREE SHAPES, because scoring output form as content is how a capability
    measurement turns into a measurement of my regex. `nemotron-nano-9b-v2`
    scored 0 of 8 with EVERY attempt marked `no_code_block`, and every reply
    began "Okay, let's tackle this. I need to write a pytest test..." -- a
    reasoning model narrating before it writes. That zero said nothing about
    the model.

    1. A closed fence: the normal case.
    2. An OPEN fence with no close: a reply truncated at the token limit, or a
       reasoning model that spent its budget before closing. Everything after
       the opening fence is still the file it was writing.
    3. No fence at all, but the reply plainly starts as a module and defines a
       test. Prose is still refused -- guessing at unstructured text would
       manufacture failures that are really parsing bugs.
    """
    text = reply or ""
    match = _CODE_FENCE.search(text)
    if match:
        return match.group(1).strip() or None
    open_match = _OPEN_FENCE.search(text)
    if open_match:
        body = open_match.group(1).strip()
        if body:
            return body
    stripped = text.strip()
    if stripped.startswith(("import ", "from ")) and "def test" in stripped:
        return stripped
    return None


def _import_path(module: str) -> str:
    return module[: -len(".py")].replace("/", ".")


def _test_filename(target: Target) -> str:
    stem = _import_path(target.module).replace(".", "_")
    return f"tests/test_pin_{stem}_{target.function}.py"


def _attempt_one(
    corpus, client, target: Target, *, attempt: int, extra: str = "", model: str = ""
) -> Attempt:
    started = time.monotonic()
    record = Attempt(
        target=target.label, outcome="unknown", attempt=attempt, model=model
    )

    prompt = PROMPT.format(
        module=target.module,
        import_path=_import_path(target.module),
        function=target.function,
        source=target.source.rstrip(),
    )
    if extra:
        prompt += f"\nYour previous attempt was rejected. Fix exactly this:\n{extra}\n"

    try:
        reply = complete_via(client, prompt, system=SYSTEM)
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
    parser.add_argument(
        "--models",
        default="ollama.qwen2.5-coder:7b",
        help=(
            "comma-separated escalation ladder, weakest first. Each target is "
            "offered to the next model only when the previous one fails to earn "
            "it, so the record says which tier could do what."
        ),
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="provider credentials to load into the environment first",
    )
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

    if args.env_file:
        try:
            loaded = load_provider_env(args.env_file)
        except CorpusError as exc:
            print(f"FAIL  {exc}")
            return 1
        print(f"env     : loaded {len(loaded)} var(s) from {args.env_file}")

    if WORKTREE.exists():
        print(f"FAIL  {WORKTREE} already exists — remove it before running")
        return 1

    targets = collect_targets(REPO_ROOT, limit=args.targets)
    if not targets:
        print("no targets matched the selection rule")
        return 1

    # Resolve the WHOLE ladder before starting, and drop what cannot answer
    # with its reason. A provider that fails mid-run turns into a low score for
    # a model that was never asked -- the vacuous-FAIL shape again, one layer
    # out. Multi-provider is not redundancy for its own sake here: on this
    # account Claude is unavailable, xAI returns 403, and NVIDIA times out, so a
    # single-model design would have reported "the system cannot learn" when the
    # truth was "one endpoint was down".
    ladder: list[tuple[str, object, str]] = []
    for spec in [m.strip() for m in args.models.split(",") if m.strip()]:
        try:
            client, served = resolve_client(spec, timeout_s=args.model_timeout)
        except CorpusError as exc:
            print(f"        {spec:<46} UNUSABLE — {str(exc)[:80]}")
            continue
        ladder.append((spec, client, served))
    if not ladder:
        print("FAIL  no model in the ladder is usable")
        return 1

    db = REPO_ROOT / "data" / "aios_memory.db"
    init_memory_db(db)
    skills = SkillMemory(db_path=db)

    print("ladder  : " + " -> ".join(spec for spec, _c, _s in ladder))
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
                print(f"  {target.label}")
                earned_by = ""
                # Escalate, do not vote. Each model gets the previous one's
                # rejection reason, so a stronger tier is answering a sharper
                # question than the first was -- and the ladder stops the moment
                # one earns, because a second earning proves nothing new about
                # the target and costs a frontier call.
                for spec, client, _served in ladder:
                    feedback = ""
                    for n in range(1, args.retries + 2):
                        record = _attempt_one(
                            corpus,
                            client,
                            target,
                            attempt=n,
                            extra=feedback,
                            model=spec,
                        )
                        attempts.append(record)
                        flag = "EARNED " if record.earned else "       "
                        print(
                            f"    {flag}{record.outcome:<14} {spec:<34} "
                            f"(try {n}, {record.seconds:.0f}s)"
                        )
                        for note in record.notes[:1]:
                            flat = " ".join(note.split())
                            print(f"            {flat[:140]}")
                        if record.earned:
                            earned_by = spec
                            break
                        feedback = " | ".join(record.notes)[:600]
                    if earned_by:
                        break
                if earned_by:
                    print(f"    -> earned by {earned_by}")

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
    # Per-model, on IDENTICAL targets: the datum multi-model exists to produce.
    # One model's score is a number; several models over the same functions is a
    # comparison, and a comparison is what tells the clerk from the frontier.
    by_model: dict[str, list[int]] = {}
    for a in attempts:
        row = by_model.setdefault(a.model or "(unknown)", [0, 0])
        row[0] += int(a.earned)
        row[1] += 1
    for spec, (won, tried) in sorted(by_model.items()):
        print(f"  {spec:<42} earned {won} of {tried} attempt(s)")
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
        "models": args.models,
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
