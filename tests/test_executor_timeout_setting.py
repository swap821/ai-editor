"""AIOS_EXECUTOR_TIMEOUT_S: the sandboxed command budget is a bounded setting.

2026-10-28: with the operator's backend allowed to verify this repository's own
tests (docs/operations/WORK_SCOPE.md), every test file that loads the API app
took 33-41 s in the 1-CPU sandbox and was killed at the executor's hard-coded
30 s, reported as TIMEOUT. The budget is now a setting: unchanged by default,
bounded both ways, and still overridden by an explicit per-executor budget.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from aios import config
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.core.executor import Executor
from aios.security.gateway import RateLimiter

REPO = Path(__file__).resolve().parents[1]


def _configured(tmp_path: Path, value: str | None) -> int:
    """config.EXECUTOR_TIMEOUT_S as a fresh process computes it."""
    env = {k: v for k, v in os.environ.items() if k != "AIOS_EXECUTOR_TIMEOUT_S"}
    env["AIOS_DATA_DIR"] = str(tmp_path / "data")
    if value is not None:
        env["AIOS_EXECUTOR_TIMEOUT_S"] = value
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "from aios import config; print(config.EXECUTOR_TIMEOUT_S)",
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return int(out.stdout.strip().splitlines()[-1])


def test_the_default_budget_is_the_one_the_executor_always_had(tmp_path) -> None:
    assert _configured(tmp_path, None) == 30 == config.EXECUTOR_TIMEOUT_S_DEFAULT


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("120", 120),
        ("1", 5),
        ("0", 5),
        ("-30", 5),
        ("99999", 600),
        ("not-a-number", 30),
    ],
)
def test_the_setting_is_honoured_and_bounded(tmp_path, raw, expected) -> None:
    """Neither a typo nor an extreme value can make every command time out or
    let one run unbounded."""
    assert _configured(tmp_path, raw) == expected


def _recording_executor(**kwargs) -> tuple[Executor, list[int]]:
    budgets: list[int] = []

    def runner(command, *, cwd, env, timeout_s):
        budgets.append(timeout_s)
        return "ok\n", "", 0  # the Runner contract: (stdout, stderr, exit_code)

    return (
        Executor(
            runner=runner,
            rate_limiter=RateLimiter(),
            audit_log=lambda *a, **k: None,
            emergency_stop=UNGOVERNED_FIXTURE,
            **kwargs,
        ),
        budgets,
    )


def test_an_executor_without_its_own_budget_runs_with_the_setting(monkeypatch) -> None:
    monkeypatch.setattr(config, "EXECUTOR_TIMEOUT_S", 120)
    executor, budgets = _recording_executor()
    assert executor.timeout_s == 120
    result = executor.execute("echo hi")
    assert result.status == "OK", result
    assert budgets == [120], "the runner was not handed the configured budget"


def test_an_explicit_budget_still_wins(monkeypatch) -> None:
    """The self-apply verifier passes its own 120 s; a setting must not move it."""
    monkeypatch.setattr(config, "EXECUTOR_TIMEOUT_S", 300)
    executor, budgets = _recording_executor(timeout_s=7)
    assert executor.timeout_s == 7
    executor.execute("echo hi")
    assert budgets == [7]
