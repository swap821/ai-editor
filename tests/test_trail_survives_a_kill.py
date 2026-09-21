"""A run that is killed must leave behind what it had already done.

The runner's module docstring has always promised this:

    "Every attempt appends an audit row whatever the outcome... A tool that
    only writes when it succeeds is how 'we ran it' becomes indistinguishable
    from 'it worked'."

It was not true. `_write_trail` ran once, at the end, so a killed or crashed
run left NOTHING on disk. On 2026-09-21 a stopped run's absence was briefly
read as the previous run's result -- the exact confusion the docstring warns
about, produced by the tool that warns about it.

The durability test here is not a mock. A child process writes one row and
then calls `os._exit`, which skips atexit hooks, buffer flushing and `finally`
blocks -- the closest thing to `kill -9` that a test can arrange. If the row is
readable afterwards, a killed run keeps its evidence.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tools import reverse_engineer_gagos as rg


@pytest.fixture()
def trail(tmp_path, monkeypatch):
    path = tmp_path / "runs.jsonl"
    monkeypatch.setattr(rg, "TRAIL", path)
    return path


def _rows(path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestDurability:
    def test_a_hard_exit_keeps_the_row(self, tmp_path) -> None:
        """`os._exit` skips every cleanup path Python has. The row must survive."""
        path = tmp_path / "runs.jsonl"
        child = (
            "import os, sys;"
            f"sys.path.insert(0, {str(rg.REPO_ROOT)!r});"
            "from tools import reverse_engineer_gagos as rg;"
            "import pathlib;"
            f"rg.TRAIL = pathlib.Path({str(path)!r});"
            "rg.record_attempt_row('run-1', rg.Attempt(target='t', outcome='rejected'));"
            "os._exit(1)"
        )
        result = subprocess.run(
            [sys.executable, "-c", child], capture_output=True, text=True
        )
        assert result.returncode == 1, result.stderr[-500:]

        rows = _rows(path)
        assert len(rows) == 1, (
            "the attempt was written and the process died immediately after; "
            "if nothing is here, a killed run still loses its evidence"
        )
        assert rows[0]["kind"] == "attempt"
        assert rows[0]["attempt"]["outcome"] == "rejected"

    def test_each_attempt_lands_before_the_next_one_starts(self, trail) -> None:
        """Durability is per attempt, not per run — that is the whole point."""
        rg.record_attempt_row("run-1", rg.Attempt(target="a", outcome="rejected"))
        assert len(_rows(trail)) == 1
        rg.record_attempt_row("run-1", rg.Attempt(target="b", outcome="earned"))
        assert len(_rows(trail)) == 2


class TestAPartialRunReadsAsPartial:
    """Silence and 'it earned nothing' must not look the same."""

    def test_attempts_without_a_summary_are_an_unfinished_run(self, trail) -> None:
        rg.record_attempt_row("run-1", rg.Attempt(target="a", outcome="rejected"))

        rows = _rows(trail)
        run_ids = {r["run_id"] for r in rows if r["kind"] == "attempt"}
        closed = {r["run_id"] for r in rows if r["kind"] == "run"}
        assert run_ids - closed == {"run-1"}, (
            "an attempt row with no matching summary row IS the partial-run "
            "signal; without it a killed run is indistinguishable from a run "
            "that never started"
        )

    def test_a_completed_run_closes_itself(self, trail) -> None:
        args = _Args()
        rg.record_attempt_row(
            "run-1", rg.Attempt(target="a", outcome="earned", earned=True)
        )
        rg._write_trail(
            args,
            [rg.Attempt(target="a", outcome="earned", earned=True)],
            run_id="run-1",
        )

        rows = _rows(trail)
        summary = [r for r in rows if r["kind"] == "run"]
        assert len(summary) == 1
        assert summary[0]["outcome"] == "completed"
        assert summary[0]["earned"] == 1

    def test_an_aborted_run_says_so_and_why(self, trail) -> None:
        """A grader that refused (hollow run) must be legible as a refusal."""
        rg._write_trail(
            _Args(), [], run_id="run-1", error="the suite run produced no output at all"
        )

        summary = [r for r in _rows(trail) if r["kind"] == "run"][0]
        assert summary["outcome"] == "aborted"
        assert "no output at all" in summary["error"]


class TestOlderRowsStillParse:
    def test_rows_written_before_this_change_are_readable(self, trail) -> None:
        """The existing trail has 8 rows with no `kind`; do not orphan them."""
        legacy = {"ts": "2026-09-21T09:27:06+00:00", "models": "x", "earned": 4}
        trail.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
        rg.record_attempt_row("run-1", rg.Attempt(target="a", outcome="earned"))

        rows = _rows(trail)
        assert len(rows) == 2
        assert rows[0].get("kind") is None, "a legacy row is a run row by default"
        assert rows[1]["kind"] == "attempt"


class _Args:
    models = "ollama.qwen2.5-coder:7b"
    targets = 4
    retries = 1


class TestRunIds:
    def test_two_runs_do_not_collide(self) -> None:
        assert rg.new_run_id() != rg.new_run_id()

    def test_a_run_id_sorts_by_time(self) -> None:
        """So `sort` on the trail is chronological without parsing timestamps."""
        first = rg.new_run_id()
        assert first[:4].isdigit() and "-" in first
