"""Loop safety must stop spinning without stopping debugging.

`_detect_agent_loop` trips on three identical calls, or on a four-call
`A->B->A->B` alternation. `_tool_call_history` used to be cleared only at the
start of `run()`, so those patterns were evaluated across the whole turn.

Edit -> test -> edit -> test IS `A->B->A->B`. The canonical debugging loop was
therefore indistinguishable from spinning, and the agent was stopped exactly
when it started iterating toward a fix. Organ 44's golden cohort lost a mission
to "Agent loop detected" while doing that, and two more stalled as near misses
(7-of-9 and 4-of-5 assertions) that an agent allowed to re-test might have
closed.

This is the change in this PR most capable of weakening a real safety control,
so the no-progress cases are pinned as hard as the progress ones. A loop
detector that never fires is worse than the bug it replaced.
"""

from __future__ import annotations

import pytest

from aios.agents.tool_agent import ToolAgent


def _call(name: str, **args: object) -> dict[str, object]:
    return {"function": {"name": name, "arguments": args}}


@pytest.fixture()
def agent() -> ToolAgent:
    """A ToolAgent with only loop-safety state initialised.

    `_detect_agent_loop` and `note_progress` touch nothing else, so the loop
    machinery is exercised directly rather than through a full agent
    construction that would drag in an LLM, an executor and a gateway.
    """
    instance = ToolAgent.__new__(ToolAgent)
    instance._tool_call_history = []
    instance._repeated_tool_threshold = 3
    instance._last_verify_output = None
    return instance


# --------------------------------------------------------------------------- #
# The control must still fire.
# --------------------------------------------------------------------------- #


def test_three_identical_calls_with_no_progress_still_trip(agent) -> None:
    """The original protection, unchanged: repeating one action forever with
    nothing changing in between is still a loop."""
    call = _call("run_command", command="pytest -q")
    assert agent._detect_agent_loop([call]) is None
    assert agent._detect_agent_loop([call]) is None
    assert agent._detect_agent_loop([call])


def test_alternating_two_calls_with_no_progress_still_trip(agent) -> None:
    """A->B->A->B with nothing landing in between is genuine oscillation."""
    a = _call("read_file", filepath="x.py")
    b = _call("read_file", filepath="y.py")
    assert agent._detect_agent_loop([a]) is None
    assert agent._detect_agent_loop([b]) is None
    assert agent._detect_agent_loop([a]) is None
    assert agent._detect_agent_loop([b])


def test_progress_does_not_disarm_the_detector_permanently(agent) -> None:
    """After progress the window restarts -- it does not switch off. An agent
    that writes a file once and then spins forever is still caught."""
    agent._detect_agent_loop([_call("run_command", command="pytest -q")])
    agent.note_progress("file write applied")

    call = _call("run_command", command="pytest -q")
    assert agent._detect_agent_loop([call]) is None
    assert agent._detect_agent_loop([call]) is None
    assert agent._detect_agent_loop([call])


# --------------------------------------------------------------------------- #
# The debugging loop must survive.
# --------------------------------------------------------------------------- #


def test_edit_test_edit_test_is_not_a_loop(agent) -> None:
    """The exact sequence that was being killed.

    Every write lands, so every repeat acts on different bytes than the one
    before it. That is iteration, not repetition.
    """
    edit = _call("edit_file", filepath="calc.py")
    test = _call("run_command", command="pytest -q calc.py")

    for _ in range(4):
        assert agent._detect_agent_loop([edit]) is None
        agent.note_progress("file write applied")
        assert agent._detect_agent_loop([test]) is None
        agent.note_progress("verifier verdict changed")


def test_retesting_after_a_changed_verdict_is_not_a_loop(agent) -> None:
    """An identical pytest command run again after the verdict moved.

    "2 failed" becoming "1 failed" means the edit in between did something,
    even though the command is byte-identical.
    """
    test = _call("run_command", command="pytest -q")
    for _ in range(5):
        assert agent._detect_agent_loop([test]) is None
        agent.note_progress("verifier verdict changed")


