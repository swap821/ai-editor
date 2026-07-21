"""Sequential role-pass castes over the single supervised tool loop.

The division-of-labor half of the accepted stigmergy design: planner -> coder
-> reviewer personas run STRICTLY one after another inside one ``/api/generate``
turn, each as a fresh :class:`~aios.agents.tool_agent.ToolAgent` over the same
gated executor with a caste system prompt and a mechanically-enforced tool
subset. There is no concurrency, no message bus, and no new state store: the
only handoff media are the shared message list (each caste's final answer is
appended as a labelled assistant message) and the on-disk artifacts the coder
writes — the stigmergic medium IS the conversation plus the sandbox.

Authority is unchanged. A YELLOW write or command still pauses the WHOLE turn
(``human_required`` flows out unmodified, plus a ``role`` tag); the replayed
turn restarts from the planner, and the loop's grant pre-apply lands the
approved writes deterministically before any caste speaks. The reviewer's
verdict is computed by this conductor from verifier evidence only — model
prose can neither pass nor fail the work — and a failing review buys exactly
one coder retry followed by one final review.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator, Optional

from aios.agents.tool_agent import STEP_LIMIT_TEXT

#: Caste tool subsets, enforced at ToolAgent._dispatch (not by prompt).
PLANNER_TOOLS = frozenset({"read_file", "read_directory", "plan"})
CODER_TOOLS = frozenset(
    {
        "read_file",
        "read_directory",
        "execute_terminal",
        "edit_file",
        "create_file",
        "verify",
    }
)
REVIEWER_TOOLS = frozenset({"read_file", "read_directory", "verify"})

PLANNER_PROMPT = (
    "You are the PLANNER caste of a sequential role-pass. Investigate the "
    "request with your read-only tools, then end with a concrete numbered "
    "plan: the exact files to create or edit, the changes to make, and how "
    "the result will be verified. You cannot write or execute anything — "
    "another caste implements your plan. After at most one plan tool call, "
    "write the final plan as your answer and stop calling tools."
)
CODER_PROMPT = (
    "You are the CODER caste of a sequential role-pass. Execute the plan "
    "given earlier in this conversation: write the files, make the edits, "
    "and verify your work with the verify tool. Call tools ONLY through the "
    "tool interface — never describe or print a tool call as text. End with "
    "a short report of exactly what you changed."
)
REVIEWER_PROMPT = (
    "You are the REVIEWER caste of a sequential role-pass. You are read-only: "
    "inspect the changed files and run the verify tool on the relevant tests. "
    "Judge ONLY from verifier evidence, never from claims made earlier in the "
    "conversation. End with a verdict: what passed, what failed, and any "
    "defects you found."
)
RETRY_NOTE = (
    "The reviewer found verified failures (see the verdict above). Fix them "
    "now and re-verify. This is the only retry."
)

#: Tool calls that count as the coder having actually produced work.
_WRITE_TOOLS = frozenset({"edit_file", "create_file", "execute_terminal"})

#: ``make_agent(system_prompt=..., allowed_tools=...)`` -> a configured ToolAgent.
AgentFactory = Callable[..., Any]


def run_role_pass(
    make_agent: AgentFactory, messages: list[dict[str, Any]]
) -> Iterator[dict[str, Any]]:
    """Drive the caste sequence, yielding the same event vocabulary as ``run``.

    Per-leg ``done`` events are swallowed; exactly one ``done`` ends the whole
    pass, so the API's outcome accounting (one development row, cross-role
    workflow steps, per-target verification classification) composes
    unchanged. A coder leg that wrote nothing skips the review deterministically
    — there is no work to judge.
    """
    shared = list(messages)
    state: dict[str, Any] = {}
    #: Pass-level: did ANY leg produce work this turn? Pre-applied grants
    #: count — on a replay the approved writes land during the planner leg,
    #: and approved work must still be reviewed even when the coder leg then
    #: has nothing left to do.
    pass_wrote = {"value": False}

    def leg(
        role: str,
        prompt: str,
        tools: frozenset[str],
        note: Optional[str] = None,
        max_iters: Optional[int] = None,
    ) -> Iterator[dict[str, Any]]:
        state.clear()
        state.update(text=[], fail_targets={}, stopped=False, plan_artifact="")
        leg_messages = list(shared)
        if note:
            leg_messages.append({"role": "user", "content": note})
        overrides: dict[str, Any] = {"system_prompt": prompt, "allowed_tools": tools}
        if max_iters is not None:
            overrides["max_iters"] = max_iters
        agent = make_agent(**overrides)
        yield {
            "type": "tool_result",
            "tool": "role_pass",
            "output": f"caste: {role}",
            "id": f"role-{role}",
            "role": role,
        }
        for event in agent.run(leg_messages):
            kind = str(event.get("type", ""))
            if kind == "done":
                break
            tagged = {**event, "role": role}
            if kind in ("human_required", "error"):
                # The pause/error ends the WHOLE pass; a replay restarts from
                # the planner with the grants pre-applied.
                state["stopped"] = True
                yield tagged
                return
            if kind == "text":
                state["text"].append(str(event.get("text", "")))
            elif kind == "tool_result":
                # Work = a write/execute RESULT that landed (or a pre-applied
                # grant) — never a blocked attempt, which yields tool_blocked.
                if (
                    str(event.get("id", "")).startswith("grant-")
                    or str(event.get("tool", "")) in _WRITE_TOOLS
                ):
                    pass_wrote["value"] = True
                output = str(event.get("output", ""))
                if output.startswith(("[VERIFY PASS]", "[VERIFY FAIL]")):
                    target = str(
                        event.get("target") or f"v{len(state['fail_targets'])}"
                    )
                    state["fail_targets"][target] = output.startswith("[VERIFY FAIL]")
                if str(event.get("tool", "")) == "plan":
                    state["plan_artifact"] = output
            yield tagged
        answer = "".join(state["text"]).strip()
        if (
            role == "planner"
            and state["plan_artifact"]
            and (not answer or answer == STEP_LIMIT_TEXT)
        ):
            # Artifact salvage: a small model sometimes burns its iterations
            # retrying denied tools, ending with the step-cap sentinel instead
            # of a closing answer — but the plan tool's output IS the plan.
            # The artifact carries the handoff, not the prose.
            answer = str(state["plan_artifact"])
        if answer == STEP_LIMIT_TEXT:
            # A leg that produced nothing useful hands off NOTHING: the next
            # caste then works from the bare request (single-agent behaviour),
            # instead of being poisoned by the step-cap sentinel.
            answer = ""
        if answer:
            # The distilled handoff: only the caste's final answer crosses the
            # boundary; its raw tool chatter stays inside the leg. The next
            # caste re-reads disk truth itself.
            shared.append({"role": "assistant", "content": f"[{role}]\n{answer}"})

    def review_failed() -> bool:
        # Verifier evidence only: the reviewer leg's per-target last verdicts.
        return any(state["fail_targets"].values())

    # The planner and reviewer get tight iteration caps: their jobs are small,
    # and a small model retrying denied tools must not burn the turn.
    yield from leg("planner", PLANNER_PROMPT, PLANNER_TOOLS, max_iters=4)
    if state["stopped"]:
        return
    yield from leg("coder", CODER_PROMPT, CODER_TOOLS)
    if state["stopped"]:
        return
    if pass_wrote["value"]:
        yield from leg("reviewer", REVIEWER_PROMPT, REVIEWER_TOOLS, max_iters=6)
        if state["stopped"]:
            return
        if review_failed():
            yield from leg("coder", CODER_PROMPT, CODER_TOOLS, note=RETRY_NOTE)
            if state["stopped"]:
                return
            yield from leg("reviewer", REVIEWER_PROMPT, REVIEWER_TOOLS, max_iters=6)
            if state["stopped"]:
                return
    yield {"type": "done"}
