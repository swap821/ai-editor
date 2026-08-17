"""`overwrite_file`: the missing route on an edit step, gated as an edit.

Why it exists
-------------
On an "Edit X to add Y" step the model had no workable route:

    create_file       -> blocked, "already exists; use edit_file"
    edit_file         -> needs an EXACT byte match for old_string
    execute_terminal  -> scope-blocked

and it demonstrably cannot produce that match. Captured from a real run, the
model's `old_string` for `pipeline.py` was

    class Pipeline:
        def __init__(self, steps: List[Callable[[Any], Any]]):

while the file on disk had `def __init__(self):` with `self._steps`. Not
whitespace drift — no normalisation matches it. Fuzzy matching MUST NOT fix
this: it would apply an edit to code the model never read. `edit_file` refusing
is correct, so the gap is the missing route, not the matching.

Measured: 7 of 10 `unverified` failures across 20 golden missions were this.

Why it is not a new privilege
-----------------------------
An overwrite IS an edit whose `old_string` is the file's current body. `run()`
resolves it into exactly that before dispatch, so the approval pause, the
`edits` payload the operator reviews, the unified diff, the pre-write snapshot,
the audit entry, earned autonomy and the forced auto-verify are all the ones
`edit_file` already had. There is no second gated write path.

These tests lean on the refusals rather than the happy path: a whole-file write
is the most destructive shape a sandbox write can take, so what it must NOT do
matters more than what it does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aios.agents import tool_handlers
from aios.agents.tool_agent import TOOL_SPECS, ToolAgent


@pytest.fixture()
def agent(tmp_path: Path) -> ToolAgent:
    """A ToolAgent with only what the overwrite translation touches."""
    instance = ToolAgent.__new__(ToolAgent)
    instance.read_root = tmp_path
    return instance


def _scoped(monkeypatch, root: Path) -> None:
    """Treat *root* as the editable sandbox for these tests."""
    monkeypatch.setattr(
        tool_handlers.scope_lock,
        "is_path_in_scope",
        lambda p: type("S", (), {"in_scope": True, "resolved": p})(),
    )


# --------------------------------------------------------------------------- #
# It resolves into a real edit -- not a new write path.
# --------------------------------------------------------------------------- #


def test_an_overwrite_becomes_an_edit_carrying_the_real_old_string(
    agent, tmp_path, monkeypatch
) -> None:
    """The whole design: old_string is the file's CURRENT body, read server-side.

    This is what makes the approval preview honest and the replay correct -- the
    operator sees a diff against what is actually on disk, not against whatever
    the model believed was there.
    """
    _scoped(monkeypatch, tmp_path)
    target = tmp_path / "pipeline.py"
    target.write_text("class Pipeline:\n    pass\n", encoding="utf-8")

    args, refusal = agent._overwrite_as_edit(
        {"filepath": "pipeline.py", "content": "class Pipeline:\n    ok = 1\n"}
    )

    assert refusal is None
    assert args["old_string"] == "class Pipeline:\n    pass\n", (
        "old_string must be the real file body; anything else makes the diff a lie"
    )
    assert args["new_string"] == "class Pipeline:\n    ok = 1\n"
    assert args["filepath"] == "pipeline.py"


def test_the_model_never_supplies_old_string(agent, tmp_path, monkeypatch) -> None:
    """The point of the tool: the model cannot get this wrong, because it does
    not provide it. Its inability to reproduce existing bytes is the defect
    being routed around."""
    _scoped(monkeypatch, tmp_path)
    (tmp_path / "x.py").write_text("real = 1\n", encoding="utf-8")

    args, _ = agent._overwrite_as_edit(
        {"filepath": "x.py", "content": "new = 2\n", "old_string": "HALLUCINATED"}
    )
    assert args["old_string"] == "real = 1\n", (
        "a model-supplied old_string leaked into the edit"
    )


def test_dispatch_has_no_overwrite_branch() -> None:
    """Translation happens in run(); a dispatch branch would be a second path.

    Two write paths is precisely how the earlier defects in this area survived.
    """
    import inspect

    src = inspect.getsource(ToolAgent._dispatch)
    assert 'name == "overwrite_file"' not in src


# --------------------------------------------------------------------------- #
# Refusals -- the half that matters for a whole-file write.
# --------------------------------------------------------------------------- #


def test_a_missing_file_is_refused_not_created(agent, tmp_path, monkeypatch) -> None:
    """Creating one here would dodge create_file's own approval preview."""
    _scoped(monkeypatch, tmp_path)
    args, refusal = agent._overwrite_as_edit(
        {"filepath": "brand_new.py", "content": "x = 1\n"}
    )
    assert args == {}
    assert refusal is not None and "does not exist" in refusal
    assert "create_file" in refusal, "the refusal should name the right tool"
    assert not (tmp_path / "brand_new.py").exists(), "the file was created anyway"


