#!/usr/bin/env python3
"""Close the WHOLE chain on real code, or report honestly which link did not.

WHAT THIS ADDS TO THE SELF-CORPUS RUNNER
----------------------------------------
`reverse_engineer_gagos.py` already produces genuine failures on real code: a
model is shown a real function and gets it wrong roughly seven times in ten.
What it does NOT do is let those failures travel the chain — it writes test
files directly, so nothing reflects, nothing confirms, nothing compiles.

The consequence showed up in the ledger. Skill acquisition (L3) and organic
acquisition (L7) had organic evidence; reflection, lesson transfer, reflex
compilation and reflex replay had only ever been exercised against goals a
benchmark seeded for itself. That is a harness gap, not a credibility gap, and
this closes it:

    a real failure on real code        -> ReflectionAgent records a lesson   L1
    the identical command later passes -> that lesson is promoted            L2
    the arc earns three STRONG runs    -> the skill verifies                 L3
    the verified arc compiles          -> a reflex exists                    L4
    the reflex serves the next request -> with the LLM rigged to raise       L5

Every link is the PRODUCTION class doing its production job. Nothing here
reimplements a link in order to watch it work.

WHAT WOULD MAKE THIS DISHONEST, AND IS THEREFORE REFUSED
--------------------------------------------------------
Seeding a failure. A deliberately broken input produces a lesson that proves
the recorder works, not that the loop learns — synthetic evidence wearing an
organic label, which is exactly what LC10 exists to catch. So the failures here
are whatever the model actually does, and if it happens to succeed first time on
every target, L1 and L2 report NOT PROVEN rather than inventing a stumble.

CONTAINMENT is inherited unchanged from `self_corpus()`: a throwaway worktree
pinned to a commit, `AIOS_SCOPE_ROOTS` REPLACED (so `training_ground` and `lab`
drop out too), a green baseline required, and the live tree fingerprinted before
and after. `probe_common.ALLOWED_FILE_RE` is not touched — widening a sandbox
guard to make a ledger go green is the trade this whole effort refuses.

    python tools/organic_chain_run.py --targets 2
    python tools/organic_chain_run.py --targets 3 --models ollama.qwen2.5-coder:7b
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _load_env_file() -> None:
    """Provider credentials into this process BEFORE any `aios` import.

    `aios.config` derives `BEDROCK_ENABLED` at import time, so a `--env-file`
    read inside `main()` is too late by the length of the import block below —
    the ladder prints "routes to Bedrock, which is not configured" and falls
    back to local-only with real credentials two frames away. Observed here
    exactly once before this existed.

    Unlike the ladder's version this does NOT re-exec: `os.execv` on Windows is
    spawn-then-exit, which detaches the run and makes the launcher return 0
    immediately. Reading the file here is enough, because this happens above
    the imports rather than inside `main()`.
    """
    argv = sys.argv[1:]
    if "--env-file" not in argv:
        return
    index = argv.index("--env-file") + 1
    path = Path(argv[index]) if index < len(argv) else None
    if path is None or not path.is_file():
        return  # main() reports it properly; bootstrapping must not swallow it
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip("<>").strip()
    # The ladder module runs its OWN bootstrap at import time, and that one
    # re-execs when it sees `--env-file`. On Windows `os.execv` is
    # spawn-then-exit, so importing it would detach this run and hand the
    # launcher a silent exit 0 — observed exactly that, once. This is the
    # ladder's own marker saying "already loaded"; setting it makes the
    # imported bootstrap return instead of restarting the process.
    os.environ["_AIOS_RE_ENV_LOADED"] = "1"


_load_env_file()

# Same bootstrap as the ladder: credentials must land before `aios.config`
# freezes provider flags at import time.
from tools.reverse_engineer_gagos import (  # noqa: E402
    Attempt,
    _attempt_one,
    _last_digest,
    _test_filename,
    resolve_client,
    tier_verdict,
)
from aios.agents import tool_loop_helpers  # noqa: E402
from aios.agents.reflection_agent import ReflectionAgent  # noqa: E402
from aios.core.cerebellum import Cerebellum  # noqa: E402
from aios.core.verification_strength import VerificationStrength  # noqa: E402
from aios.memory.db import get_connection, init_memory_db  # noqa: E402
from aios.memory.mistake import MistakeMemory  # noqa: E402
from aios.memory.skills import SkillMemory  # noqa: E402
from tools.self_corpus import CorpusError, self_corpus  # noqa: E402
from tools.self_corpus_grading import (  # noqa: E402
    _pin_verify_command,
    pin_steps,
    record_pin_outcome,
)
from tools.self_corpus_targets import collect_targets  # noqa: E402

TRAIL = REPO_ROOT / ".aios" / "audit" / "organic-chain-runs.jsonl"
WORKTREE = REPO_ROOT.parent / "ai-editor-selfcorpus"
DB = REPO_ROOT / "data" / "aios_memory.db"


@dataclass
class LinkEvidence:
    """One link of the chain, and what actually happened to it."""

    link: str
    faculty: str
    fired: bool = False
    detail: str = ""
    refs: list[str] = field(default_factory=list)


class RefusingLLM:
    """Raises if anything asks it to think. The proof for L5."""

    def __init__(self) -> None:
        self.calls = 0

    def _boom(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError(
            "the LLM was consulted on a turn a compiled reflex was supposed to "
            "serve — the reflex preceded the model instead of replacing it"
        )

    chat = _boom
    complete = _boom
    stream = _boom


def _append(row: dict) -> None:
    """Crash-durable, for the reason Stage 1b established: a run that dies
    with nothing on disk is indistinguishable from a run that never started."""
    TRAIL.parent.mkdir(parents=True, exist_ok=True)
    with TRAIL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _failure_text(record: Attempt) -> str:
    """What the model's failure actually said, for the lesson to reason about."""
    return " | ".join(record.notes)[:1800] or f"attempt outcome: {record.outcome}"


