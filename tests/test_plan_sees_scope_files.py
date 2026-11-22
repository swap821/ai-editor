"""The operator's plans see the files GAGOS's tools read from its scope
(his decision, 2026-11-22).

Live, that day: organ 44's cohort on plan.claude-sonnet-5-5 asked the counter
to edit training_ground/test_sorted_insert.py. Every code file its tools read
reached the plan as ``[FILE CONTENT REDACTED]`` (the privacy audit counted it
as ``redacted_tool_files``), and Sonnet answered that it would be guessing at
the edit. The counter keeps the full filter for his words; only a
``read_file`` result from inside the scope roots, on his plans' route, keeps
its content. Credentials, high-entropy runs and local paths stay masked, the
label never leaves, and every other route redacts as before.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aios.agents import tool_agent
from aios.core import privacy_filter as pf
from aios.core.plan_cli import PlanCliClient
from aios.core.privacy_filter import PrivacyFilter

_GH_TOKEN = "ghp_" + "a" * 36
_CODE = "\n".join(
    [
        "import bisect",
        "",
        "def test_long_list():",
        "    lst = list(range(0, 2000, 2))",
        f"    token = '{_GH_TOKEN}'",
        "    open('/home/kumar/secret/config.yaml')",
        "    assert len(lst) == 1000",
    ]
)


def _tool(content: str, label: str | None) -> dict:
    msg = {"role": "tool", "content": content}
    if label:
        msg["scope_file"] = label
    return msg


def test_his_plans_see_a_scope_file_with_keys_and_paths_masked() -> None:
    safe, audit = PrivacyFilter(scope_files_shown=True).filter(
        [_tool(_CODE, "training_ground/test_sorted_insert.py")]
    )
    content = safe[0]["content"]
    assert "def test_long_list():" in content
    assert "list(range(0, 2000, 2))" in content
    assert "FILE CONTENT REDACTED" not in content
    assert _GH_TOKEN not in content
    assert "/home/kumar/secret/config.yaml" not in content
    assert audit["redacted_tool_files"] == 0
    assert safe[0] == {"role": "tool", "content": content}  # the label never leaves


@pytest.mark.parametrize(
    "shown,label",
    [
        (False, "training_ground/test_sorted_insert.py"),  # every other route
        (True, None),  # an unlabelled tool result on his plans' route
    ],
)
def test_otherwise_a_code_file_is_still_redacted_whole(shown, label) -> None:
    safe, audit = PrivacyFilter(scope_files_shown=shown).filter([_tool(_CODE, label)])
    assert "FILE CONTENT REDACTED" in safe[0]["content"]
    assert "def test_long_list" not in safe[0]["content"]
    assert audit["redacted_tool_files"] == 1
    assert "scope_file" not in safe[0]


def test_a_scope_file_arrives_whole_not_cut_to_the_blob_limit() -> None:
    """``read_file`` already bounds a file (20,000 characters). The filter's
    500-character blob cut would leave a plan the first 8 lines."""
    body = "def f():\n" + "".join(f"    x{i} = {i}\n" for i in range(400))
    assert len(body) > pf._LARGE_BLOB_CHAR_LIMIT
    safe, _ = PrivacyFilter(scope_files_shown=True).filter(
        [_tool(body, "training_ground/big.py")]
    )
    assert safe[0]["content"] == body


def test_only_his_plan_client_turns_it_on() -> None:
    """One switch, one caller: no other client in aios/ passes
    ``scope_files_shown=True`` (Bedrock, Gemini, OpenAI, Anthropic and the
    rest keep the whole-file redaction)."""
    root = Path(__file__).resolve().parents[1] / "aios"
    callers = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "scope_files_shown":
                if isinstance(node.value, ast.Constant) and node.value.value is True:
                    callers.add(path.relative_to(root.parent).as_posix())
    assert callers == {"aios/core/plan_cli.py"}
    client = PlanCliClient(claude_models=(), codex_models=(), claude="", codex="")
    assert client._privacy_filter.scope_files_shown is True


@pytest.fixture
def scope(tmp_path, monkeypatch):
    """A project with one scope root (training_ground) and a file beside it
    that the read root reaches but the scope does not."""
    (tmp_path / "training_ground").mkdir()
    (tmp_path / "training_ground" / "t.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "aios").mkdir()
    (tmp_path / "aios" / "core.py").write_text("y = 2\n", encoding="utf-8")
    monkeypatch.setattr(
        tool_agent.config, "SCOPE_ROOTS", (tmp_path / "training_ground",)
    )
    return tmp_path


def test_a_read_inside_the_scope_roots_is_labelled(scope) -> None:
    label = tool_agent._scope_file(
        "read_file", "ok", {"filepath": "training_ground/t.py"}, scope
    )
    assert label == "training_ground/t.py"


@pytest.mark.parametrize(
    "name,status,filepath",
    [
        ("read_file", "ok", "aios/core.py"),  # under the read root, outside the scope
        ("read_file", "ok", "training_ground/../aios/core.py"),  # traversal out
        ("read_file", "blocked", "training_ground/t.py"),  # a refused read
        ("read_directory", "ok", "training_ground"),  # not a file's content
        ("verify", "ok", "training_ground/t.py"),
    ],
)
def test_nothing_else_is_labelled(scope, name, status, filepath) -> None:
    assert tool_agent._scope_file(name, status, {"filepath": filepath}, scope) is None