def test_note_progress_is_safe_on_an_empty_history(agent) -> None:
    """Called before any tool call has been made -- must not raise, and must
    not log a reset that never happened."""
    agent.note_progress("approved writes applied")
    assert agent._tool_call_history == []


# --------------------------------------------------------------------------- #
# When it fires, it must say what it saw.
# --------------------------------------------------------------------------- #


def test_the_reason_names_the_repeated_call(agent) -> None:
    """The detector used to return a bare bool.

    The error it produced said only "the model repeated the same action(s)" --
    never which ones. Diagnosing a single occurrence meant re-running the
    mission under a tracer, because the one component that knew the answer
    threw it away. That is what this session actually had to do to establish
    that a real `Agent loop detected` was correct rather than a false positive.
    """
    call = _call("read_file", filepath="training_ground/test_calculator.py")
    agent._detect_agent_loop([call])
    agent._detect_agent_loop([call])
    reason = agent._detect_agent_loop([call])

    assert reason, "the detector fired without saying why"
    assert "read_file" in reason, f"the reason does not name the tool: {reason}"
    assert "test_calculator.py" in reason, (
        f"the reason does not identify WHICH call repeated: {reason}"
    )
    assert "3 times" in reason


def test_the_alternating_reason_names_both_calls(agent) -> None:
    """Oscillation is a different failure from repetition, and says so."""
    a = _call("read_file", filepath="a.py")
    b = _call("read_file", filepath="b.py")
    agent._detect_agent_loop([a])
    agent._detect_agent_loop([b])
    agent._detect_agent_loop([a])
    reason = agent._detect_agent_loop([b])

    assert reason
    assert "alternated" in reason
    assert "a.py" in reason and "b.py" in reason, (
        f"an oscillation reason that names neither side is not diagnosable: {reason}"
    )


def test_a_huge_argument_is_truncated_in_the_reason(agent) -> None:
    """Arguments carry whole file bodies; this text reaches an operator.

    A create_file call can hold a few KB of source. Pasting that into an error
    message turns a diagnostic into a wall of code.
    """
    call = _call("create_file", filepath="x.py", content="x = 1\n" * 500)
    agent._detect_agent_loop([call])
    agent._detect_agent_loop([call])
    reason = agent._detect_agent_loop([call])

    assert reason
    assert len(reason) < 300, f"reason is {len(reason)} chars; it must stay readable"
    assert "..." in reason, "a long argument should be visibly truncated"


# ── the step budget must fit the recovery path the system recommends ──────────

def test_the_step_budget_can_walk_the_recovery_path_it_recommends() -> None:
    """A way forward the budget cannot reach is not a way forward.

    The measured dominant failure in organ 44's golden cohort was `edit_file`
    BLOCKED on "old_string not found" -- 7 of 10 unverified steps. #240 gave
    that dead end an exit: the error names `overwrite_file` with the complete
    body. Walking it costs, at minimum:

        read_file 1, edit_file 2 (fails), overwrite_file 3, verify 4 (may fail),
        fix 5, verify 6

    With the previous hardcoded `DEFAULT_MAX_ITERS = 5` the turn ended on the
    step where the guidance began, so the recovery could never be observed to
    work or fail. This asserts the budget is large enough to take the advice at
    least once with room to verify, because a cap below that measures the cap
    rather than the model.
    """
    from aios.agents.tool_agent import DEFAULT_MAX_ITERS

    minimum_recovery_path = 6
    assert DEFAULT_MAX_ITERS >= minimum_recovery_path + 2, (
        f"DEFAULT_MAX_ITERS={DEFAULT_MAX_ITERS} cannot complete the "
        f"read->edit(fail)->overwrite->verify(fail)->fix->verify path "
        f"({minimum_recovery_path} steps) with any margin. Raising the cap is "
        "not a weakened control: repetition is still stopped by "
        "_detect_agent_loop, which bounds spinning independently of this number."
    )


def test_the_step_budget_is_operator_tunable() -> None:
    """The cap was hardcoded, so measuring a different one meant editing code."""
    from aios import config
    from aios.agents import tool_agent

    assert tool_agent.DEFAULT_MAX_ITERS == config.AGENT_MAX_ITERS
