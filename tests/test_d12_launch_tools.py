"""D12's launch tools: the no-thinking local spec, the local-student rule, and
the parallel practice partition."""

from __future__ import annotations

import pytest

from aios.core.llm import OllamaClient
from tools import calibrate_local_student as cal
from tools import practice_parallel as pp
from tools.reverse_engineer_gagos import resolve_client


def test_nothink_spec_asks_the_local_model_not_to_think() -> None:
    client, tag = resolve_client("ollama.qwen3.5:9b@nothink", timeout_s=5)
    assert isinstance(client, OllamaClient)
    assert (client.model, tag, client.think) == ("qwen3.5:9b", "qwen3.5:9b", False)


def test_a_plain_local_spec_is_unchanged() -> None:
    client, tag = resolve_client("ollama.qwen2.5-coder:7b", timeout_s=5)
    assert (client.model, tag, client.think) == (
        "qwen2.5-coder:7b",
        "qwen2.5-coder:7b",
        None,
    )


def _result(earned: int, median: float) -> dict:
    return {"earned": earned, "reached": 20, "median_seconds": median, "targets": []}


def test_the_student_is_the_one_that_earns_most_without_memory() -> None:
    results = {
        "ollama.qwen2.5-coder:7b": _result(2, 40),
        "ollama.qwen3.5:9b@nothink": _result(6, 70),
        "ollama.granite4.2:8b": _result(4, 30),
    }
    assert cal.choose(results, {}) == "ollama.qwen3.5:9b@nothink"


def test_a_tie_goes_to_the_smaller_model_then_the_faster() -> None:
    results = {
        "ollama.big:9b@nothink": _result(5, 10),
        "ollama.small:7b": _result(5, 90),
    }
    sizes = {"big:9b": 6_600_000_000, "small:7b": 4_700_000_000}
    assert cal.choose(results, sizes) == "ollama.small:7b"
    same_size = {"big:9b": 1, "small:7b": 1}
    assert cal.choose(results, same_size) == "ollama.big:9b@nothink"


@pytest.mark.parametrize(
    ("start", "count", "workers"),
    [(0, 156, 3), (0, 20, 3), (20, 136, 3), (0, 5, 1), (0, 2, 3)],
)
def test_the_partition_covers_every_target_exactly_once(start, count, workers) -> None:
    slices = pp.partition(start, count, workers)
    covered = [o + k for o, size in slices for k in range(size)]
    assert covered == list(range(start, start + count))
    assert len(slices) <= workers


def test_each_worker_has_its_own_store_corpus_and_trail(tmp_path) -> None:
    cmds = [
        pp.worker_command(
            index=i,
            offset=o,
            size=s,
            student="s",
            teacher="t",
            critic="c",
            retries=2,
            model_timeout=420,
            out=tmp_path,
            corpus_prefix="C:/d12cloud",
        )
        for i, (o, s) in enumerate(pp.partition(0, 156, 3))
    ]

    def value(cmd, flag):
        return cmd[cmd.index(flag) + 1]

    for flag in ("--db", "--corpus-dir", "--trail", "--offset"):
        assert len({value(c, flag) for c in cmds}) == 3, flag
    assert all(
        value(c, "--teacher") == "t" and value(c, "--critic") == "c" for c in cmds
    )
    assert all(value(c, "--models") == "s,t" for c in cmds)


def test_the_local_stream_refuses_more_than_one_worker(tmp_path) -> None:
    assert (
        pp.main(
            [
                "--stream",
                "local",
                "--workers",
                "2",
                "--student",
                "ollama.x",
                "--teacher",
                "t",
                "--count",
                "4",
                "--out",
                str(tmp_path),
                "--dry-run",
            ]
        )
        == 2
    )
