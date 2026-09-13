"""Earned autonomy fell back to running on the host.

`AIOS_PROFILE` defaults to `"development"`. In that profile `get_executor`
(aios/api/deps.py) passes `command_runner=None`, and `Executor.__init__` resolves
`self.runner = runner or _default_runner` -- a real host subprocess. Measured
2026-09-13 with the variable unset: `runner is _default_runner` is True and
`getattr(runner, "is_private_service", False)` is False.

That is survivable for GREEN, and for YELLOW that a human just approved: someone
chose. Earned autonomy is the case where NOBODY chose. A repeatedly-clean YELLOW
class is promoted to automatic, and `pytest` is YELLOW -- so an earned `pytest`
imports and executes project code on the operator's machine with no approval and
no container.

Scope-lock, argv parsing and the classifier regexes are real controls, but none
of them is an OS boundary; they constrain which command runs, not what that
command can then do once the interpreter is executing.

So the fallback now fails closed, and ONLY for earned autonomy. Refusing every
unisolated execution would break local development and the whole GREEN surface,
which is not what the finding is about.
"""

from __future__ import annotations

import pytest

from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.core.executor import Executor, _default_runner

YELLOW_COMMAND = "pytest"


class _SpyRunner:
    """Records whether the command ever reached a runner."""

    def __init__(self, *, isolated: bool) -> None:
        self.calls: list[str] = []
        if isolated:
            self.is_private_service = True

    def __call__(self, command: str, *, cwd: str, env: dict, timeout_s: int):
        self.calls.append(command)
        return ("", "", 0)


def _executor_with(runner: _SpyRunner) -> Executor:
    """An executor whose kernel always grants earned autonomy.

    The stop is wired explicitly: since #329 an ABSENT emergency stop is itself
    a refusal, so a bare `Executor()` blocks every command before reaching a
    runner -- which would make each assertion below pass or fail for the wrong
    reason.
    """
    executor = Executor(runner=runner, emergency_stop=UNGOVERNED_FIXTURE)
    executor.policy_kernel.autonomy.is_earned = lambda *a, **k: True
    executor.policy_kernel.earned_autonomy_enabled = lambda: True
    return executor


def test_the_default_profile_really_has_no_isolated_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The premise. If the default profile were isolated, the rest is moot."""
    monkeypatch.delenv("AIOS_PROFILE", raising=False)

    executor = Executor()

    assert executor.runner is _default_runner
    assert getattr(executor.runner, "is_private_service", False) is False


def test_earned_autonomy_is_refused_without_an_isolated_runner() -> None:
    """THE BAR. Nobody approved this, so something other than a regex must contain it."""
    runner = _SpyRunner(isolated=False)
    executor = _executor_with(runner)

    result = executor.execute(YELLOW_COMMAND)

    assert runner.calls == [], (
        "an earned-autonomy YELLOW command reached a non-isolated runner: "
        f"{runner.calls}"
    )
    assert result.status == "BLOCKED"
    assert result.control == "isolation_required"


def test_earned_autonomy_proceeds_when_isolation_exists() -> None:
    """A guard that refuses the configured case would just disable the feature."""
    runner = _SpyRunner(isolated=True)
    executor = _executor_with(runner)

    result = executor.execute(YELLOW_COMMAND)

    assert runner.calls == [YELLOW_COMMAND], "isolated earned autonomy was refused"
    assert result.status != "BLOCKED"


def test_green_commands_still_run_without_isolation() -> None:
    """Scoped deliberately. Failing closed on GREEN would break local development."""
    runner = _SpyRunner(isolated=False)
    executor = _executor_with(runner)

    result = executor.execute("echo hi")

    assert runner.calls == ["echo hi"], (
        "a GREEN command was caught by the isolation gate"
    )
    assert result.status != "BLOCKED"


def test_a_human_approved_yellow_still_runs_without_isolation() -> None:
    """A human chose. That is a different question from earned autonomy.

    `execute_approved` carries an explicit decision by the operator; the finding
    is about the path where no one is in the loop. Widening the refusal to here
    would change a documented product behaviour, not close the hole.
    """
    runner = _SpyRunner(isolated=False)
    executor = _executor_with(runner)

    result = executor.execute_approved(YELLOW_COMMAND)

    assert runner.calls == [YELLOW_COMMAND], "an operator-approved YELLOW was refused"
    assert result.status != "BLOCKED"
