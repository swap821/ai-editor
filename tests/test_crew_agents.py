"""GAGOS's crew agents (2026-11-11): what each may use, and the lead's plan."""

from __future__ import annotations

import json

import pytest

from aios.maintenance import crew_agents as ca
from aios.maintenance import crew_workspace as cw
from tests.test_crew_workspace import _redact, make_project


@pytest.fixture()
def ws(tmp_path):
    root, base = make_project(tmp_path)
    return cw.build(root, base, ["frontend/"], _redact, tmp_path / "ws")


def _arg(argv, flag):
    return argv[argv.index(flag) + 1]


def test_the_lead_reads_and_never_writes_or_tests() -> None:
    argv = ca.agent_argv("m", write=False, max_turns=5, schema=ca.PLAN_SCHEMA)
    assert _arg(argv, "--tools") == "Read,Grep,Glob"
    assert "--mcp-config" not in argv and "--allowedTools" not in argv
    assert json.loads(_arg(argv, "--json-schema")) == ca.PLAN_SCHEMA


def test_a_worker_has_file_tools_and_only_gagoss_test_tool(tmp_path) -> None:
    argv = ca.agent_argv("m", write=True, max_turns=5, mcp_config=tmp_path / "m.json")
    tools = _arg(argv, "--tools").split(",")
    assert tools == ["Read", "Grep", "Glob", "Edit", "Write"]
    assert not {"Bash", "WebFetch", "WebSearch", "Task"} & set(tools), (
        "no shell, no web"
    )
    assert _arg(argv, "--allowedTools") == "mcp__gagos__run_tests"
    for flag in ("--strict-mcp-config", "--no-session-persistence"):
        assert flag in argv
    assert _arg(argv, "--permission-mode") == "acceptEdits"
    assert "Never add eslint-disable" in _arg(argv, "--append-system-prompt")


def test_a_plan_is_checked_before_any_worker_starts(ws) -> None:
    ok = {
        "summary": "two parts",
        "subtasks": [
            {"title": "a", "instructions": "do a", "files": ["frontend/src/a.ts"]},
            {"title": "b", "instructions": "do b", "files": ["frontend/src/b.test.ts"]},
        ],
    }
    summary, subs = ca.parse_plan(ok, ws, ["frontend/"])
    assert summary == "two parts" and [s.files for s in subs] == [
        ("frontend/src/a.ts",),
        ("frontend/src/b.test.ts",),
    ]


@pytest.mark.parametrize(
    ("files", "why"),
    [
        (["frontend/src/a.ts"], "in two sub-tasks"),
        (["../outside.ts"], "inside the crew's scopes"),
        (["aios/x.py"], "inside the crew's scopes"),
        (["frontend/src/logo.png"], "does not hold"),
    ],
)
def test_a_plan_that_overlaps_or_reaches_outside_is_refused(ws, files, why) -> None:
    plan = {
        "summary": "",
        "subtasks": [
            {"title": "a", "instructions": "x", "files": ["frontend/src/a.ts"]},
            {"title": "b", "instructions": "y", "files": files},
        ],
    }
    with pytest.raises(ca.PlanRefused, match=why):
        ca.parse_plan(plan, ws, ["frontend/"])


def test_too_many_sub_tasks_are_refused(ws) -> None:
    plan = {
        "summary": "",
        "subtasks": [
            {"title": f"t{i}", "instructions": "x", "files": [f"frontend/src/n{i}.ts"]}
            for i in range(ca.MAX_SUBTASKS + 1)
        ],
    }
    with pytest.raises(ca.PlanRefused, match="more than"):
        ca.parse_plan(plan, ws, ["frontend/"])


def test_each_worker_gets_its_own_copy_under_the_same_mask(ws, tmp_path) -> None:
    other = ca.clone(ws, tmp_path / "w2")
    (other.root / "frontend/src/a.ts").write_bytes(b"export const a = 2;\n")
    assert cw.changes(ws) == {} and list(cw.changes(other)) == ["frontend/src/a.ts"]
    assert other.mapping == ws.mapping


def test_a_worker_changing_files_outside_its_sub_task_is_named() -> None:
    sub = ca.Subtask("a", "x", ("frontend/src/a.ts",))
    assert ca.outside_its_files(
        {"frontend/src/a.ts": "x", "frontend/src/b.ts": None}, sub
    ) == ["frontend/src/b.ts"]


def test_the_worker_prompt_names_its_files_and_the_others() -> None:
    a = ca.Subtask("a", "do a", ("frontend/src/a.ts",))
    b = ca.Subtask("b", "do b", ("frontend/src/b.ts",))
    text = ca.worker_prompt("the goal", a, [b])
    assert "ONLY these files" in text and "frontend/src/a.ts" in text
    assert "never touch their files" in text and "frontend/src/b.ts" in text
    assert "run_tests" in text


def test_the_prompt_goes_on_stdin_and_the_rules_are_one_line(
    monkeypatch, tmp_path
) -> None:
    """On Windows ``claude`` is a .cmd launcher; cmd.exe cuts a command-line
    argument at its first line break (measured 2026-11-11: the lead saw only its
    prompt's first line). The prompt goes on stdin; the rules stay one line."""
    seen = {}

    class Done:
        returncode = 0
        stdout = json.dumps({"result": "ok", "num_turns": 2})
        stderr = ""

    def run(argv, **kw):
        seen["argv"], seen["input"] = argv, kw.get("input")
        return Done()

    monkeypatch.setattr(ca.subprocess, "run", run)
    prompt = "line one\nline two\nthe goal"
    out = ca.run_agent(ca.agent_argv("m", write=False, max_turns=3), prompt, tmp_path)
    assert out.error is None and out.result == "ok" and out.turns == 2
    assert seen["input"] == prompt and prompt not in seen["argv"]
    assert not any("\n" in a for a in seen["argv"]), "no argument may hold a line break"
    assert "\n" not in ca.RULES