def run_chain(
    *,
    models: str,
    targets: int,
    retries: int,
    model_timeout: int,
) -> tuple[list[LinkEvidence], list[Attempt], str]:
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
    init_memory_db(DB)

    mistakes = MistakeMemory(db_path=DB)
    skills = SkillMemory(db_path=DB)
    cerebellum = Cerebellum(DB)

    ladder = []
    for spec in [m.strip() for m in models.split(",") if m.strip()]:
        try:
            client, _served = resolve_client(spec, timeout_s=model_timeout)
        except CorpusError as exc:
            print(f"  {spec:<40} UNUSABLE — {str(exc)[:70]}")
            continue
        ladder.append((spec, client))
    if not ladder:
        raise CorpusError("no model in the ladder is usable")

    # The store is passed EXPLICITLY: ReflectionAgent refuses to guess one,
    # so a lesson can never land somewhere other than where the rest of the
    # chain will look for it.
    reflector = ReflectionAgent(ladder[0][1], mistakes=mistakes, db_path=DB)

    links = {
        name: LinkEvidence(name, faculty)
        for name, faculty in (
            ("reflection", "L1"),
            ("lesson_transfer", "L2"),
            ("skill_acquisition", "L3"),
            ("reflex_compilation", "L4"),
            ("reflex_replay", "L5"),
        )
    }
    attempts: list[Attempt] = []
    # Skills this run actually recorded. L4/L5 may only ever cite a
    # playbook whose skill is in here -- see `_organic_playbook`.
    organic_skill_ids: set[int] = set()

    print(f"run id  : {run_id}")
    print("ladder  : " + " -> ".join(spec for spec, _ in ladder))

    with self_corpus(REPO_ROOT, WORKTREE) as corpus:
        print(f"corpus  : {corpus.root} @ {corpus.sha[:12]}\n")
        chosen = collect_targets(corpus.root, limit=targets)

        for target in chosen:
            print(f"  {target.label}")
            test_rel = _test_filename(target)
            verify_command = _pin_verify_command(test_rel)
            # `pending` is the fail->confirm tracker the turn path keeps in
            # memory for a session; the same shape, for the same reason.
            pending: list[tuple[int, str]] = []

            for spec, client in ladder:
                tier_attempts: list[Attempt] = []
                feedback = ""
                for n in range(1, retries + 2):
                    record = _attempt_one(
                        corpus, client, target, attempt=n, extra=feedback, model=spec
                    )
                    attempts.append(record)
                    tier_attempts.append(record)
                    flag = "EARNED " if record.earned else "       "
                    print(
                        f"    {flag}{record.outcome:<14} {spec:<30} "
                        f"(try {n}, {record.seconds:.0f}s)"
                    )

                    # --- L1: a REAL failure becomes a lesson -----------------
                    # Only a GRADED failure. A transport error is not the
                    # model's mistake and there is nothing to learn from it.
                    if not record.earned and record.outcome in ("rejected", "vacuous"):
                        reflection = _reflect(
                            reflector, verify_command, _failure_text(record), run_id
                        )
                        if reflection is not None:
                            pending.append((reflection, verify_command))
                            links["reflection"].fired = True
                            links["reflection"].refs.append(
                                f"lesson {reflection} from {target.label} via {spec}"
                            )
                            print(f"            L1 lesson {reflection} recorded")

                    # --- L2: the identical command succeeding confirms it ----
                    if record.earned and pending:
                        promoted: list[int] = []
                        list(
                            tool_loop_helpers.confirm(
                                pending,
                                verify_command,
                                0,
                                lambda mid: (
                                    promoted.append(mid),
                                    mistakes.promote(mid),
                                ),
                                strength=VerificationStrength.STRONG,
                            )
                        )
                        if promoted:
                            links["lesson_transfer"].fired = True
                            links["lesson_transfer"].refs.append(
                                f"lesson {promoted[0]} promoted by {verify_command!r}"
                            )
                            print(f"            L2 lesson {promoted[0]} PROMOTED")

                    if record.earned:
                        break
                    feedback = " | ".join(record.notes)[:600]

                should_record, tier_earned, why = tier_verdict(tier_attempts)
                if not should_record:
                    print(f"            not recorded — never reached ({why})")
                    continue

                skill_id = record_pin_outcome(
                    skills,
                    _V(tier_earned),
                    target_label=target.label,
                    model=spec,
                    steps=pin_steps(
                        target.module, test_rel, _last_digest(tier_attempts)
                    ),
                )
                organic_skill_ids.add(skill_id)
                if tier_earned:
                    links["skill_acquisition"].fired = True
                    links["skill_acquisition"].refs.append(f"skill {skill_id}")
                if tier_earned:
                    break

        # --- A verify-only arc, so L5 has something it CAN replay ----------
        # `tests/test_code_chunking.py` is real, fast and dependency-free, and
        # the corpus is a real checkout of this repository -- so this is a real
        # module being really tested, just without a write in the workflow.
        print("\n  verify-only arc (read + verify, no writes)")
        verify_skill_id, verify_detail = _verify_only_cycle(
            corpus,
            ladder[0][1],
            skills,
            target_test="tests/test_code_chunking.py",
            repeats=3,
        )
        if verify_skill_id is not None:
            organic_skill_ids.add(verify_skill_id)
        print(f"    {verify_detail}")

        # --- L4: does anything the chain earned actually compile? -----------
        compiled = cerebellum.try_compile_all()
        # ONLY a playbook whose skill this run earned counts. Taking "the
        # newest compiled playbook" instead made L5 light up on a leftover
        # `lab/` seed from the synthetic prover -- a pass for a reason
        # unrelated to organic learning, which is the lucky-pass failure this
        # benchmark's own rules forbid.
        live = _organic_playbook(DB, organic_skill_ids)
        if compiled and live is not None:
            links["reflex_compilation"].fired = True
            links["reflex_compilation"].detail = f"{compiled} newly compiled"
            links["reflex_compilation"].refs.append(
                f"playbook {live['id']}: {live['goal_pattern'][:70]}"
            )
            print(f"\n  L4 compiled {compiled} playbook(s)")
        else:
            links[
                "reflex_compilation"
            ].detail = "no verified arc became a reflex this run"

        # --- L5: the reflex serves a request with the LLM rigged to raise ---
        if live is not None:
            served, detail = _replay_without_llm(DB, str(live["goal_pattern"]))
            links["reflex_replay"].fired = served
            links["reflex_replay"].detail = detail
            if served:
                links["reflex_replay"].refs.append(f"playbook {live['id']}")
            print(f"  L5 {'SERVED with zero LLM calls' if served else detail}")
        else:
            links["reflex_replay"].detail = (
                "no playbook from an ORGANIC arc to replay; a synthetic one "
                "matching by chance would not be evidence"
            )

    return list(links.values()), attempts, run_id


