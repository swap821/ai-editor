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
from aios.security import scope_lock
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
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([tmp_path / "training_ground"])
    try:
        yield tmp_path
    finally:
        scope_lock.set_scope_roots(list(original))


@pytest.mark.parametrize(
    "name,args",
    [
        ("read_file", {"filepath": "training_ground/t.py"}),
        ("read_directory", {"path": "training_ground"}),
        # A write's result is its diff: the plan saw [FILE CONTENT REDACTED]
        # for its own write and could not tell whether it landed (2026-11-22).
        ("create_file", {"filepath": "training_ground/t.py"}),
        ("edit_file", {"filepath": "training_ground/t.py"}),
    ],
)
def test_a_file_tool_result_inside_the_scope_roots_is_labelled(
    scope, name, args
) -> None:
    label = tool_agent._scope_file(name, "ok", args, scope)
    assert label == next(iter(args.values()))


@pytest.mark.parametrize(
    "name,status,filepath",
    [
        ("read_file", "ok", "aios/core.py"),  # under the read root, outside the scope
        ("read_file", "ok", "training_ground/../aios/core.py"),  # traversal out
        ("read_file", "blocked", "training_ground/t.py"),  # a refused read
        ("read_directory", "ok", "."),  # the read root itself, wider than the scope
        ("create_file", "approval", "training_ground/t.py"),  # not written yet
        ("verify", "ok", "training_ground/t.py"),
    ],
)
def test_nothing_else_is_labelled(scope, name, status, filepath) -> None:
    args = {"filepath": filepath, "path": filepath}
    assert tool_agent._scope_file(name, status, args, scope) is None


# --------------------------------------------------------------------------- #
# Test reports (his decision, 2026-11-23)
# --------------------------------------------------------------------------- #
# Organ 44's cohort, 2026-11-23, data-pipeline step 2: the plan route turned
# this report into [FILE CONTENT REDACTED] whole, and the model re-ran its
# tests nine times without seeing the ImportError it had to fix.
_FAILING_REPORT = "\n".join(
    [
        "[VERIFY FAIL] 0 passed, 1 failed (exit 2) (strength=NONE)",
        "==================================== ERRORS ====================================",
        "______________ ERROR collecting training_ground/test_pipeline.py _______________",
        "ImportError while importing test module '/workspace/training_ground/test_pipeline.py'.",
        "Traceback:",
        "/usr/local/lib/python3.12/importlib/__init__.py:90: in import_module",
        "    return _bootstrap._gcd_import(name[level:], package, level)",
        "training_ground/test_pipeline.py:8: in <module>",
        "    from pipeline import Pipeline, PipelineError, filter_nulls  # noqa: E402",
        "E   ImportError: cannot import name 'PipelineError' from 'pipeline' (/workspace/training_ground/pipeline.py)",
        "ERROR training_ground/test_pipeline.py",
        "1 error in 0.40s",
    ]
)


def test_his_plans_see_a_failing_scope_test_report() -> None:
    safe, audit = PrivacyFilter(scope_files_shown=True).filter(
        [_tool(_FAILING_REPORT, "training_ground/test_pipeline.py")]
    )
    content = safe[0]["content"]
    assert "ImportError: cannot import name 'PipelineError'" in content
    assert "from pipeline import Pipeline, PipelineError, filter_nulls" in content
    assert "FILE CONTENT REDACTED" not in content
    assert "/workspace/training_ground/pipeline.py" not in content  # paths masked
    assert audit["redacted_tool_files"] == 0
    assert "scope_file" not in safe[0]


def test_an_unlabelled_test_report_is_still_redacted_whole() -> None:
    safe, audit = PrivacyFilter(scope_files_shown=True).filter(
        [_tool(_FAILING_REPORT, None)]
    )
    assert "FILE CONTENT REDACTED" in safe[0]["content"]
    assert "PipelineError" not in safe[0]["content"]
    assert audit["redacted_tool_files"] == 1


@pytest.mark.parametrize(
    "command,label",
    [
        ("pytest training_ground/t.py", "training_ground/t.py"),
        (
            tool_agent.build_auto_verify_command("training_ground/t.py"),
            "training_ground/t.py",
        ),
        (
            "python3 -m pytest -v training_ground/t.py::test_x",
            "training_ground/t.py",
        ),
        (
            "pytest -q --tb=short -k 'long and not slow' training_ground",
            "training_ground",
        ),
        ("pytest --collect-only -q training_ground/t.py", "training_ground/t.py"),
    ],
)
def test_a_pytest_run_inside_the_scope_roots_is_labelled(scope, command, label) -> None:
    args = {"command": command}
    assert tool_agent._scope_file("verify", "ok", args, scope) == label


@pytest.mark.parametrize(
    "command",
    [
        "pytest",  # collects from the whole root
        "pytest -q",
        "pytest aios/core.py",  # under the read root, outside the scope
        "pytest training_ground/../aios/core.py",  # traversal out
        "pytest training_ground/missing.py",
        "pytest training_ground/t.py aios/core.py",  # one path outside
        "pytest training_ground/t.py; cat aios/core.py",
        "pytest training_ground/t.py | tee out.txt",
        "pytest training_ground/t.py > out.txt",
        "pytest training_ground/t.py $(cat aios/core.py)",
        "pytest training_ground/t.py `cat aios/core.py`",
        "pytest training_ground/t.py && cat aios/core.py",
        "pytest -p evil training_ground/t.py",  # a plugin from anywhere
        "pytest -c aios/x.ini training_ground/t.py",
        "pytest --rootdir=aios training_ground/t.py",
        "pytest -o pythonpath=aios training_ground/t.py",
        "pytest -o=pythonpath=aios training_ground/t.py",
        "pytest training_ground/t.py -k",  # an option missing its value
        "python -c 'import os' training_ground/t.py",
        "cat training_ground/t.py",
        "pytest 'training_ground/t.py",  # unbalanced quote
    ],
)
def test_no_other_command_is_labelled(scope, command) -> None:
    assert tool_agent._scope_file("verify", "ok", {"command": command}, scope) is None


def test_a_verify_that_did_not_run_is_not_labelled(scope) -> None:
    args = {"command": "pytest training_ground/t.py"}
    for status in ("blocked", "approval"):
        assert tool_agent._scope_file("verify", status, args, scope) is None
