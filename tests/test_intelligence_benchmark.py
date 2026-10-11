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


# --------------------------------------------------------------------------- #
# From reports to router calibration
# --------------------------------------------------------------------------- #


def _report(
    model: str, passed: list, category: str = "coding", suite: str = "basic"
) -> dict:
    return {
        "generated_at": "2026-10-11T00:00:00+00:00",
        "suite": suite,
        "results": [
            {
                "model": model,
                "outcomes": [{"category": category, "passed": p} for p in passed],
            }
        ],
    }


def test_rates_combine_reports_and_never_count_errors() -> None:
    basic = _report("bedrock:m", [True] * 9 + [None] * 3)
    hard = _report("bedrock:m", [True, False, None], suite="hard")
    rated = ib.emit_rates([basic, hard])
    rows = {(r["provider"], r["model"], r["task"]): r for r in rated["rates"]}
    coding = rows[("bedrock", "m", "coding")]
    assert coding["n"] == 11, "9 + 2 answered; the 4 errors are not answers"
    assert coding["rate"] == round(10 / 11, 4)
    assert rows[("bedrock", "m", "general")]["n"] == 11
    assert rated["suites"] == ["basic", "hard"]


def test_too_few_answers_are_not_rated() -> None:
    rated = ib.emit_rates([_report("ollama:tiny", [True] * 9)])
    assert rated["rates"] == []


def test_live_evidence_overrides_the_benchmark(tmp_path) -> None:
    from aios.core import benchmark_rates as br

    path = tmp_path / "rates.json"
    path.write_text(
        '{"rates": [{"provider": "bedrock", "model": "m", "task": "coding", "rate": 0.9, "n": 30},'
        ' {"provider": "bedrock", "model": "n", "task": "coding", "rate": 1.5, "n": 30}]}',
        encoding="utf-8",
    )
    br._load.cache_clear()
    merged = br.merged_rates({("bedrock", "m", "coding"): 0.4}, path)
    assert merged[("bedrock", "m", "coding")] == 0.4, "real work outranks a test"
    assert merged[("bedrock", "n", "coding")] == 1.0, "a rate is clamped to [0, 1]"
    br._load.cache_clear()


def test_a_missing_rates_file_is_no_prior(tmp_path) -> None:
    from aios.core import benchmark_rates as br

    br._load.cache_clear()
    assert br.benchmark_rates(tmp_path / "absent.json") == {}
    br._load.cache_clear()


def test_the_router_reads_the_merged_rates(monkeypatch) -> None:
    from aios.core import benchmark_rates as br
    from aios.core import router_wiring

    monkeypatch.setattr(
        router_wiring,
        "_router_policy",
        lambda: __import__("aios.core.router", fromlist=["Policy"]).Policy(
            cloud_tasks=frozenset({"coding"})
        ),
    )
    monkeypatch.setattr(
        br, "benchmark_rates", lambda path=None: {("bedrock", "m", "coding"): 0.9}
    )

    class Development:
        def model_task_success_rates(self):
            return {("bedrock", "x", "coding"): 0.5}

    metrics = router_wiring._route_metrics(Development(), "auto")
    assert metrics == {("bedrock", "m", "coding"): 0.9, ("bedrock", "x", "coding"): 0.5}


def test_the_shipped_rates_exist_and_are_well_formed() -> None:
    """The prior ships with the code. A fresh checkout (CI) has no file only
    if it was ignored or dropped -- which happened once: aios/core/data/ is
    git-ignored by the repo's `data` rule."""
    from aios.core import benchmark_rates as br

    assert br.RATES_PATH.is_file(), br.RATES_PATH
    br._load.cache_clear()
    rates = br.benchmark_rates()
    assert len(rates) >= 10
    assert all(0.0 <= rate <= 1.0 for rate in rates.values())
    assert {task for (_p, _m, task) in rates} >= {"coding", "reasoning", "general"}
