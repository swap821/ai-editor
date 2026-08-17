"""A no-op write must not be a dead end.

The defect
----------
`create_file` answers a re-write of an already-correct file with

    <path> already exists with exactly the requested content; nothing to write.

True, and nowhere to go. Traced on organ 44's `error-handling` mission, the
model wrote `safe_json.py`, was told `[VERIFY SKIPPED] no sibling test`, and then
re-issued `create_file` for `safe_json.py` **five more times** — burning every
remaining iteration on a file that was already correct, never creating the test,
and ending the turn `unverified`.

Two existing controls both miss it:

* the loop detector keys on (tool, arguments) and the `content` argument varies
  between attempts, so the calls are not "identical";
* a `noop` is not progress either, so it does not clear the detector's window.

This is the same shape #215 fixed for the no-sibling-test note: the loop knows
what remains outstanding and does not say it, so the model repeats the work it
just finished. The reply now names the one thing left.

What this file pins
-------------------
That the hint appears when a Python file has no sibling test, that it stays
silent when there is nothing useful to add, and that it never breaks a write.
"""

from __future__ import annotations

from pathlib import Path

from aios.agents.tool_handlers import _next_step_after_noop


def test_an_unverifiable_file_is_told_what_is_missing(tmp_path: Path) -> None:
    """The traced case: implementation written, no test, nothing to write."""
    impl = tmp_path / "safe_json.py"
    impl.write_text("x = 1", encoding="utf-8")

    hint = _next_step_after_noop(impl)

    assert "test_safe_json.py" in hint, (
        f"the hint does not name the file to create: {hint!r}"
    )
    assert "UNVERIFIED" in hint
    assert "Do NOT re-write" in hint, (
        "the hint must say not to re-write the implementation -- re-writing it "
        "five times is the actual observed failure"
    )


def test_nothing_is_said_once_the_sibling_test_exists(tmp_path: Path) -> None:
    """Verification will run and speak for itself; a hint would be noise."""
    impl = tmp_path / "pipeline.py"
    impl.write_text("x = 1", encoding="utf-8")
    (tmp_path / "test_pipeline.py").write_text("x = 1", encoding="utf-8")

    assert _next_step_after_noop(impl) == ""


def test_a_test_file_is_not_told_to_test_itself(tmp_path: Path) -> None:
    """Without this, a no-op on test_x.py would ask for test_test_x.py."""
    test = tmp_path / "test_pipeline.py"
    test.write_text("x = 1", encoding="utf-8")

    assert _next_step_after_noop(test) == ""


def test_non_python_files_get_no_hint(tmp_path: Path) -> None:
    """The sibling-test rule is auto-verify's rule, and it is Python-only."""
    doc = tmp_path / "notes.md"
    doc.write_text("hello", encoding="utf-8")

    assert _next_step_after_noop(doc) == ""


def test_a_hint_can_never_break_a_write(tmp_path: Path) -> None:
    """Fail-safe: this runs inside the create/edit path.

    A hint that raised would turn a successful no-op into an error, which is
    strictly worse than the dead end it replaces.
    """
    missing = tmp_path / "nope" / "deep" / "thing.py"
    assert _next_step_after_noop(missing) != "  "  # does not raise
    assert isinstance(_next_step_after_noop(missing), str)


def test_both_noop_paths_carry_the_hint() -> None:
    """create_file AND edit_file both answered with a dead end.

    Pinned together because fixing only one leaves the same trap reachable by
    the other route -- the model chooses which tool to retry with.
    """
    import inspect

    from aios.agents import tool_handlers

    create_src = inspect.getsource(tool_handlers.create_file)
    edit_src = inspect.getsource(tool_handlers.edit_file)
    assert "_next_step_after_noop" in create_src, (
        "create_file's no-op is still a dead end"
    )
    assert "_next_step_after_noop" in edit_src, "edit_file's no-op is still a dead end"
