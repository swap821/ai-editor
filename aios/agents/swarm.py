"""Ephemeral worker swarm over the single supervised tool loop — ant-colony.

REACHABLE THROUGH THE WORKER FOUNDRY (2026-11-09).
--------------------------------------------------
From 2026-07-15 to 2026-11-09 ``generate_pipeline`` refused every swarm turn
(``strategy_unavailable``: "route it through WorkerFoundry before enabling"),
and this banner said it was dormant. A turn with ``swarm`` now runs here, and
every caste leg is a worker the Foundry admits
(:mod:`aios.application.workers.swarm_foundry`): the emergency stop is checked
at each admission, the scheduler bounds the legs, and each leg's lifecycle lands
on the cortex bus. ``role_pass`` is still refused. Pinned by
``tests/test_documented_reachability.py``: if the Foundry route goes, this
banner must be rewritten.


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

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from aios import config
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.agents.tool_agent import STEP_LIMIT_TEXT
from aios.security.secret_scanner import scan_and_redact

logger = logging.getLogger(__name__)

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

    @property
    def status(self) -> str:
        """How the leg ended, as the Worker Foundry records a worker."""
        if not self.stopped:
            return "completed"
        if any(e.get("type") == "human_required" for e in self.events):
            return "awaiting_approval"
        return "failed"


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
    admit: Optional[LegAdmission] = None,
) -> _LegResult:
    """Run the QUORUM caste for one subtask's redundant replicas."""
    role = f"quorum-{subtask_index + 1}"
    note = _format_quorum_note(subtask, results)
    return _run_leg(
        make_agent,
        shared,
        role,
        QUORUM_PROMPT,
        QUORUM_TOOLS,
        note=note,
        max_iters=4,
        admit=admit,
    )


#: How a leg runs as an admitted worker: ``admit(role, tools, run)`` returns
#: ``run()``'s result, or raises when the boundary refuses the leg (an
#: emergency stop). Production passes the Worker Foundry's
#: (aios/application/workers/swarm_foundry.py); tests may run legs directly.
LegAdmission = Callable[[str, frozenset[str], Callable[[], "_LegResult"]], "_LegResult"]


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
    admit: Optional[LegAdmission] = None,
) -> _LegResult:
    """Execute one caste leg and return its events + distilled handoff.

    With *admit*, the leg runs as one worker the boundary admits; a leg it
    refuses ends stopped, with an error event that says so.

    The leg is fully deterministic and state-local: it reads from ``shared`` but
    does NOT mutate it. The caller decides when (and whether) to deposit the
    distilled ``answer`` back into ``shared``.
    """
    if admit is not None:
        failed: list[BaseException] = []

        def leg() -> _LegResult:
            try:
                return _run_leg_now(
                    make_agent,
                    shared,
                    role,
                    prompt,
                    tools,
                    note=note,
                    max_iters=max_iters,
                    subtask_index=subtask_index,
                    cloud_provider=cloud_provider,
                )
            except BaseException as exc:
                failed.append(exc)
                raise

        try:
            return admit(role, tools, leg)
        except Exception as exc:  # noqa: BLE001 - a leg's own failure is re-raised below
            if failed and failed[0] is exc:
                # The leg's own failure, raised as a single agent's would be
                # (the correctness review of 2026-11-09: it was reported as a
                # refusal, unredacted and unlogged).
                raise
            logger.warning("swarm leg %s was not run", role, exc_info=exc)
            said = scan_and_redact(f"{type(exc).__name__}: {exc}").scrubbed
            return _LegResult(
                role=role,
                events=[
                    {
                        "type": "error",
                        "role": role,
                        "code": "worker_refused",
                        "text": f"the worker foundry did not run the {role} leg: {said}",
                    }
                ],
                answer="",
                wrote=False,
                stopped=True,
            )
    return _run_leg_now(
        make_agent,
        shared,
        role,
        prompt,
        tools,
        note=note,
        max_iters=max_iters,
        subtask_index=subtask_index,
        cloud_provider=cloud_provider,
    )


