"""A mission's writers as agents (2026-11-15, the operator: "624 utilize also
as per GAGOS"). #624's crew ran Claude Code agents with file tools and GAGOS's
sandboxed run_tests beside GAGOS's organs. Here they are a mission's workers.
Pinned, with a stand-in agent and no model:

* off by default: ``AIOS_GAGOS_AGENT_WORKERS=1`` switches them on;
* an agent works in a masked copy of the base, never the project; the one MCP
  server it may use is GAGOS's run_tests, whose state lives outside the copy;
* what it changed comes back restored and is recorded as the task's group of
  proposals through the static checks; a file it creates is a creation;
* a file outside its own, or a deletion, refuses its whole change; a file GAGOS
  may not edit refuses the goal before any agent is asked;
* the Claude Code agent is launched only by :class:`PlanAgentClient`: its file
  tools and GAGOS's MCP tool alone, the prompt through the privacy filter, the
  session one call recorded by the one gateway.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.core import plan_cli
from aios.maintenance import daily_work as dw
from aios.runtime.gagos_writer import WriterRefused
from tests.test_gagos_daily import _result
from tools import gagos_daily as tool

REL = "frontend/src/workbench/Panel.jsx"
NEW = "frontend/src/workbench/Fresh.jsx"
BEFORE = "export const panel = 1;\n"
AFTER = "export const panel = 2;\n"
GOAL = "Make the panel two, and add Fresh.jsx exporting fresh."


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture()
def project(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "frontend/src/workbench").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "core.autocrlf", "false")
    (root / REL).write_bytes(BEFORE.encode())
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setenv("AIOS_GAGOS_AGENT_WORKERS", "1")
    monkeypatch.setattr(tool, "colony_on", lambda: False)
    monkeypatch.setattr(tool, "goals_through_clerk", lambda: False)
    monkeypatch.setattr(tool, "project_facts", lambda root: ())
    monkeypatch.setattr(tool, "editable_frontend_files", lambda root: [REL])
    monkeypatch.setattr(
        tool, "check_texts", lambda root, texts, **kw: {k: _result() for k in texts}
    )
    return root, _git(root, "rev-parse", "HEAD"), led


def _work(project, files, agent):
    root, head, led = project
    tid = led.add_task(files[0], GOAL, said_by="operator", also=tuple(files[1:]))
    return tool.MissionWork(led, root, head, led.task(tid), region="r", agent=agent)


def _contract():
    return SimpleNamespace(mission_id="mission-0123456789ab", metadata={})


def _agent(edits, seen=None):
    """A stand-in agent: it writes *edits* into its copy, as its file tools
    would, and says what it did."""

    def agent(model, *, workdir, mcp_config):
        def complete(prompt, system, request_id):
            if seen is not None:
                seen.update(
                    model=model,
                    workdir=Path(workdir),
                    config=json.loads(Path(mcp_config).read_text(encoding="utf-8")),
                    prompt=prompt,
                    system=system,
                    request_id=request_id,
                    copy=(Path(workdir) / REL).read_text(encoding="utf-8"),
                )
            for rel, text in edits.items():
                path = Path(workdir) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            return "Changed the panel; run_tests: PASSED"

        return complete

    return agent


def test_agent_workers_are_off_until_switched_on(monkeypatch) -> None:
    monkeypatch.delenv("AIOS_GAGOS_AGENT_WORKERS", raising=False)
    assert not tool.agent_workers_on()
    monkeypatch.setenv("AIOS_GAGOS_AGENT_WORKERS", "1")
    assert tool.agent_workers_on()


def test_an_agent_edits_its_copy_and_its_change_is_the_tasks(project) -> None:
    seen: dict = {}
    work = _work(project, [REL, NEW], _agent({REL: AFTER, NEW: AFTER}, seen))
    edits = work.write(_contract())
    assert edits == {REL: AFTER, NEW: AFTER}
    root, _head, led = project
    members = led.group_members(work.task["task_id"])
    assert [(m["rel"], m["op"], m["status"]) for m in members] == [
        (NEW, "create", "proposed"),
        (REL, None, "proposed"),
    ]
    # The copy, never the project: the project is as it was.
    assert (root / REL).read_text(encoding="utf-8") == BEFORE
    assert not (root / NEW).exists()
    assert seen["copy"] == BEFORE and root not in seen["workdir"].parents
    # The one MCP server: GAGOS's run_tests, its state outside the copy.
    (server,) = seen["config"]["mcpServers"].values()
    assert server["args"][0].endswith("gagos_crew_mcp.py")
    state = Path(server["args"][server["args"].index("--state") + 1])
    assert seen["workdir"] not in state.parents
    # The prompt names its files and the test tool; the rules are the agent's.
    assert REL in seen["prompt"] and NEW in seen["prompt"]
    assert "run_tests" in seen["prompt"] and GOAL in seen["prompt"]
    assert seen["system"] == tool.AGENT_RULES
    assert seen["request_id"].startswith("gagos:mission-0123456789ab:agent:")
    # The copy is gone afterwards.
    assert not seen["workdir"].exists()


def test_a_file_outside_its_own_refuses_the_agents_change(project) -> None:
    other = "frontend/src/workbench/Other.jsx"
    work = _work(project, [REL], _agent({REL: AFTER, other: AFTER}))
    with pytest.raises(WriterRefused, match="a file outside its own"):
        work.write(_contract())
    _root, _head, led = project
    (only,) = led.group_members(work.task["task_id"])
    assert only["status"] == "refused" and "Other.jsx" in only["refusal"]


def test_an_agent_that_changes_nothing_is_refused(project) -> None:
    work = _work(project, [REL], _agent({}))
    with pytest.raises(WriterRefused, match="changed nothing"):
        work.write(_contract())


def test_a_file_gagos_may_not_edit_refuses_before_any_agent(project) -> None:
    asked: list = []

    def agent(model, **kw):
        asked.append(model)
        raise AssertionError("no agent may be asked")

    work = _work(project, ["frontend/src/elsewhere/Nope.jsx"], agent)
    with pytest.raises(WriterRefused, match="not a file GAGOS may edit"):
        work.write(_contract())
    assert asked == []


def test_the_agent_is_launched_sealed_to_its_tools(tmp_path, monkeypatch) -> None:
    observed: list = []
    monkeypatch.setattr(plan_cli.model_calls, "observe", lambda *a: observed.append(a))
    calls: list = []

    def run(argv, **kw):
        calls.append((argv, kw))
        return SimpleNamespace(
            returncode=0, stdout=json.dumps({"result": "done"}), stderr=""
        )

    key = "AKIAIOSFODNN7EXAMPLE"
    client = plan_cli.PlanAgentClient(
        "claude-sonnet-5-5",
        workdir=tmp_path,
        mcp_config=tmp_path / "mcp.json",
        run=run,
        claude="claude",
    )
    assert client.complete(f"change it; the key is {key}", system="rules") == "done"
    ((argv, kw),) = calls
    assert argv[1 : 1 + len(plan_cli.CLAUDE_AGENT)] == list(plan_cli.CLAUDE_AGENT)
    assert "Read,Grep,Glob,Edit,Write" in argv
    assert argv[argv.index("--allowedTools") + 1] == plan_cli.AGENT_RUN_TESTS
    assert argv[argv.index("--mcp-config") + 1] == str(tmp_path / "mcp.json")
    assert "--strict-mcp-config" in argv and "Bash" not in " ".join(argv)
    assert kw["cwd"] == str(tmp_path)
    assert key not in kw["input"], "the prompt passes the privacy filter"
    assert observed == [("plan", "claude-sonnet-5-5", "agent")]


def test_only_the_plan_client_launches_claude_code_as_an_agent() -> None:
    """One derivation: the workshop never spells the agent's flags itself."""
    source = Path(tool.__file__).read_text(encoding="utf-8")
    assert "--permission-mode" not in source and "acceptEdits" not in source
    assert "PlanAgentClient" in source


