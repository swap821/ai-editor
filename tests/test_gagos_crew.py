"""GAGOS's crew at work on a task (2026-11-11): the lead plans, workers change
their own files in their own copies, and the change is recorded as one group of
proposals under the task. No model is called here: the agents are stand-ins
that do to their copies what an agent's file tools would."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aios.maintenance import crew_agents as ca
from aios.maintenance import daily_work as dw
from tests.test_gagos_daily import _result
from tools import gagos_crew as crew

A = "frontend/src/a.ts"
OLD = "frontend/src/old.ts"
NEW = "frontend/src/fresh.ts"


def _git(root, *args) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture()
def setup(tmp_path):
    root = tmp_path / "project"
    (root / "frontend/src").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "core.autocrlf", "false")
    (root / A).write_bytes(b"export const a = 1;\n")
    (root / OLD).write_bytes(b"export const old = 1;\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    led = dw.DailyLedger(tmp_path / "l.db")
    tid = led.add_task(A, "Make a 2, add fresh.ts, retire old.ts", said_by="operator")
    return root, led, tid, tmp_path / "crew"


class Foundry:
    """Runs every leg; records the mission it admitted them under."""

    def __init__(self):
        self.missions = []

    def run_batch(self, mission_id, legs):
        self.missions.append((mission_id, [leg.files for leg in legs]))
        out = []
        for leg in legs:
            try:
                leg.run()
                out.append(None)
            except Exception as exc:  # as the Foundry reports a failed leg
                out.append(exc)
        return out


def _agents(plan, work):
    """A stand-in for :func:`crew_agents.run_agent`: the lead (read-only)
    answers *plan*; a worker applies ``work[its first file]`` to its copy."""
    seen = []

    def run(argv, prompt, cwd, timeout_s=0):
        write = argv[argv.index("--tools") + 1].endswith("Write")
        seen.append(("worker" if write else "lead", Path(cwd).name))
        if not write:
            return (
                ca.AgentRun(plan, 3, 1.0)
                if not isinstance(plan, str)
                else ca.AgentRun(None, 0, 1.0, plan)
            )
        mine = prompt.split("ONLY these files (create them if new): ", 1)[1]
        own = mine.splitlines()[0].split(", ")
        first = next(f for f in work if f in own)
        work[first](Path(cwd))
        return ca.AgentRun("done", 5, 1.0)

    return run, seen


def _clean(root, texts, **kw):
    return {rel: _result() for rel in texts}


def _go(setup, plan, work):
    root, led, tid, work_dir = setup
    run, seen = _agents(plan, work)
    foundry = Foundry()
    line = crew.crew_task(
        led,
        root,
        led.task(tid),
        redact=lambda t: t,
        check_texts=_clean,
        foundry=foundry,
        work_dir=work_dir,
        run_agent=run,
    )
    return line, led, tid, seen, foundry


PLAN = {
    "summary": "two workers",
    "subtasks": [
        {"title": "a", "instructions": "a = 2", "files": [A]},
        {
            "title": "files",
            "instructions": "add fresh, retire old",
            "files": [NEW, OLD],
        },
    ],
}


def _edit_a(cwd):
    (cwd / A).write_bytes(b"export const a = 2;\n")


def _swap(cwd):
    (cwd / NEW).write_bytes(b"export const fresh = 1;\n")
    (cwd / OLD).unlink()


def test_the_crew_plans_works_in_parallel_and_records_one_group(setup) -> None:
    line, led, tid, seen, foundry = _go(setup, PLAN, {A: _edit_a, NEW: _swap})
    assert line.startswith(f"task {tid}: the crew (2 worker(s)) proposed 3 file(s)")
    assert seen[0] == ("lead", "lead") and sorted(s[1] for s in seen[1:]) == [
        "w1",
        "w2",
    ]
    assert foundry.missions == [(f"crew:{tid}", [(A,), (NEW, OLD)])]
    by_rel = {p["rel"]: p for p in led.proposals()}
    assert by_rel[A]["new_text"] == "export const a = 2;\n" and by_rel[A]["op"] is None
    assert by_rel[NEW]["op"] == dw.OP_CREATE and by_rel[NEW]["base_text"] == ""
    assert by_rel[OLD]["op"] == dw.OP_DELETE and by_rel[OLD]["new_text"] == ""
    assert {p["group_id"] for p in by_rel.values()} == {tid}
    assert {p["status"] for p in by_rel.values()} == {"proposed"}
    assert by_rel[A]["model"].startswith("crew:")
    assert led.task(tid)["status"] == "taken"


def test_a_worker_that_touches_another_workers_file_stops_the_change(setup) -> None:
    def greedy(cwd):
        _edit_a(cwd)
        (cwd / OLD).write_bytes(b"export const old = 'mine';\n")

    line, led, tid, _seen, _f = _go(setup, PLAN, {A: greedy, NEW: _swap})
    assert "changed files its sub-task does not name: frontend/src/old.ts" in line
    assert led.task(tid)["status"] == "refused" and led.proposals() == []


def test_a_lead_that_fails_leaves_the_task_open(setup) -> None:
    line, led, tid, seen, _f = _go(setup, "usage limit reached", {})
    assert "stays open: the lead failed: usage limit reached" in line
    assert led.task(tid)["status"] == "open" and [s[0] for s in seen] == ["lead"]


def test_an_overlapping_plan_is_refused_before_any_worker_starts(setup) -> None:
    plan = {
        "summary": "",
        "subtasks": [
            {"title": "a", "instructions": "x", "files": [A]},
            {"title": "b", "instructions": "y", "files": [A]},
        ],
    }
    line, led, tid, seen, _f = _go(setup, plan, {})
    assert "in two sub-tasks" in line and led.task(tid)["status"] == "refused"
    assert [s[0] for s in seen] == ["lead"]


def test_each_worker_gets_gagoss_test_server_on_its_own_copy(tmp_path) -> None:
    import json

    cfg = crew.mcp_config(tmp_path / "proj", tmp_path / "w1.json", tmp_path / "m.json")
    server = json.loads(cfg.read_text())["mcpServers"]
    assert list(server) == ["gagos"], "no other MCP server"
    args = server["gagos"]["args"]
    assert args[0].endswith("gagos_crew_mcp.py")
    assert args[args.index("--state") + 1] == str(tmp_path / "w1.json")


def test_the_crew_is_off_until_switched_on(monkeypatch) -> None:
    monkeypatch.delenv("AIOS_GAGOS_CREW", raising=False)
    assert not crew.crew_enabled()
    monkeypatch.setenv("AIOS_GAGOS_CREW", "1")
    assert crew.crew_enabled()


def test_a_plan_on_a_file_gagos_has_in_flight_makes_the_task_wait(setup) -> None:
    root, led, tid, work_dir = setup
    run, seen = _agents(PLAN, {A: _edit_a, NEW: _swap})
    line = crew.crew_task(
        led,
        root,
        led.task(tid),
        redact=lambda t: t,
        check_texts=_clean,
        foundry=Foundry(),
        work_dir=work_dir,
        run_agent=run,
        busy=frozenset({OLD}),
    )
    assert line == f"task {tid} waits: an unmerged GAGOS change holds {OLD}"
    assert led.task(tid)["status"] == "open" and [s[0] for s in seen] == ["lead"]
