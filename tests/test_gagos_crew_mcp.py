"""GAGOS's run_tests tool for crew agents (2026-11-11): the protocol it speaks,
and that what it returns never carries what the agent's copy hid."""

from __future__ import annotations

import io
import json

from aios.maintenance import crew_workspace as cw
from aios.maintenance import sandbox_tests as st
import pytest

from tests.test_crew_workspace import SECRET, _redact, make_project
from tools import gagos_crew_mcp as mcp


@pytest.fixture()
def project(tmp_path):
    return make_project(tmp_path)


def _talk(*messages, tools=None) -> list[dict]:
    out = io.StringIO()
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    mcp.serve(stdin, out, tools or {"run_tests": lambda a: "PASSED: fine"})
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_the_protocol_handshake_and_its_one_tool() -> None:
    replies = _talk(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "run_tests", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "shell", "arguments": {}},
        },
        {"jsonrpc": "2.0", "id": 5, "method": "resources/list"},
    )
    assert [r["id"] for r in replies] == [1, 2, 3, 4, 5], "a notification gets no reply"
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert replies[0]["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert [t["name"] for t in replies[1]["result"]["tools"]] == ["run_tests"]
    assert replies[2]["result"]["content"][0]["text"] == "PASSED: fine"
    assert "unknown tool" in replies[3]["error"]["message"]
    assert replies[4]["error"]["code"] == -32601


def test_a_tool_that_fails_says_so_without_its_details() -> None:
    def boom(_args):
        raise RuntimeError(f"leaked {SECRET}")

    [reply] = _talk(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "run_tests"},
        },
        tools={"run_tests": boom},
    )
    assert reply["result"]["isError"] is True
    assert SECRET not in json.dumps(reply)


def test_run_tests_runs_the_restored_changes_and_masks_the_answer(
    project, tmp_path
) -> None:
    root, base = project
    ws = cw.build(root, base, ["frontend/"], _redact, tmp_path / "ws")
    keys = tmp_path / "ws/frontend/src/keys.ts"
    keys.write_bytes(keys.read_bytes().replace(b"b = 2", b"b = 3"))
    seen = {}

    def run(trees, *, base_commit, changes):
        seen.update(changes)
        # A verdict that quotes the real value, as a test name could.
        return st.SandboxVerdict(
            st.BROKE, f"1 test fails: expects {SECRET}", broken=("keys.test.ts::key",)
        )

    answer = mcp.run_tests_for(root, ws, redact=_redact, run=run)
    assert seen == {
        "frontend/src/keys.ts": f"export const key = '{SECRET}';\nexport const b = 3;\n"
    }
    assert answer.startswith("BROKE: 1 test fails") and "keys.test.ts::key" in answer
    assert SECRET not in answer and "GAGOSMASKQ_0000" in answer


def test_run_tests_with_nothing_changed_runs_nothing(project, tmp_path) -> None:
    root, base = project
    ws = cw.build(root, base, ["frontend/"], _redact, tmp_path / "ws")

    def never(*a, **k):
        raise AssertionError("no sandbox run for no change")

    assert mcp.run_tests_for(root, ws, redact=_redact, run=never).startswith("UNTESTED")


def test_the_state_that_restores_the_copy_lives_outside_it(project, tmp_path) -> None:
    root, base = project
    ws = cw.build(root, base, ["frontend/"], _redact, tmp_path / "ws")
    state = tmp_path / "state.json"
    mcp.save_state(ws, state)
    assert not state.is_relative_to(ws.root)
    back = mcp.load_state(state)
    assert (
        back.mapping == ws.mapping
        and back.shown == ws.shown
        and back.base_commit == base
    )
    assert SECRET not in "".join(p.read_text() for p in ws.root.rglob("*.ts"))
