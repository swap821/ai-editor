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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from aios import config
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.agents.tool_agent import STEP_LIMIT_TEXT

#: Caste tool subsets, enforced mechanically at ToolAgent._dispatch.
DECOMPOSER_TOOLS = frozenset({"read_file", "read_directory", "plan"})
SCOUT_TOOLS = frozenset({"plan"})
WORKER_TOOLS = frozenset(
    {
        "read_file",
        "read_directory",
        "execute_terminal",
        "edit_file",
        "create_file",
        "verify",
        "browse",
    }
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
SCOUT_PROMPT = (
    "You are the SCOUT of an ant-colony swarm. Decide whether the user's goal "
    "matches a known successful decomposition pattern. Known patterns are listed "
    "below. If one clearly fits, reply exactly:\n"
    "USE_PATTERN\n"
    "1. <subtask one>\n"
    "2. <subtask two>\n"
    "...\n"
    "If none fit, or the plan cannot be reused verbatim, reply exactly:\n"
    "DECOMPOSE\n"
    "No commentary."
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
QUORUM_PROMPT = (
    "You are the QUORUM of a worker swarm. Several workers were given the SAME "
    "subtask and produced the reports listed below. Inspect the produced files and "
    "run the verify tool if needed. Pick the SINGLE canonical report best supported "
    "by verifier evidence. If all reports agree, summarize the agreed result. If "
    "they conflict, choose the replica whose verify passed or whose file is more "
    "complete. End with one concise report for this subtask."
)
CLOUD_BROKER_PROMPT = (
    "You are the CLOUD_BROKER of an ant-colony swarm. The user's request was split "
    "into the subtasks below. Label each subtask as CLOUD (safe to run on a remote "
    "provider: public knowledge, no secrets, no local-only files) or LOCAL (must "
    "stay on this machine). Reply with one line per subtask:\n"
    "1. CLOUD\n"
    "2. LOCAL\n"
    "No commentary."
)

#: Tool calls that count as a worker having actually produced work.
_WRITE_TOOLS = frozenset({"edit_file", "create_file", "execute_terminal"})

QUORUM_TOOLS = frozenset({"read_file", "read_directory", "verify", "plan"})
CLOUD_BROKER_TOOLS = frozenset({"plan"})

#: ``make_agent(system_prompt=..., allowed_tools=..., max_iters=...)`` -> ToolAgent.
AgentFactory = Callable[..., Any]

_SUBTASK_LINE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.*\S)\s*$")


@dataclass
class _LegResult:
    role: str
    events: list[dict[str, Any]]
    answer: str
    wrote: bool
    stopped: bool
    fail_targets: dict[str, bool] = field(default_factory=dict)


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


def _format_recall(patterns: list[dict[str, Any]]) -> str:
    """Build the SCOUT leg note from recalled verified patterns."""
    if not patterns:
        return ""
    lines = ["Known successful decomposition patterns:"]
    for idx, pattern in enumerate(patterns, 1):
        lines.append(
            f"Pattern {idx}: {pattern.get('goal_pattern', '')} "
            f"(successes {pattern.get('success_count', 0)}, "
            f"rate {pattern.get('success_rate', 0.0)})"
        )
        for sidx, sub in enumerate(pattern.get("subtasks", []), 1):
            lines.append(f"  {sidx}. {sub}")
    return "\n".join(lines)


def _format_quorum_note(subtask: str, results: list[_LegResult]) -> str:
    """Build the QUORUM leg note from redundant worker reports."""
    lines = [f"SUBTASK: {subtask}", "REPLICA REPORTS:"]
    for result in results:
        lines.append(f"[{result.role}] {result.answer or '(no report)'}")
    return "\n".join(lines)


def _parse_cloud_labels(answer: str, n: int) -> list[bool]:
    """Parse the CLOUD_BROKER's per-subtask locality labels.

    Any line that contains ``CLOUD`` marks that subtask as cloud-eligible;
    everything else defaults to local. A malformed response safely falls back
    to all-local.
    """
    labels: list[bool] = []
    for line in answer.splitlines():
        if _SUBTASK_LINE.match(line):
            labels.append("CLOUD" in line.upper())
    if len(labels) != n:
        return [False] * n
    return labels


def _run_quorum(
    make_agent: AgentFactory,
    shared: list[dict[str, Any]],
    subtask_index: int,
    subtask: str,
    results: list[_LegResult],
) -> _LegResult:
    """Run the QUORUM caste for one subtask's redundant replicas."""
    role = f"quorum-{subtask_index + 1}"
    note = _format_quorum_note(subtask, results)
    return _run_leg(
        make_agent, shared, role, QUORUM_PROMPT, QUORUM_TOOLS, note=note, max_iters=4
    )


def _run_leg(
    make_agent: AgentFactory,
    shared: list[dict[str, Any]],
    role: str,
    prompt: str,
    tools: frozenset[str],
    note: Optional[str] = None,
    max_iters: Optional[int] = None,
    subtask_index: Optional[int] = None,
    cloud_provider: Optional[str] = None,
) -> _LegResult:
    """Execute one caste leg and return its events + distilled handoff.

    The leg is fully deterministic and state-local: it reads from ``shared`` but
    does NOT mutate it. The caller decides when (and whether) to deposit the
    distilled ``answer`` back into ``shared``.
    """
    state: dict[str, Any] = {
        "text": [],
        "fail_targets": {},
        "stopped": False,
        "plan_artifact": "",
        "wrote": False,
    }
    leg_messages = list(shared)
    if note:
        leg_messages.append({"role": "user", "content": note})
    overrides: dict[str, Any] = {"system_prompt": prompt, "allowed_tools": tools}
    if max_iters is not None:
        overrides["max_iters"] = max_iters
    agent = make_agent(**overrides)
    events: list[dict[str, Any]] = [
        {"type": "caste_start", "role": "swarm", "caste": role},
        {
            "type": "tool_result",
            "tool": "swarm",
            "output": f"caste: {role}",
            "id": f"swarm-{role}",
            "role": role,
        },
    ]
    if cloud_provider and subtask_index is not None:
        events.append(
            {
                "type": "cloud_route",
                "role": "swarm",
                "subtask_index": subtask_index,
                "provider": cloud_provider,
            }
        )
    for event in agent.run(leg_messages):
        kind = str(event.get("type", ""))
        if kind == "done":
            break
        tagged = {**event, "role": role}
        if kind in ("human_required", "error"):
            state["stopped"] = True
            events.append(tagged)
            break
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
        events.append(tagged)

    answer = "".join(state["text"]).strip()
    if state["plan_artifact"] and (not answer or answer == STEP_LIMIT_TEXT):
        answer = str(state["plan_artifact"])  # the plan artifact carries the handoff
    if answer == STEP_LIMIT_TEXT:
        answer = ""  # a leg that produced nothing hands off NOTHING

    return _LegResult(
        role=role,
        events=events,
        answer=answer,
        wrote=state["wrote"],
        stopped=state["stopped"],
        fail_targets=state["fail_targets"],
    )


def _deposit(
    result: _LegResult, shared: list[dict[str, Any]], *, role: Optional[str] = None
) -> None:
    """Pheromone deposit: only the distilled final answer crosses to the shared
    conversation; raw tool chatter stays inside the leg."""
    if result.answer:
        alias = role or result.role
        shared.append({"role": "assistant", "content": f"[{alias}]\n{result.answer}"})


def run_swarm(
    make_agent: AgentFactory,
    messages: list[dict[str, Any]],
    *,
    subtasks: Optional[list[str]] = None,
    max_workers: int = config.SWARM_MAX_WORKERS,
    worker_concurrency: int = config.SWARM_WORKER_CONCURRENCY,
    redundancy: int = config.SWARM_REDUNDANCY,
    pattern_memory: Optional[SwarmPatternMemory] = None,
    enable_scout: bool = True,
    cloud_burst: bool = config.SWARM_CLOUD_BURST_ENABLED,
    make_cloud_agent: Optional[AgentFactory] = None,
    cloud_provider: Optional[str] = None,
) -> Iterator[dict[str, Any]]:
    """Decompose -> dispatch ephemeral workers -> synthesize, yielding ``run``'s
    event vocabulary plus a ``role`` tag per leg.

    Per-leg ``done`` events are swallowed; exactly one ``done`` ends the swarm so
    the API's outcome accounting composes unchanged. A pause/error in any leg ends
    the whole swarm (a replay restarts it). If ``subtasks`` is given, the
    decomposer leg is skipped (the caller already split the work).

    A SCOUT caste may run before the decomposer. If ``pattern_memory`` is provided
    and it recalls verified patterns for the user's goal, the scout decides whether
    to reuse a known plan verbatim (skipping the decomposer) or to decompose fresh.

    Worker legs run sequentially when ``worker_concurrency`` is 1, preserving the
    original stigmergy where each worker sees the previous worker's deposit. When
    ``worker_concurrency`` is >1, workers fan out in parallel and their deposits are
    appended after the whole pool finishes.

    When ``redundancy`` is >1, each subtask gets that many independent replicas and
    a QUORUM caste picks the canonical result before synthesis.

    When ``cloud_burst`` is enabled and ``make_cloud_agent`` is supplied, a
    CLOUD_BROKER caste labels each subtask as local or cloud; cloud-eligible
    subtasks use the cloud factory while staying behind the same executor gate.
    ``cloud_provider`` is emitted in ``cloud_route`` frames for UI visibility.
    """
    shared = list(messages)
    cap = max(1, min(int(max_workers), config.SWARM_MAX_WORKERS))
    concurrency = max(1, min(int(worker_concurrency), cap))
    replicas = max(1, min(int(redundancy), config.SWARM_REDUNDANCY))
    goal = _user_text(messages)

    # 1. PLAN — scout + pattern recall, or decomposer.
    plan = list(subtasks) if subtasks else None
    if plan is None and pattern_memory is not None and enable_scout:
        recalled = pattern_memory.recall(goal, limit=3)
        if recalled:
            scout = _run_leg(
                make_agent,
                shared,
                "scout",
                SCOUT_PROMPT,
                SCOUT_TOOLS,
                note=_format_recall(recalled),
                max_iters=4,
            )
            yield from scout.events
            if scout.stopped:
                return
            _deposit(scout, shared)
            parsed = _parse_subtasks(scout.answer, limit=cap)
            if parsed and "DECOMPOSE" not in scout.answer.upper():
                plan = parsed
                # Reinforce the strongest recalled pattern.
                try:
                    pattern_memory.bump_use(recalled[0]["pattern_id"])
                except Exception:  # noqa: BLE001 - memory must not break swarm
                    pass

    if plan is None:
        decomposer = _run_leg(
            make_agent,
            shared,
            "decomposer",
            DECOMPOSER_PROMPT,
            DECOMPOSER_TOOLS,
            max_iters=4,
        )
        yield from decomposer.events
        if decomposer.stopped:
            return
        _deposit(decomposer, shared)
        plan = _parse_subtasks(decomposer.answer, limit=cap)
    plan = plan[:cap]
    if not plan:
        # Nothing to fan out — degrade to a single worker over the bare request.
        plan = [goal]

    yield {"type": "swarm_plan", "role": "swarm", "plan": list(plan)}

    # 2. PLAN BROKER — cloud-burst eligibility labels.
    cloud_labels: Optional[list[bool]] = None
    if cloud_burst and make_cloud_agent is not None:
        broker_note = "Subtasks:\n" + "\n".join(
            f"{i + 1}. {subtask}" for i, subtask in enumerate(plan)
        )
        broker = _run_leg(
            make_agent,
            shared,
            "cloud_broker",
            CLOUD_BROKER_PROMPT,
            CLOUD_BROKER_TOOLS,
            note=broker_note,
            max_iters=4,
        )
        yield from broker.events
        if broker.stopped:
            return
        _deposit(broker, shared)
        cloud_labels = _parse_cloud_labels(broker.answer, len(plan))

    # 3. DISPATCH redundant replicas per subtask, then QUORUM if needed.
    any_work = False
    assignments = [
        (index, replica, plan[index])
        for index in range(len(plan))
        for replica in range(replicas)
    ]

    def _factory_for(index: int) -> AgentFactory:
        if cloud_labels and cloud_labels[index] and make_cloud_agent is not None:
            return make_cloud_agent
        return make_agent

    def _run_worker(index: int, replica: int, subtask: str) -> _LegResult:
        factory = _factory_for(index)
        is_cloud = cloud_labels and cloud_labels[index] and make_cloud_agent is not None
        provider = cloud_provider if is_cloud else None
        if replicas > 1:
            role = f"worker-{index + 1}-{replica + 1}"
            note = (
                f"YOUR SUBTASK ({index + 1} of {len(plan)}, "
                f"replica {replica + 1} of {replicas}):\n{subtask}"
            )
        else:
            role = f"worker-{index + 1}"
            note = f"YOUR SUBTASK ({index + 1} of {len(plan)}):\n{subtask}"
        return _run_leg(
            factory,
            shared,
            role,
            WORKER_PROMPT,
            WORKER_TOOLS,
            note=note,
            subtask_index=index,
            cloud_provider=provider,
        )

    if concurrency <= 1 or len(plan) <= 1:
        # Sequential path: run replicas for one subtask, quorum, then next subtask.
        for index in range(len(plan)):
            subtask = plan[index]
            results: list[_LegResult] = []
            for replica in range(replicas):
                result = _run_worker(index, replica, subtask)
                yield from result.events
                if result.stopped:
                    return
                results.append(result)
            if replicas > 1:
                quorum = _run_quorum(make_agent, shared, index, subtask, results)
                yield from quorum.events
                if quorum.stopped:
                    return
                _deposit(quorum, shared, role=f"worker-{index + 1}")
            else:
                _deposit(results[0], shared)
            yield {
                "type": "caste_end",
                "role": "swarm",
                "caste": f"worker-{index + 1}",
                "outcome": "ok",
            }
            any_work = any_work or any(r.wrote for r in results)
    else:
        # Concurrent path: fan out all replicas, then quorum per subtask.
        def _worker_task(item: tuple[int, int, str]) -> tuple[int, _LegResult]:
            index, replica, subtask = item
            return index, _run_worker(index, replica, subtask)

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            indexed_results = list(pool.map(_worker_task, assignments))

        grouped: list[list[_LegResult]] = [[] for _ in plan]
        for index, result in indexed_results:
            grouped[index].append(result)

        for index, results in enumerate(grouped):
            for result in results:
                yield from result.events
                if result.stopped:
                    return
            if replicas > 1:
                quorum = _run_quorum(make_agent, shared, index, plan[index], results)
                yield from quorum.events
                if quorum.stopped:
                    return
                _deposit(quorum, shared, role=f"worker-{index + 1}")
            else:
                _deposit(results[0], shared)
            yield {
                "type": "caste_end",
                "role": "swarm",
                "caste": f"worker-{index + 1}",
                "outcome": "ok",
            }
            any_work = any_work or any(r.wrote for r in results)

    # 3. SYNTHESIZE from verifier evidence (skipped if no worker produced work).
    if any_work:
        synthesizer = _run_leg(
            make_agent,
            shared,
            "synthesizer",
            SYNTHESIZER_PROMPT,
            SYNTHESIZER_TOOLS,
            max_iters=6,
        )
        yield from synthesizer.events
        if synthesizer.stopped:
            return
        yield {
            "type": "caste_end",
            "role": "swarm",
            "caste": "synthesizer",
            "outcome": "ok",
        }

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