VERIFY_ONLY_PROMPT = (
    "Use the verify tool to run exactly this command and report the result: "
    "`{command}`. Do not create or edit any files."
)


def _verify_only_cycle(
    corpus,
    client,
    skills,
    *,
    target_test: str,
    repeats: int,
) -> tuple[Optional[int], str]:
    """Earn an arc on real code that a reflex can actually replay.

    WHY THIS SHAPE EXISTS. The pin task writes a file, and a replay may only
    CONFIRM a `create_file` whose exact bytes a human approved. The self-corpus
    has no human, so a pin arc can never be replayed -- not because replay is
    broken, but because the write guard is doing its job. Registering
    agent-written bytes as approved would be forging an approval.

    A read+verify task has no such problem, and it is not a contrivance: the
    learning-loop prover uses exactly this shape for its own reflex phase, for
    exactly this reason. The work is real (a real module, a real suite that
    really runs in the corpus); only the WRITE is absent.

    The steps are derived by `turn_pipeline._workflow_step`, the production
    function, so the arc is the same kind of object a chat turn would record.
    """
    from aios.agents.tool_agent import ToolAgent
    from aios.api.turn_pipeline import _workflow_step
    from aios.core.autonomy import UNGOVERNED_FIXTURE
    from aios.core.executor import Executor
    from aios.core.verification_strength import derive_strength
    from aios.security.gateway import RateLimiter

    command = f"pytest {target_test}"
    goal = VERIFY_ONLY_PROMPT.format(command=command)
    skill_id: Optional[int] = None
    detail = ""

    for attempt in range(1, repeats + 1):
        agent = ToolAgent(
            client,
            Executor(
                rate_limiter=RateLimiter(),
                audit_log=lambda *a, **k: None,
                emergency_stop=UNGOVERNED_FIXTURE,
            ),
            max_iters=4,
            read_root=corpus.root,
            session_id=f"organic-verify-{attempt}",
        )
        steps: list[str] = []
        passed = False
        verify_output = ""
        try:
            for event in agent.run([{"role": "user", "content": goal}]):
                if event.get("type") == "tool_call":
                    steps.append(_workflow_step(event))
                if event.get("type") == "tool_result" and event.get("tool") == "verify":
                    verify_output = str(event.get("output", ""))
                    passed = "[VERIFY PASS]" in verify_output
        except Exception as exc:  # noqa: BLE001 - a bad turn is a result
            detail = f"turn {attempt} raised {type(exc).__name__}: {str(exc)[:90]}"
            continue

        if not steps:
            detail = f"turn {attempt} made no tool calls"
            continue

        strength = derive_strength(
            passed=passed,
            passed_count=_passed_count(verify_output),
            failed_count=0 if passed else 1,
            command=command,
        )
        skill_id = skills.record_attempt(goal, steps, success=passed, strength=strength)
        detail = f"{attempt} turn(s), last strength={strength.name}, passed={passed}"
        print(
            f"    verify-only turn {attempt}: passed={passed} "
            f"strength={strength.name} steps={len(steps)}"
        )
    return skill_id, detail


