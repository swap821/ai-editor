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
    assert agent._detect_agent_loop([call]) is False
    assert agent._detect_agent_loop([call]) is False
    assert agent._detect_agent_loop([call]) is True


def test_alternating_two_calls_with_no_progress_still_trip(agent) -> None:
    """A->B->A->B with nothing landing in between is genuine oscillation."""
    a = _call("read_file", filepath="x.py")
    b = _call("read_file", filepath="y.py")
    assert agent._detect_agent_loop([a]) is False
    assert agent._detect_agent_loop([b]) is False
    assert agent._detect_agent_loop([a]) is False
    assert agent._detect_agent_loop([b]) is True


def test_progress_does_not_disarm_the_detector_permanently(agent) -> None:
    """After progress the window restarts -- it does not switch off. An agent
    that writes a file once and then spins forever is still caught."""
    agent._detect_agent_loop([_call("run_command", command="pytest -q")])
    agent.note_progress("file write applied")

    call = _call("run_command", command="pytest -q")
    assert agent._detect_agent_loop([call]) is False
    assert agent._detect_agent_loop([call]) is False
    assert agent._detect_agent_loop([call]) is True


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
        assert agent._detect_agent_loop([edit]) is False
        agent.note_progress("file write applied")
        assert agent._detect_agent_loop([test]) is False
        agent.note_progress("verifier verdict changed")


def test_retesting_after_a_changed_verdict_is_not_a_loop(agent) -> None:
    """An identical pytest command run again after the verdict moved.

    "2 failed" becoming "1 failed" means the edit in between did something,
    even though the command is byte-identical.
    """
    test = _call("run_command", command="pytest -q")
    for _ in range(5):
        assert agent._detect_agent_loop([test]) is False
        agent.note_progress("verifier verdict changed")


def test_note_progress_is_safe_on_an_empty_history(agent) -> None:
    """Called before any tool call has been made -- must not raise, and must
    not log a reset that never happened."""
    agent.note_progress("approved writes applied")
    assert agent._tool_call_history == []
