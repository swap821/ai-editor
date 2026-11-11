"""GAGOS's crew: a lead and parallel workers, like Codex's sub-agents or Claude
Code's ultracode (2026-11-11; the operator: "Make GAGOS work same like codex
(multi-sub agents) working", and, for their tools, "Files + sandboxed tests").

* The **lead** is a Claude Code agent with read-only file tools in a masked copy
  of the project (:mod:`aios.maintenance.crew_workspace`). It explores, then
  splits the goal into at most :data:`MAX_SUBTASKS` sub-tasks whose files do
  not overlap, as structured output (:data:`PLAN_SCHEMA`).
* Each **worker** is a Claude Code agent in its OWN copy with file tools (read,
  search, edit, write) and one tool of GAGOS's, ``run_tests``
  (``tools/gagos_crew_mcp.py``): its changes' tests and the type check in the
  sealed sandbox. It may only change its sub-task's files.

No agent gets a shell, the web, or any MCP server but GAGOS's one; each runs
with no session kept. What they produce goes through the workshop's gates like
any proposal: static checks, the sandbox, the adversarial reviewer, CI and the
operator's merge.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from aios.maintenance.crew_workspace import Workspace

#: Who leads and who works: the operator's Claude plan (2026-11-03, "several
#: SONNET AND HAIKU AGENTS").
LEAD_MODEL = "claude-sonnet-5-5"
WORKER_MODELS = ("claude-sonnet-5-5", "claude-haiku-5-5")
#: The most sub-agents one goal is split into.
MAX_SUBTASKS = 6
LEAD_MAX_TURNS = 40
WORKER_MAX_TURNS = 80
AGENT_TIMEOUT_S = 2400
#: The only tools an agent has. Reading outside its copy is refused by Claude
#: Code's own permission rules (measured 2026-11-11).
READ_TOOLS = "Read,Grep,Glob"
WRITE_TOOLS = "Read,Grep,Glob,Edit,Write"
RUN_TESTS = "mcp__gagos__run_tests"

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "subtasks": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_SUBTASKS,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "instructions": {"type": "string"},
                    "files": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                },
                "required": ["title", "instructions", "files"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "subtasks"],
    "additionalProperties": False,
}

RULES = (
    "Rules for everyone on GAGOS's crew: the code you see is GAGOS's own, in a "
    "copy. Some spans are replaced by placeholders (GAGOSMASK followed by Qs, an "
    "underscore and four digits): they hide values that may not leave this "
    "machine; keep every one you keep exactly as written and never invent one. "
    "The operator's palette and textures are sacred: never change a colour token "
    "or a texture asset. Never add eslint-disable, @ts-ignore, @ts-nocheck, "
    "@ts-expect-error, noqa, type: ignore, nosec or pragma comments."
)


@dataclass(frozen=True)
class Subtask:
    title: str
    instructions: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class AgentRun:
    """What one agent said and did: its final text (or structured output),
    how many turns it took, how long, and an error if it failed."""

    result: object
    turns: int
    seconds: float
    error: str | None = None


def agent_argv(
    model: str,
    *,
    write: bool,
    max_turns: int,
    mcp_config: Path | None = None,
    schema: dict | None = None,
    system: str = RULES,
) -> list[str]:
    """The Claude Code command for one crew agent. Every agent: its file tools
    only, no session kept, no MCP server but the one in *mcp_config* (strict),
    edits accepted inside its directory only."""
    argv = [
        "claude",
        "-p",
        "--model",
        model,
        "--output-format",
        "json",
        "--tools",
        WRITE_TOOLS if write else READ_TOOLS,
        "--permission-mode",
        "acceptEdits",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--max-turns",
        str(max_turns),
        "--append-system-prompt",
        system,
    ]
    if mcp_config is not None:
        argv += ["--mcp-config", str(mcp_config), "--allowedTools", RUN_TESTS]
    if schema is not None:
        argv += ["--json-schema", json.dumps(schema)]
    return argv


def run_agent(
    argv: Sequence[str], prompt: str, cwd: Path, timeout_s: int = AGENT_TIMEOUT_S
) -> AgentRun:
    """Run one agent to its end in *cwd*; never raises for the agent's own
    failure (it is said in :attr:`AgentRun.error`)."""
    started = time.monotonic()
    claude = shutil.which(argv[0]) or argv[0]
    try:
        # The prompt goes on stdin: on Windows ``claude`` is a .cmd launcher,
        # and cmd.exe cuts a command-line argument at its first line break
        # (measured 2026-11-11: the lead saw its prompt's first line only).
        proc = subprocess.run(
            [claude, *argv[1:]],
            cwd=str(cwd),
            capture_output=True,
            input=prompt,
            timeout=timeout_s,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return AgentRun(None, 0, time.monotonic() - started, f"ran past {timeout_s}s")
    except OSError as exc:
        return AgentRun(None, 0, time.monotonic() - started, f"could not start: {exc}")
    seconds = time.monotonic() - started
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or [""]
        return AgentRun(
            None,
            0,
            seconds,
            f"no JSON answer (exit {proc.returncode}): {tail[0][:200]}",
        )
    turns = int(data.get("num_turns") or 0)
    if data.get("is_error") or proc.returncode != 0:
        return AgentRun(
            data.get("result"),
            turns,
            seconds,
            f"the agent failed: {str(data.get('result'))[:300]}",
        )
    result = (
        data.get("structured_output")
        if "structured_output" in data
        else data.get("result")
    )
    return AgentRun(result, turns, seconds)


def clone(ws: Workspace, dest: Path) -> Workspace:
    """Another agent's own copy of *ws* (the same mask, a separate directory)."""
    shutil.copytree(ws.root, dest)
    return Workspace(
        root=Path(dest),
        base_commit=ws.base_commit,
        shown=dict(ws.shown),
        mapping=dict(ws.mapping),
        left_out=dict(ws.left_out),
    )


