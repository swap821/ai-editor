"""GAGOS's crew at work on a task (2026-11-11).

The operator: "Make GAGOS work same like codex (multi-sub agents) working ...
Same like u do work on ultra code", with agents that have "Files + sandboxed
tests". One open task at a time:

1. a masked copy of the base commit (:mod:`aios.maintenance.crew_workspace`);
2. the lead plans in it, read-only, into sub-tasks that share no file
   (:mod:`aios.maintenance.crew_agents`);
3. one worker per sub-task, in parallel, each admitted by the Worker Foundry
   in its own copy, with file tools and GAGOS's ``run_tests``;
4. every worker's change read back and restored; one that touched a file its
   sub-task does not name, or failed, stops the whole change;
5. the change recorded as one group of proposals under the task, through the
   same static checks as any task (all or nothing).

From there the hour's usual steps carry it: the sandbox runs its tests
together, the adversarial reviewer judges it, delivery opens the PR, and the
operator merges. Nothing an agent wrote runs outside the sandbox.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aios.application.workers.workshop_foundry import WriterLeg  # noqa: E402
from aios.maintenance import crew_agents as ca  # noqa: E402
from aios.maintenance import crew_workspace as cw  # noqa: E402
from aios.maintenance.daily_work import (  # noqa: E402
    OP_CREATE,
    OP_DELETE,
    TASK_RULE,
    Finding,
    ProposalRefused,
    StaticVerdict,
    is_python,
    task_verdict,
)
from aios.maintenance.python_static import (  # noqa: E402
    check_python_texts,
    format_python_text,
    import_refusal,
)

#: Open tasks the crew takes in one hour.
CREW_TASKS_PER_HOUR = 1
#: What the crew's copy holds. The frontend's docs are left out: their dated
#: logs alone hold more placeholders than one copy may (measured 2026-11-11).
CREW_SCOPES = ("frontend/",)


def crew_enabled() -> bool:
    """Whether the crew takes the open tasks: ``AIOS_GAGOS_CREW=1``. Off until
    a live run of the whole crew has proven it on GAGOS's own code (then the
    hourly job switches it on); until then the one-shot writers take tasks."""
    return os.environ.get("AIOS_GAGOS_CREW", "0").strip() == "1"


def mcp_config(project: Path, state: Path, dest: Path) -> Path:
    """The one MCP server a worker may use: GAGOS's run_tests, on its copy."""
    dest.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "gagos": {
                        "command": sys.executable,
                        "args": [
                            str(ROOT / "tools" / "gagos_crew_mcp.py"),
                            "--project",
                            str(project),
                            "--state",
                            str(state),
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return dest


def _base_text(root: Path, base: str, rel: str) -> str | None:
    import subprocess

    proc = subprocess.run(
        ["git", "-C", str(root), "show", f"{base}:{rel}"], capture_output=True
    )
    return proc.stdout.decode("utf-8") if proc.returncode == 0 else None


def crew_task(
    led,
    root: Path,
    task: dict,
    *,
    redact: Callable[[str], str],
    check_texts: Callable,
    foundry,
    work_dir: Path,
    run_agent: Callable = ca.run_agent,
    busy: frozenset[str] = frozenset(),
) -> str:
    """Run the crew on one open *task*; its change is recorded as one group of
    proposals under the task. Returns one line saying what happened. A lead or
    worker that failed leaves the task open for a later hour; a plan or change
    that cannot be accepted refuses the task, saying why."""
    from tools.gagos_crew_mcp import save_state

    tid = task["task_id"]
    base = _base(root)
    run_dir = work_dir / f"c{uuid.uuid4().hex[:8]}"
    goal = redact(task["text"].strip())
    named = [task["rel"], *task.get("also", [])]
    goal += "\n\nFiles the operator named: " + ", ".join(named)
    ws = cw.build(root, base, CREW_SCOPES, redact, run_dir / "lead")

    lead = run_agent(
        ca.agent_argv(
            ca.LEAD_MODEL,
            write=False,
            max_turns=ca.LEAD_MAX_TURNS,
            schema=ca.PLAN_SCHEMA,
        ),
        ca.lead_prompt(goal, CREW_SCOPES),
        ws.root,
    )
    if lead.error:
        return f"task {tid} stays open: the lead failed: {lead.error}"
    try:
        summary, subs = ca.parse_plan(lead.result, ws, CREW_SCOPES)
    except ca.PlanRefused as exc:
        led.refuse_task(tid, f"the crew's plan was refused: {exc}")
        return f"task {tid} refused: the crew's plan: {exc}"
    held = sorted({f for sub in subs for f in sub.files} & set(busy))
    if held:
        shutil.rmtree(run_dir, ignore_errors=True)
        return f"task {tid} waits: an unmerged GAGOS change holds {', '.join(held)}"

    copies, results = [], [None] * len(subs)
    legs = []
    for i, sub in enumerate(subs):
        mine = ca.clone(ws, run_dir / f"w{i + 1}")
        state = run_dir / f"w{i + 1}.json"
        save_state(mine, state)
        config = mcp_config(root, state, run_dir / f"w{i + 1}-mcp.json")
        model = ca.WORKER_MODELS[i % len(ca.WORKER_MODELS)]
        argv = ca.agent_argv(
            model, write=True, max_turns=ca.WORKER_MAX_TURNS, mcp_config=config
        )
        prompt = ca.worker_prompt(goal, sub, [o for o in subs if o is not sub])

        def run(i=i, argv=argv, prompt=prompt, mine=mine):
            results[i] = run_agent(argv, prompt, mine.root)

        copies.append(mine)
        legs.append(WriterLeg(writer=model, files=sub.files, run=run))
    outcomes = foundry.run_batch(f"crew:{tid}", legs)

    changed: dict[str, str | None] = {}
    for i, sub in enumerate(subs):
        failed = outcomes[i] or (results[i].error if results[i] else "no result")
        if failed:
            return (
                f"task {tid} stays open: worker {i + 1} ({sub.title}) failed: {failed}"
            )
        try:
            mine = cw.changes(copies[i])
            outside = ca.outside_its_files(mine, sub)
            if outside:
                raise ProposalRefused(
                    f"worker {i + 1} changed files its sub-task does not name: "
                    + ", ".join(outside)
                )
            changed.update(cw.restore(copies[i], mine))
        except ProposalRefused as exc:
            led.refuse_task(tid, f"the crew's change was refused: {exc}")
            return f"task {tid} refused: {exc}"
    if not changed:
        led.refuse_task(tid, "the crew changed nothing")
        return f"task {tid} refused: the crew changed nothing"

    ids = _record(
        led,
        root,
        base,
        tid,
        changed,
        check_texts,
        model="crew:"
        + "+".join(
            [
                ca.LEAD_MODEL,
                *sorted(
                    {
                        ca.WORKER_MODELS[i % len(ca.WORKER_MODELS)]
                        for i in range(len(subs))
                    }
                ),
            ]
        ),
    )
    led.take_task(tid, ids[0])
    shutil.rmtree(run_dir, ignore_errors=True)
    return f"task {tid}: the crew ({len(subs)} worker(s)) proposed {len(changed)} file(s): {summary[:160]}"


def _base(root: Path) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _record(led, root, base, tid, changed, check_texts, *, model) -> list[str]:
    """The crew's change as one group of proposals, through the same static
    checks as any task: all or nothing."""
    from aios.maintenance.frontend_static import StaticCheckUnavailable

    verdicts: dict[str, StaticVerdict | None] = {}
    why: dict[str, str] = {}
    bases: dict[str, str] = {}
    existed: dict[str, bool] = {}
    for rel, new in sorted(changed.items()):
        base_text = _base_text(root, base, rel)
        bases[rel] = base_text or ""
        existed[rel] = base_text is not None
        if new is None:
            if base_text is None:
                why[rel] = "deletes a file the base does not have"
            verdicts[rel] = StaticVerdict(
                True, "deletes the file", base_text.count("\n") if base_text else 0
            )
            continue
        try:
            if is_python(rel):
                new = changed[rel] = format_python_text(root, rel, new)
            check = check_python_texts if is_python(rel) else check_texts
            before = check(root, {rel: bases[rel]}, inline_off=True)[rel]
            after = check(root, {rel: new}, inline_off=True)[rel]
        except StaticCheckUnavailable as exc:
            verdicts[rel], why[rel] = None, f"static checks unavailable: {exc}"
            continue
        verdict = task_verdict(rel, bases[rel], new, before, after)
        if verdict.passed and is_python(rel) and base_text is not None:
            taken = import_refusal(root, rel, base_text, new)
            if taken:
                verdict = StaticVerdict(False, taken, verdict.changed_lines)
        verdicts[rel] = verdict
        if not verdict.passed:
            why[rel] = verdict.reason
    first = min(why) if why else None
    ids = []
    for rel, new in sorted(changed.items()):
        op = OP_DELETE if new is None else (None if existed[rel] else OP_CREATE)
        refusal = None
        if first is not None and rel != first:
            refusal = (
                f"{first} was refused ({why[first]}); a crew's change is all or nothing"
            )
        elif first == rel and verdicts.get(rel) is None:
            refusal = why[rel]
        ids.append(
            led.record_proposal(
                Finding(rel, TASK_RULE, ()),
                base_text=bases[rel],
                base_commit=base,
                model=model,
                new_text="" if new is None else new,
                verdict=verdicts.get(rel),
                refusal=refusal,
                group_id=tid,
                op=op,
            )
        )
    return ids


__all__ = [
    "CREW_SCOPES",
    "CREW_TASKS_PER_HOUR",
    "crew_enabled",
    "crew_task",
    "mcp_config",
]