def test_an_agent_keeps_each_files_line_endings(project) -> None:
    """Its file tools may write the platform's endings: each file keeps its
    base's, and a file rewritten only in its endings did not change."""
    root, _head, led = project

    def agent(model, *, workdir, mcp_config):
        def complete(prompt, system, request_id):
            (Path(workdir) / REL).write_bytes(AFTER.replace("\n", "\r\n").encode())
            return "done"

        return complete

    work = _work(project, [REL], agent)
    assert work.write(_contract()) == {REL: AFTER}

    def endings_only(model, *, workdir, mcp_config):
        def complete(prompt, system, request_id):
            (Path(workdir) / REL).write_bytes(BEFORE.replace("\n", "\r\n").encode())
            return "done"

        return complete

    again = _work(project, [REL], endings_only)
    with pytest.raises(WriterRefused, match="changed nothing"):
        again.write(_contract())


def test_each_colony_part_is_its_own_agent(project, monkeypatch) -> None:
    from aios.agents import swarm

    monkeypatch.setattr(tool, "colony_on", lambda: True)
    parts = [
        swarm.ColonyPart((REL,), "make the panel two"),
        swarm.ColonyPart((NEW,), "add Fresh.jsx exporting fresh"),
    ]

    def colony(goal, files, *, decompose, write_part, **kw):
        for part in parts:
            write_part(part)
        return SimpleNamespace(parts=parts, scout="fresh", pattern_id=None)

    monkeypatch.setattr(swarm, "run_writer_colony", colony)
    prompts: list = []

    def agent(model, *, workdir, mcp_config):
        def complete(prompt, system, request_id):
            prompts.append(prompt)
            rel = REL if "make the panel two" in prompt else NEW
            (Path(workdir) / rel).write_text(AFTER, encoding="utf-8")
            return "done"

        return complete

    work = _work(project, [REL, NEW], agent)
    edits = work.write(_contract())
    assert {k: v.replace("\r\n", "\n") for k, v in edits.items()} == {
        REL: AFTER,
        NEW: AFTER,
    }
    assert len(prompts) == 2
    assert (
        "make the panel two" in prompts[0]
        and NEW
        not in prompts[0].split("You may change ONLY these files", 1)[1].splitlines()[0]
    )
