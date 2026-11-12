"""A task's writer that makes no edit is heard (2026-11-12).

The task writer is told: "If the task cannot be done in this file alone,
reply with no edit at all." The blueprint goal PERF-04 was refused twice as
"expected exactly one fenced code block, got 0" -- the workshop read the reply
as a broken whole file -- and what the writer said was lost (it had been
shown the test file, not the store whose API the test needed). Now such a
reply is refused as "the writer made no edit", keeping its own words,
scrubbed and cut short. Pinned without a model, for a task over one file and
over several.
"""

from __future__ import annotations

from tests.test_gagos_daily import REL
from tests.test_gagos_tasks_workshop import WORDS
from tests.test_gagos_workforce import OTHER, _batch
from tools import gagos_daily as tool

PROSE = (
    "This cannot be done in this file alone: the store's exported API is not "
    "shown, so I am making no edit."
)


def _answer(monkeypatch, text):
    def completer(model, region):
        def complete(prompt, system, request_id):
            return text

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)


def _refusals(led):
    return [p["refusal"] for p in led.proposals() if p["status"] == "refused"]


def test_a_writer_that_makes_no_edit_is_heard(tmp_path, monkeypatch) -> None:
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)
    _answer(monkeypatch, PROSE)
    tid = led.add_task(REL, WORDS, said_by="operator")
    args.budget = 1
    assert tool.cmd_propose(args) == 0
    (why,) = _refusals(led)
    assert why.startswith("the writer made no edit: ")
    assert "cannot be done in this file alone" in why
    assert "fenced code block" not in why
    assert led.task(tid)["status"] == "taken"


def test_a_task_over_several_files_hears_it_too(tmp_path, monkeypatch) -> None:
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)
    _answer(monkeypatch, PROSE)
    led.add_task(REL, WORDS, said_by="operator", also=[OTHER])
    args.budget = 1
    assert tool.cmd_propose(args) == 0
    (why,) = _refusals(led)
    assert why.startswith("the writer made no edit: ")


def test_its_words_are_scrubbed_and_cut_short(tmp_path, monkeypatch) -> None:
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)
    secret = "AKIAIOSFODNN7EXAMPLE"
    _answer(monkeypatch, f"No edit; the key {secret} is needed. " + "x " * 400)
    led.add_task(REL, WORDS, said_by="operator")
    args.budget = 1
    tool.cmd_propose(args)
    (why,) = _refusals(led)
    assert secret not in why
    assert len(why) < len("the writer made no edit: ") + tool.NO_EDIT_EXCERPT + 10


def test_an_empty_answer_says_so() -> None:
    assert tool.no_edit_refusal("") == "the writer made no edit (an empty answer)"
    assert tool.no_edit_refusal("   \n ") == "the writer made no edit (an empty answer)"


def test_edits_and_whole_files_are_left_to_their_readers() -> None:
    edits = "<<<<<<< SEARCH\nconst a = 1;\n=======\nconst a = 2;\n>>>>>>> REPLACE\n"
    assert tool.no_edit_refusal(edits) is None
    assert tool.no_edit_refusal("```jsx\nconst a = 2;\n```") is None
