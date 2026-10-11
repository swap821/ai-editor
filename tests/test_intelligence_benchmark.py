"""The intelligence benchmark scores honestly.

Pinned without any model: the answer key (every code snippet's real output
passes its checker; a plausible wrong answer fails), the final-answer parser,
an errored call is never scored, the Wilson interval, and a regex answer that
would backtrack forever cannot hang the run.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from tools import intelligence_benchmark as ib


@pytest.mark.parametrize(
    "task", [t for t in ib.TASKS if "```python" in t.prompt], ids=lambda t: t.task_id
)
def test_every_code_task_is_keyed_to_its_real_output(task) -> None:
    snippet = re.search(r"```python\n(.*?)\n```", task.prompt, re.S).group(1)
    out = subprocess.run(
        [sys.executable, "-c", snippet], capture_output=True, text=True
    ).stdout.strip()
    assert task.check(out), (task.task_id, out)


def test_the_task_set_is_fifteen_and_fifteen_with_unique_ids() -> None:
    assert sum(t.category == "coding" for t in ib.TASKS) == 15
    assert sum(t.category == "reasoning" for t in ib.TASKS) == 15
    assert len({t.task_id for t in ib.TASKS}) == 30


def test_the_last_answer_line_counts_and_none_is_none() -> None:
    assert ib.final_answer("ANSWER: 1\nthinking...\nANSWER: 42") == "42"
    assert ib.final_answer("no tag here") is None


def test_an_errored_call_is_never_scored() -> None:
    outcomes = [
        ib.Outcome("a", "coding", True, "1", 1.0),
        ib.Outcome("b", "coding", None, None, 1.0, "LLMError: down"),
        ib.Outcome("c", "reasoning", False, "x", 2.0),
    ]
    summary = ib.summarise(outcomes)
    assert summary["coding"] == {
        "passed": 1,
        "tasks": 2,
        "errors": 1,
        "accuracy": 0.5,
        "ci95": list(map(lambda v: round(v, 3), ib.wilson(1, 2))),
    }
    assert summary["all"]["passed"] == 1 and summary["all"]["errors"] == 1
    assert summary["median_seconds"] == 1.5, "errored calls are left out of latency"


def test_wilson_intervals() -> None:
    low, high = ib.wilson(15, 15)
    assert high == 1.0 and 0.79 < low < 0.81
    assert ib.wilson(0, 0) == (0.0, 0.0)


def test_a_backtracking_regex_cannot_hang_the_run() -> None:
    check = ib.regex_fullmatch(["a" * 30 + "!"], [])
    assert check("(a+)+$") is False  # catastrophic on 'aaaa...!': killed by the timeout


def test_a_missing_answer_line_is_wrong_not_an_error() -> None:
    class Silent:
        def chat(self, messages, *, tools=None, model=None):
            return {"content": "I think it is 56."}

    outcome = ib.ask(Silent(), "m", ib.TASKS[0])
    assert outcome.passed is False and outcome.error is None


def test_a_failing_client_is_an_error() -> None:
    class Down:
        def chat(self, messages, *, tools=None, model=None):
            raise RuntimeError("connection refused")

    outcome = ib.ask(Down(), "m", ib.TASKS[0])
    assert outcome.passed is None and "connection refused" in outcome.error
