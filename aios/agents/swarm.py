"""Ephemeral worker swarm over the single supervised tool loop — ant-colony.

The dynamic-fan-out generalization of the sequential role-pass
(:mod:`aios.agents.role_pass`). A DECOMPOSER caste splits a task into independent
subtasks; then one ephemeral WORKER caste :class:`~aios.agents.tool_agent.ToolAgent`
is spawned PER subtask (bounded by ``SWARM_MAX_WORKERS``), each a fresh agent over
the SAME gated executor with a worker system prompt + tool subset; finally a
SYNTHESIZER caste composes the workers' results from verifier evidence.

Stigmergy, not orchestration. Workers share NO mutable state and exchange no
messages directly. Their only shared media are exactly the ant-colony's:

  * the conversation — each worker's distilled final answer is appended as a
    labelled assistant message the next workers re-read (a pheromone deposit);
  * the sandbox — the files a worker writes are read by later workers/the
    synthesizer (the environment IS the shared memory);
  * the development trail field — verified work deposits/reinforces skill trails
    through the normal recording path, so a later swarm follows stronger trails.

Each worker is spawned for one subtask and DISSOLVES; nothing persists but the
disk artifacts and the trails it laid. Authority is unchanged: every worker is
gated, and a YELLOW write/command pauses the WHOLE swarm (``human_required``
flows out with a worker ``role`` tag); the replayed turn restarts the swarm with
the loop's grant pre-apply landing approved writes first.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterator, Optional

from aios import config
from aios.agents.tool_agent import STEP_LIMIT_TEXT

#: Caste tool subsets, enforced mechanically at ToolAgent._dispatch.
DECOMPOSER_TOOLS = frozenset({"read_file", "read_directory", "plan"})
WORKER_TOOLS = frozenset(
    {"read_file", "read_directory", "execute_terminal", "edit_file", "create_file", "verify"}
)
SYNTHESIZER_TOOLS = frozenset({"read_file", "read_directory", "verify"})

DECOMPOSER_PROMPT = (
    "You are the DECOMPOSER of an ephemeral worker swarm. Investigate the request "
    "with your read-only tools, then split it into a small set of INDEPENDENT "
    "subtasks that separate workers can do without talking to each other (share "
    "only files). End with a numbered list, one subtask per line, each a single "
    "concrete deliverable (e.g. '1. Create training_ground/foo.py with ...'). "
    "Do not implement anything yourself; another caste's workers do that."
)
WORKER_PROMPT = (
    "You are ONE WORKER of a swarm, assigned EXACTLY ONE subtask (stated below). "
    "Do only that subtask: read what you need, write the file(s), and verify your "
    "work with the verify tool. Other workers handle the other subtasks in "
    "parallel — do not do theirs. Call tools ONLY through the tool interface. End "
    "with a one-line report of what you delivered."
)
SYNTHESIZER_PROMPT = (
    "You are the SYNTHESIZER of a worker swarm. The workers' reports are above and "
    "their files are on disk. You are read-only: inspect the produced files and "
    "run the verify tool on the relevant tests. Judge ONLY from verifier evidence, "
    "never from a worker's claim. End with a synthesis: what the swarm delivered, "
    "what verified, and any subtask that failed or is missing."
)

#: Tool calls that count as a worker having actually produced work.
_WRITE_TOOLS = frozenset({"edit_file", "create_file", "execute_terminal"})

#: ``make_agent(system_prompt=..., allowed_tools=..., max_iters=...)`` -> ToolAgent.
AgentFactory = Callable[..., Any]

_SUBTASK_LINE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.*\S)\s*$")


def _parse_subtasks(answer: str, *, limit: int) -> list[str]:
    """Extract numbered/bulleted subtask lines from the decomposer's answer.

    Robust to a weak model: takes lines shaped like ``1. ...`` / ``- ...``; if
    none are found, the whole (non-empty) answer becomes a single subtask, so the
    swarm degrades safely to one worker rather than fanning out on noise.
    """
    found: list[str] = []
    for line in answer.splitlines():
        match = _SUBTASK_LINE.match(line)
        if match:
            found.append(match.group(1).strip())
    if not found:
        stripped = answer.strip()
        found = [stripped] if stripped and stripped != STEP_LIMIT_TEXT else []
    return found[: max(1, limit)]


def run_swarm(
    make_agent: AgentFactory,
    messages: list[dict[str, Any]],
    *,
    subtasks: Optional[list[str]] = None,
    max_workers: int = config.SWARM_MAX_WORKERS,
) -> Iterator[dict[str, Any]]:
    """Decompose -> dispatch ephemeral workers -> synthesize, yielding ``run``'s
    event vocabulary plus a ``role`` tag per leg.

    Per-leg ``done`` events are swallowed; exactly one ``done`` ends the swarm so
    the API's outcome accounting composes unchanged. A pause/error in any leg ends
    the whole swarm (a replay restarts it). If ``subtasks`` is given, the
    decomposer leg is skipped (the caller already split the work).
    """
    shared = list(messages)
    state: dict[str, Any] = {}
    cap = max(1, min(int(max_workers), config.SWARM_MAX_WORKERS))

    def leg(
        role: str,
        prompt: str,
        tools: frozenset[str],
        note: Optional[str] = None,
        max_iters: Optional[int] = None,
    ) -> Iterator[dict[str, Any]]:
        state.clear()
        state.update(text=[], fail_targets={}, stopped=False, plan_artifact="", wrote=False)
        leg_messages = list(shared)
        if note:
            leg_messages.append({"role": "user", "content": note})
        overrides: dict[str, Any] = {"system_prompt": prompt, "allowed_tools": tools}
        if max_iters is not None:
            overrides["max_iters"] = max_iters
        agent = make_agent(**overrides)
        yield {
            "type": "tool_result",
            "tool": "swarm",
            "output": f"caste: {role}",
            "id": f"swarm-{role}",
            "role": role,
        }
        for event in agent.run(leg_messages):
            kind = str(event.get("type", ""))
            if kind == "done":
                break
            tagged = {**event, "role": role}
            if kind in ("human_required", "error"):
                state["stopped"] = True
                yield tagged
                return
            if kind == "text":
                state["text"].append(str(event.get("text", "")))
            elif kind == "tool_result":
                if (
                    str(event.get("id", "")).startswith("grant-")
                    or str(event.get("tool", "")) in _WRITE_TOOLS
                ):
                    state["wrote"] = True
                output = str(event.get("output", ""))
                if output.startswith(("[VERIFY PASS]", "[VERIFY FAIL]")):
                    target = str(event.get("target") or f"v{len(state['fail_targets'])}")
                    state["fail_targets"][target] = output.startswith("[VERIFY FAIL]")
                if str(event.get("tool", "")) == "plan":
                    state["plan_artifact"] = output
            yield tagged
        answer = "".join(state["text"]).strip()
        if state["plan_artifact"] and (not answer or answer == STEP_LIMIT_TEXT):
            answer = str(state["plan_artifact"])  # the plan artifact carries the handoff
        if answer == STEP_LIMIT_TEXT:
            answer = ""  # a leg that produced nothing hands off NOTHING
        if answer:
            # Pheromone deposit: only the distilled final answer crosses to the
            # shared conversation; raw tool chatter stays inside the leg.
            shared.append({"role": "assistant", "content": f"[{role}]\n{answer}"})
        return

    # 1. DECOMPOSE (skipped when the caller supplied subtasks).
    plan = list(subtasks) if subtasks else None
    if plan is None:
        yield from leg("decomposer", DECOMPOSER_PROMPT, DECOMPOSER_TOOLS, max_iters=4)
        if state["stopped"]:
            return
        plan = _parse_subtasks("".join([]) or _last_answer(shared), limit=cap)
    plan = plan[:cap]
    if not plan:
        # Nothing to fan out — degrade to a single worker over the bare request.
        plan = [_user_text(messages)]

    # 2. DISPATCH one ephemeral worker per subtask. Sequential by design (one weak
    #    local model, bounded RAM); the swarm SHAPE is the contribution — a
    #    stronger/parallel runtime can dispatch the same legs concurrently.
    any_work = False
    for index, subtask in enumerate(plan):
        note = f"YOUR SUBTASK ({index + 1} of {len(plan)}):\n{subtask}"
        yield from leg(f"worker-{index + 1}", WORKER_PROMPT, WORKER_TOOLS, note=note)
        if state["stopped"]:
            return
        any_work = any_work or bool(state["wrote"])

    # 3. SYNTHESIZE from verifier evidence (skipped if no worker produced work).
    if any_work:
        yield from leg("synthesizer", SYNTHESIZER_PROMPT, SYNTHESIZER_TOOLS, max_iters=6)
        if state["stopped"]:
            return

    yield {"type": "done"}


def _last_answer(shared: list[dict[str, Any]]) -> str:
    """The most recent assistant handoff appended to the shared conversation."""
    for message in reversed(shared):
        if message.get("role") == "assistant":
            content = str(message.get("content", ""))
            return content.split("\n", 1)[1] if content.startswith("[") else content
    return ""


def _user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""
