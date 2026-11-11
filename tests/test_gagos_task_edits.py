"""A task's writer answers with edits, not whole files (2026-11-11).

So a task reaches files over the whole-file bound (the body's largest files are
over 100,000 characters), and nothing the edits do not name can change. An
answer with no edit is still read as a whole file, as before."""

from __future__ import annotations

import pytest

from aios.maintenance import daily_work as dw
from tests.test_gagos_daily import AFTER, BEFORE, REL
from tests.test_gagos_workforce import _batch
from tools import gagos_daily as tool

WORDS = "Remove the unused local."


def _edit(search: str, replace: str) -> str:
    return f"<<<<<<< SEARCH\n{search}=======\n{replace}>>>>>>> REPLACE\n"


def test_edits_apply_in_order_to_the_text_the_writer_saw() -> None:
    original = "a = 1\nb = 2\nc = 3\n"
    raw = (
        _edit("b = 2\n", "b = 20\n")
        + "\n"
        + _edit("b = 20\nc = 3\n", "b = 21\nc = 3\n")
    )
    assert dw.parse_edits(raw, original) == "a = 1\nb = 21\nc = 3\n"


def test_the_originals_line_endings_are_kept() -> None:
    original = "a = 1\r\nb = 2\r\n"
    assert dw.parse_edits(_edit("b = 2\n", "b = 3\n"), original) == "a = 1\r\nb = 3\r\n"


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        ("Sure, here is the change.", "no edit"),
        (_edit("absent\n", "x\n"), "is not in the file"),
        (_edit("x = 1\n", "x = 2\n"), "matches 2 places"),
        ("<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n", "not complete"),
        (_edit("", "y\n"), "empty SEARCH in a file that has text"),
    ],
)
def test_an_edit_that_does_not_match_exactly_one_place_is_refused(raw, why) -> None:
    with pytest.raises(dw.ProposalRefused, match=why):
        dw.parse_edits(raw, "x = 1\nx = 1\n" if "2 places" in why else "x = 1\n")


def test_an_empty_search_writes_an_empty_file_whole() -> None:
    assert dw.parse_edits(_edit("", "new\n"), "") == "new\n"


def test_edits_over_several_files_follow_their_labels() -> None:
    raw = (
        "File 2: b.ts\n"
        + _edit("two\n", "TWO\n")
        + "File 1: a.ts\n"
        + _edit("one\n", "ONE\n")
    )
    assert dw.parse_task_edits(raw, ["one\n", "two\n", "three\n"]) == {
        0: "ONE\n",
        1: "TWO\n",
    }


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        (
            _edit("one\n", "1\n") + "File 1: a.ts\n" + _edit("one\n", "1\n"),
            "no `File N` label",
        ),
        ("File 1: a.ts\nnothing here\n", "labelled but has no edit"),
        ("File 3: c.ts\n" + _edit("one\n", "1\n"), "the task has 2 file"),
        (
            "File 1: a.ts\n"
            + _edit("one\n", "1\n")
            + "File 1: a.ts\n"
            + _edit("1\n", "2\n"),
            "given twice",
        ),
    ],
)
def test_labelled_edits_are_refused_when_they_do_not_add_up(raw, why) -> None:
    with pytest.raises(dw.ProposalRefused, match=why):
        dw.parse_task_edits(raw, ["one\n", "two\n"])


def test_a_task_over_a_file_beyond_the_whole_file_bound_is_done_with_edits(
    tmp_path, monkeypatch
) -> None:
    led, asked, args, _ids = _batch(tmp_path, monkeypatch)
    # The file is "too long" for a whole-file answer, not for a task's edits.
    monkeypatch.setattr(tool, "MAX_FILE_CHARS", 10)
    removed = "  const unused = 1;\n"
    assert removed in BEFORE and BEFORE.replace(removed, "") == AFTER

    def editor(model, region):
        def complete(prompt, system, request_id):
            asked.append(model)
            assert "<<<<<<< SEARCH" in system
            return _edit(removed, "")

        return complete

    monkeypatch.setattr(tool, "governed_completer", editor)
    tid = led.add_task(REL, WORDS, said_by="operator")
    args.rules = ["none-such"]
    assert tool.cmd_propose(args) == 0
    assert led.task(tid)["status"] == "taken" and len(asked) == 1
    [proposal] = led.proposals()
    assert proposal["new_text"] == AFTER and proposal["status"] == "proposed"