def _passed_count(verify_output: str) -> int:
    """Tests reported passing, so a hollow verify cannot mint STRONG."""
    import re as _re

    match = _re.search(r"(\d+) passed", verify_output)
    return int(match.group(1)) if match else 0


def _reflect(reflector, command: str, error_output: str, run_id: str) -> int | None:
    """Record a lesson, returning its id. Never breaks the run."""
    try:
        reflection = reflector.reflect(command, error_output, task_id=run_id)
    except Exception as exc:  # noqa: BLE001 - a learning step must not be fatal
        print(f"            L1 reflection unavailable: {type(exc).__name__}")
        return None
    return getattr(reflection, "mistake_id", None) if reflection else None


def _replay_without_llm(db: Path, goal: str) -> tuple[bool, str]:
    """Ask for the compiled goal with a client that raises if consulted."""
    from aios.agents.tool_agent import ToolAgent
    from aios.core.autonomy import UNGOVERNED_FIXTURE
    from aios.core.executor import Executor
    from aios.security.gateway import RateLimiter

    llm = RefusingLLM()
    agent = ToolAgent(
        llm,
        Executor(
            rate_limiter=RateLimiter(),
            audit_log=lambda *a, **k: None,
            emergency_stop=UNGOVERNED_FIXTURE,
        ),
        max_iters=2,
        cerebellum=Cerebellum(db),
    )
    try:
        events = list(agent.run([{"role": "user", "content": goal}]))
    except AssertionError as exc:
        return False, str(exc)[:160]
    except Exception as exc:  # noqa: BLE001 - a replay failure is a result
        return False, f"{type(exc).__name__}: {str(exc)[:140]}"
    served = any(e.get("type") == "cerebellum_done" for e in events)
    return (
        served,
        f"llm_calls={llm.calls}, events={[e.get('type') for e in events][:5]}",
    )