def _run_leg_now(
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
    """One caste leg, run here and now."""
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
    cloud_burst: bool = False,
    make_cloud_agent: Optional[AgentFactory] = None,
    cloud_provider: Optional[str] = None,
    admit: Optional[LegAdmission] = None,
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
                admit=admit,
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
            admit=admit,
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
            admit=admit,
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
            admit=admit,
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
                quorum = _run_quorum(
                    make_agent, shared, index, subtask, results, admit=admit
                )
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
                if result.stopped:
                    # Several legs ran at once, so more than one may have
                    # stopped. The turn ends at this one; say what else waits,
                    # first, since the turn may not read past this leg's pause
                    # (the safety review of 2026-11-09: a second leg's approval
                    # request was dropped unsaid).
                    notice = _also_stopped(grouped, result)
                    if notice:
                        yield {"type": "text", "role": "swarm", "text": notice}
                    yield from result.events
                    return
                yield from result.events
            if replicas > 1:
                quorum = _run_quorum(
                    make_agent, shared, index, plan[index], results, admit=admit
                )
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
            admit=admit,
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


# --------------------------------------------------------------------------- #
# The colony for a council mission (2026-11-14)
# --------------------------------------------------------------------------- #
#
# The operator, 2026-11-14: "writers can be within colony as it was meant". A
# goal over several files runs as a colony inside its council mission: a SCOUT
# reuses a verified split from the pattern memory, or a DECOMPOSER splits the
# goal into parts over disjoint files; one WORKER per part, the mission's own
# writer, writes its part side by side with the others, each admitted by the
# Foundry; the mission's sandbox and reviewer judge the whole change, from
# evidence only (the synthesizer's rule). Its only shared media are the
# colony's: the goal, the files, and the trail of splits that verified.

COLONY_DECOMPOSER_SYSTEM = (
    "You are the DECOMPOSER of an ant colony of code writers. The goal and the files "
    "it changes are below, each under its label 'File N: name'. Do not write any "
    "code. Split the goal into a few INDEPENDENT parts that separate writers can do "
    "side by side, each on its own files, without seeing each other's work: a file "
    "belongs to one part at most, and a change that two files must agree on stays "
    "in one part. Answer only with a numbered list, one part per line, as "
    "'1. files 1,3: <what to change in those files>'. Describe each change in "
    "words; never copy a placeholder (GAGOSMASK...). One part is a fine answer "
    "when the goal cannot be split."
)

_COLONY_PART = re.compile(
    r"^\s*(?:\d+[.)]|[-*])\s*files?\s+([\d\s,]+?)\s*[:\-–—]\s*(\S.*?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ColonyPart:
    """One worker's part of a colony mission: its files (repository paths,
    disjoint from every other part's) and what to change in them."""

    files: tuple[str, ...]
    work: str

    def subtask(self) -> str:
        """How the trail remembers this part."""
        return f"{', '.join(self.files)}: {self.work}"


@dataclass
class ColonyRun:
    """What one colony did: its parts, how they were found (``reused`` a
    verified split, ``fresh`` from the decomposer, or ``single`` when there was
    nothing to split), and each worker's result, in the parts' order."""

    parts: list[ColonyPart]
    scout: str
    results: list[Any] = field(default_factory=list)
    pattern_id: Optional[int] = None


ColonyAdmission = Callable[[str, Callable[[], Any]], Any]


def parse_colony_parts(
    answer: str, files: list[str], *, limit: int
) -> list[ColonyPart]:
    """The decomposer's parts, by the files' numbers (from 1): ``[]`` when the
    answer is not a valid split -- a number out of range, a file in two parts,
    no parts, or more than *limit* -- so the colony works the goal as one part
    rather than fan out on noise."""
    parts: list[ColonyPart] = []
    taken: set[int] = set()
    for line in answer.splitlines():
        match = _COLONY_PART.match(line)
        if not match:
            continue
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        if not numbers or any(n < 1 or n > len(files) for n in numbers):
            return []
        mine = sorted(set(numbers))
        if taken & set(mine):
            return []
        taken |= set(mine)
        parts.append(ColonyPart(tuple(files[n - 1] for n in mine), match.group(2)))
    if not parts or len(parts) > max(1, limit):
        return []
    return parts


def _parts_from_trail(subtasks: list[str], files: list[str]) -> list[ColonyPart]:
    """A remembered split as this goal's parts, or ``[]`` when it names a file
    this goal does not change or names one twice."""
    parts: list[ColonyPart] = []
    seen: set[str] = set()
    for subtask in subtasks:
        named, sep, work = subtask.partition(": ")
        own = tuple(f.strip() for f in named.split(",") if f.strip())
        if not sep or not own or not work.strip():
            return []
        if any(f not in files or f in seen for f in own):
            return []
        seen.update(own)
        parts.append(ColonyPart(own, work.strip()))
    return parts


def run_writer_colony(
    goal: str,
    files: list[str],
    *,
    decompose: Callable[[], str],
    write_part: Callable[[ColonyPart], Any],
    admit: ColonyAdmission,
    pattern_memory: Optional[SwarmPatternMemory] = None,
    concurrency: int = config.SWARM_CLOUD_CONCURRENCY,
) -> ColonyRun:
    """Plan a goal over *files* as a colony and have its workers write it.

    The scout recalls verified splits of like goals; one that names only this
    goal's files is reused as it is. Otherwise the decomposer (admitted as a
    leg) splits the goal; an answer that is not a valid split leaves one part
    over every file. Each part is then *write_part*'s, run as an admitted
    worker leg, at most *concurrency* at once. A worker's exception is raised
    once every leg has finished, so none is left running unseen."""
    limit = max(1, min(len(files), config.SWARM_MAX_WORKERS))
    run: Optional[ColonyRun] = None
    if pattern_memory is not None and len(files) > 1:
        for pattern in pattern_memory.recall(goal, limit=3):
            reused = _parts_from_trail(list(pattern.get("subtasks") or []), files)
            if 1 < len(reused) <= limit:
                pattern_memory.bump_use(int(pattern["pattern_id"]))
                run = ColonyRun(reused, "reused", pattern_id=int(pattern["pattern_id"]))
                break
    if run is None and len(files) > 1:
        parts = parse_colony_parts(admit("decomposer", decompose), files, limit=limit)
        if len(parts) > 1:
            run = ColonyRun(parts, "fresh")
    if run is None:
        run = ColonyRun([ColonyPart(tuple(files), goal)], "single")
    width = max(1, min(int(concurrency), len(run.parts)))
    with ThreadPoolExecutor(max_workers=width, thread_name_prefix="colony") as pool:
        futures = [
            pool.submit(admit, "worker", lambda p=part: write_part(p))
            for part in run.parts
        ]
    failure: Optional[BaseException] = None
    for future in futures:
        try:
            run.results.append(future.result())
        except BaseException as exc:  # noqa: BLE001 - re-raised below, after every leg
            run.results.append(None)
            failure = failure or exc
    if failure is not None:
        raise failure
    return run


def _also_stopped(grouped: list[list[_LegResult]], first: _LegResult) -> str:
    """What the legs that ran beside *first* still wait for, said plainly."""
    waiting, others = [], 0
    for results in grouped:
        for result in results:
            if result is first:
                continue
            asks = [e for e in result.events if e.get("type") == "human_required"]
            if asks:
                waiting.append(f"{result.role}: {asks[0].get('command', 'an action')}")
            else:
                others += 1
    if not waiting and not others:
        return ""
    lines = [
        "\n\nThe colony's legs ran side by side, and this turn pauses at the first request."
    ]
    if waiting:
        lines.append(
            "Also waiting for your approval, asked again when the turn resumes: "
            + "; ".join(waiting)
            + "."
        )
    if others:
        lines.append(
            f"{others} other leg(s) ran and will run again when the turn resumes."
        )
    return " ".join(lines)


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