def test_a_path_escaping_the_root_is_refused(agent, tmp_path, monkeypatch) -> None:
    _scoped(monkeypatch, tmp_path)
    args, refusal = agent._overwrite_as_edit(
        {"filepath": "../../etc/passwd", "content": "x"}
    )
    assert args == {}
    assert refusal is not None and "escapes the project root" in refusal


def test_an_out_of_scope_path_is_refused(agent, tmp_path, monkeypatch) -> None:
    """Scope confinement is not weakened by the new route."""
    target = tmp_path / "outside.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        tool_handlers.scope_lock,
        "is_path_in_scope",
        lambda p: type("S", (), {"in_scope": False, "resolved": p})(),
    )
    monkeypatch.setattr(tool_handlers.scope_lock, "get_scope_roots", lambda: [])

    args, refusal = agent._overwrite_as_edit(
        {"filepath": "outside.py", "content": "y = 2\n"}
    )
    assert args == {}
    assert refusal is not None and "outside the editable sandbox scope" in refusal


def test_identical_content_is_a_noop_that_names_the_next_step(
    agent, tmp_path, monkeypatch
) -> None:
    """Nothing to approve, so do not pause -- and do not dead-end either."""
    _scoped(monkeypatch, tmp_path)
    body = "def f():\n    return 1\n"
    (tmp_path / "impl.py").write_text(body, encoding="utf-8")

    args, refusal = agent._overwrite_as_edit({"filepath": "impl.py", "content": body})
    assert args == {}
    assert refusal is not None
    assert "nothing to write" in refusal
    assert "test_impl.py" in refusal, (
        "a no-op overwrite should name what is still outstanding, like the "
        "create/edit no-ops do"
    )


# --------------------------------------------------------------------------- #
# The tool the model actually sees.
# --------------------------------------------------------------------------- #


def test_the_spec_demands_the_complete_file(agent) -> None:
    """A partial body would silently delete code.

    The description has to say so, because the failure mode is invisible: the
    write succeeds and the deletion looks intentional.
    """
    spec = next(s for s in TOOL_SPECS if s["function"]["name"] == "overwrite_file")[
        "function"
    ]
    text = (
        spec["description"] + spec["parameters"]["properties"]["content"]["description"]
    )

    assert "COMPLETE" in text or "ENTIRE" in text
    assert "removed" in text or "read the file first" in text, (
        "the spec must warn that omitted code is lost"
    )
    assert "approval" in spec["description"], (
        "the spec must state it pauses for approval, like edit_file's does"
    )


def _unused(_: Any) -> None:  # pragma: no cover
    return None


# --------------------------------------------------------------------------- #
# The bridge: the failure that needs this tool must name it.
# --------------------------------------------------------------------------- #


def test_a_failed_snippet_match_names_overwrite_file(tmp_path, monkeypatch) -> None:
    """`old_string not found` used to leave only the option that just failed.

    It is organ 44's single most common write failure (7 of 10 `unverified`
    steps), and re-reading does not fix it -- the model re-read and reconstructed
    the file from memory again. The alternative needs no snippet match at all, so
    the error names it.
    """
    _scoped(monkeypatch, tmp_path)
    (tmp_path / "pipeline.py").write_text(
        "def __init__(self):\n    pass\n", encoding="utf-8"
    )

    out, status, _ = tool_handlers.edit_file(
        "pipeline.py",
        "def __init__(self, steps: List[Any]):",  # the real hallucinated shape
        "def __init__(self, steps):",
        read_root=tmp_path,
        approved_edits={},
        snapshot=None,
        audit=None,
    )

    assert status == "blocked"
    assert "overwrite_file" in out, (
        f"the refusal offers no route that can actually succeed: {out}"
    )
    assert "byte-for-byte" in out or "memory" in out, (
        "the refusal should say WHY it failed, not just that it did"
    )


def test_a_successful_edit_says_nothing_about_overwrite(tmp_path, monkeypatch) -> None:
    """The suggestion is for the failure path only -- not advice on every edit."""
    _scoped(monkeypatch, tmp_path)
    (tmp_path / "x.py").write_text("a = 1\n", encoding="utf-8")

    out, status, _ = tool_handlers.edit_file(
        "x.py",
        "a = 1",
        "a = 2",
        read_root=tmp_path,
        approved_edits={},
        snapshot=None,
        audit=None,
    )
    assert status == "approval"
    assert "overwrite_file" not in out