def _organic_playbook(db: Path, skill_ids: set[int]):
    """The newest compiled playbook whose skill THIS run earned, or None.

    The restriction is the whole point. The store also holds playbooks
    compiled from the synthetic prover's `lab/` seeds, and replaying one of
    those proves the replay machinery works — not that anything learned from
    real code can be replayed. Those are different claims and LC10 asks for
    the second.
    """
    if not skill_ids:
        return None
    placeholders = ",".join("?" * len(skill_ids))
    with get_connection(db) as conn:
        return conn.execute(
            "SELECT id, goal_pattern, skill_id FROM compiled_playbooks "
            f"WHERE status = 'compiled' AND skill_id IN ({placeholders}) "
            "ORDER BY id DESC LIMIT 1",
            tuple(skill_ids),
        ).fetchone()


class _V:
    """The `.earned` half of a PinVerdict — all `record_pin_outcome` reads."""

    def __init__(self, earned: bool) -> None:
        self.earned = earned


def render(links: list[LinkEvidence]) -> str:
    out = ["", "ORGANIC CHAIN", ""]
    fired = sum(1 for link in links if link.fired)
    out.append(f"  {fired} / {len(links)} links closed on real code")
    out.append("")
    for link in links:
        mark = "FIRED" if link.fired else "  -  "
        out.append(f"  [{mark}] {link.faculty}  {link.link}")
        if link.refs:
            out.append(f"           {link.refs[0][:120]}")
        elif link.detail:
            out.append(f"           {link.detail[:120]}")
    if fired < len(links):
        out.append("")
        out.append(
            "  A link that did not fire is NOT PROVEN, not proven-absent. The "
            "honest report is which one and why — never a seeded failure to "
            "make it light up."
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=int, default=2)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--models", default="ollama.qwen2.5-coder:7b")
    parser.add_argument("--model-timeout", type=int, default=300)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="provider credentials, read before any aios import (see _load_env_file)",
    )
    args = parser.parse_args(argv)

    try:
        links, attempts, run_id = run_chain(
            models=args.models,
            targets=args.targets,
            retries=args.retries,
            model_timeout=args.model_timeout,
        )
    except CorpusError as exc:
        print(f"\nFAIL  {exc}")
        _append(
            {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": "run",
                "outcome": "aborted",
                "error": str(exc),
            }
        )
        return 1

    print(render(links))
    _append(
        {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": "run",
            "run_id": run_id,
            "outcome": "completed",
            "models": args.models,
            "links": [asdict(link) for link in links],
            "attempts": [asdict(a) for a in attempts],
        }
    )
    print(f"\ntrail: {TRAIL.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