def lead_prompt(goal: str, scopes: Sequence[str]) -> str:
    return "\n".join(
        [
            "You lead GAGOS's crew. Your directory is a copy of GAGOS's code "
            f"(scopes: {', '.join(scopes)}). Read what you need with your tools, "
            "then split the goal below into at most "
            f"{MAX_SUBTASKS} sub-tasks for parallel workers.",
            "Each sub-task names exactly the files its worker may change "
            "(paths relative to this directory; new files allowed), and no two "
            "sub-tasks share a file. Instructions must be concrete: what to change, "
            "where, and which test proves it (workers can run the tests). Prefer "
            "fewer, coherent sub-tasks over many small ones; one is fine.",
            "",
            "The goal:",
            goal,
        ]
    )


def worker_prompt(goal: str, sub: Subtask, others: Sequence[Subtask]) -> str:
    lines = [
        "You are one worker on GAGOS's crew, in your own copy of GAGOS's code.",
        f"Your sub-task: {sub.title}",
        sub.instructions,
        "",
        "You may change ONLY these files (create them if new): " + ", ".join(sub.files),
        "Change nothing else. Add or update a test that proves your change. When "
        "you think it works, call the run_tests tool; fix what it reports and call "
        "it again, until it answers PASSED or you can say exactly why not. Finish "
        "with a short summary of what you changed and the last run_tests answer.",
        "",
        "The whole goal, for context:",
        goal,
    ]
    if others:
        lines += ["", "Other workers do, in parallel (never touch their files):"]
        lines += [f"  - {o.title}: {', '.join(o.files)}" for o in others]
    return "\n".join(lines)


class PlanRefused(ValueError):
    """The lead's plan cannot be worked as given; the message says why."""


def parse_plan(
    raw: object, ws: Workspace, scopes: Sequence[str]
) -> tuple[str, list[Subtask]]:
    """The lead's structured plan, checked: at most :data:`MAX_SUBTASKS`,
    every file a relative path inside the scopes and not one the copy left
    out, and no file in two sub-tasks."""
    if not isinstance(raw, dict) or not isinstance(raw.get("subtasks"), list):
        raise PlanRefused("the lead gave no plan")
    subs: list[Subtask] = []
    owner: dict[str, str] = {}
    for item in raw["subtasks"][: MAX_SUBTASKS + 1]:
        files = tuple(
            str(f).strip().replace("\\", "/") for f in item.get("files") or []
        )
        title = str(item.get("title") or "").strip()
        instructions = str(item.get("instructions") or "").strip()
        if not (title and instructions and files):
            raise PlanRefused("a sub-task has no title, instructions or files")
        for rel in files:
            p = PurePosixPath(rel)
            if (
                p.is_absolute()
                or ".." in p.parts
                or not any(rel.startswith(s) for s in scopes)
            ):
                raise PlanRefused(f"{rel} is not a file inside the crew's scopes")
            if rel in ws.left_out:
                raise PlanRefused(f"{rel} is a file the crew's copy does not hold")
            if rel in owner:
                raise PlanRefused(
                    f"{rel} is in two sub-tasks ({owner[rel]!r} and {title!r})"
                )
            owner[rel] = title
        subs.append(Subtask(title, instructions, files))
    if not subs:
        raise PlanRefused("the lead's plan has no sub-task")
    if len(subs) > MAX_SUBTASKS:
        raise PlanRefused(f"the plan has more than {MAX_SUBTASKS} sub-tasks")
    return str(raw.get("summary") or "").strip(), subs


def outside_its_files(changed: dict[str, str | None], sub: Subtask) -> list[str]:
    """Files a worker changed that its sub-task does not name."""
    return sorted(rel for rel in changed if rel not in sub.files)


__all__ = [
    "AGENT_TIMEOUT_S",
    "AgentRun",
    "LEAD_MODEL",
    "MAX_SUBTASKS",
    "PLAN_SCHEMA",
    "PlanRefused",
    "RULES",
    "RUN_TESTS",
    "Subtask",
    "WORKER_MODELS",
    "agent_argv",
    "clone",
    "lead_prompt",
    "outside_its_files",
    "parse_plan",
    "run_agent",
    "worker_prompt",
]
