"""Tasks the operator writes, in GAGOS's workshop (2026-11-03). Pinned here,
without a model or a network:

* a batch takes the operator's open tasks before any lint finding, records
  each under the task rule and marks the task taken by that proposal;
* a task on a file GAGOS may not edit is refused with a reason and no model is
  asked; a failed model call leaves the task open for the next hour;
* his words are scrubbed before any model reads them;
* a task's change passes the unattended checks when it parses and adds nothing
  to the lint, with no reach check; it is refused if it adds a message or a
  disable comment, or changes nothing;
* the reviewer is shown the operator's task, not a rule and its warnings; the
  commit says it was his task; the report counts the tasks;
* the command line adds, lists and cancels.
"""

from __future__ import annotations

import json

from aios.maintenance import daily_work as dw
from tests.test_gagos_daily import AFTER, BEFORE, REL, RULE, _result, _warn
from tests.test_gagos_workforce import OTHER, _batch
from tools import gagos_daily as tool

WORDS = "Rename the unused local to `spare`, and say why in a comment."


def _reply(monkeypatch, prompts):
    """Every writer answers with AFTER and keeps the prompt it was given."""

    def completer(model, region):
        def complete(prompt, system, request_id):
            prompts.append((model, prompt, system))
            return f"```jsx\n{AFTER}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)


def test_a_batch_takes_the_tasks_before_the_lint_findings(
    tmp_path, monkeypatch
) -> None:
    led, asked, args, _ids = _batch(tmp_path, monkeypatch)
    prompts: list = []
    _reply(monkeypatch, prompts)
    tid = led.add_task(REL, WORDS, said_by="operator")
    args.budget = 1
    assert tool.cmd_propose(args) == 0
    (only,) = led.proposals()
    assert (only["rule"], only["rel"], only["status"]) == (
        dw.TASK_RULE,
        REL,
        "proposed",
    )
    task = led.task(tid)
    assert (task["status"], task["proposal_id"]) == ("taken", only["proposal_id"])
    ((_model, prompt, system),) = prompts
    assert WORDS in prompt and "operator has asked" in system
    assert "Warnings to fix" not in prompt, "a task is not a lint fix"


def test_the_oldest_task_is_first_and_a_file_is_held_by_one_task_a_batch(
    tmp_path, monkeypatch
) -> None:
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)
    _reply(monkeypatch, [])
    first = led.add_task(REL, "first words", said_by="operator")
    second = led.add_task(REL, "second words", said_by="operator")
    args.budget = 5
    tool.cmd_propose(args)
    assert led.task(first)["status"] == "taken"
    assert led.task(second)["status"] == "open", "its file is held; next hour"


def test_a_task_on_a_file_gagos_may_not_edit_is_refused_and_no_model_is_asked(
    tmp_path, monkeypatch, capsys
) -> None:
    led, asked, args, _ids = _batch(tmp_path, monkeypatch)
    missing = led.add_task("frontend/src/nowhere.jsx", WORDS, said_by="operator")
    docs = led.add_task("README.md", WORDS, said_by="operator")
    args.rules = ["none-such"]
    assert tool.cmd_propose(args) == 0
    for tid in (missing, docs):
        task = led.task(tid)
        assert task["status"] == "refused" and "may edit" in task["reason"]
    assert asked == [] and led.proposals() == []
    assert "refused" in capsys.readouterr().out


def test_a_python_task_on_the_frozen_core_is_refused(tmp_path, monkeypatch) -> None:
    led, asked, args, _ids = _batch(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "editable_python_files", lambda root: ["aios/x.py"])
    frozen = led.add_task("aios/core/executor.py", WORDS, said_by="operator")
    args.rules = ["none-such"]
    tool.cmd_propose(args)
    assert led.task(frozen)["status"] == "refused" and asked == []


def test_a_file_over_the_bound_is_refused(tmp_path, monkeypatch) -> None:
    led, asked, args, _ids = _batch(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "MAX_FILE_CHARS", 10)
    tid = led.add_task(REL, WORDS, said_by="operator")
    args.rules = ["none-such"]
    tool.cmd_propose(args)
    assert led.task(tid)["status"] == "refused" and "bound" in led.task(tid)["reason"]
    assert asked == []


def test_a_failed_model_call_leaves_the_task_open(tmp_path, monkeypatch) -> None:
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)

    def refusing(model, region):
        def complete(prompt, system, request_id):
            raise RuntimeError("AWS refused the account")

        return complete

    monkeypatch.setattr(tool, "governed_completer", refusing)
    tid = led.add_task(REL, WORDS, said_by="operator")
    args.rules = ["none-such"]
    tool.cmd_propose(args)
    task = led.task(tid)
    assert (task["status"], task["proposal_id"]) == ("open", None)
    (failed,) = led.proposals()
    assert failed["refusal"].startswith("model call failed")


def test_a_proposal_refused_by_the_checks_still_takes_the_task(
    tmp_path, monkeypatch
) -> None:
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)
    monkeypatch.setattr(
        tool,
        "check_texts",
        lambda r, texts, **kw: {k: _result(_warn(RULE)) for k in texts},
    )

    def completer(model, region):
        return lambda prompt, system, request_id: f"```jsx\n{BEFORE}```"

    monkeypatch.setattr(tool, "governed_completer", completer)
    tid = led.add_task(REL, WORDS, said_by="operator")
    args.rules = ["none-such"]
    tool.cmd_propose(args)
    (p,) = led.proposals()
    assert p["status"] == "refused" and "changes nothing" in p["refusal"]
    assert led.task(tid)["proposal_id"] == p["proposal_id"]


def test_his_words_are_scrubbed_before_a_model_reads_them(
    tmp_path, monkeypatch
) -> None:
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)
    prompts: list = []
    _reply(monkeypatch, prompts)
    secret = "AKIAIOSFODNN7EXAMPLE"
    led.add_task(REL, f"Use the key {secret} when it connects.", said_by="operator")
    args.rules = ["none-such"]
    tool.cmd_propose(args)
    assert prompts, "the task reached a model, scrubbed"
    for _model, prompt, _system in prompts:
        assert secret not in prompt


# ------------------------------------------------------------- the verdict


def test_a_clean_change_far_from_any_warning_passes() -> None:
    far = BEFORE + "\n" * 40 + "const added = 1;\n"
    before = _result(_warn(RULE), text=BEFORE)
    after = _result(_warn(RULE), text=far)
    verdict = dw.task_verdict(REL, BEFORE, far, before, after)
    assert verdict.passed and verdict.changed_lines > 0, "no reach check"


def test_a_change_that_adds_a_warning_is_refused() -> None:
    new = BEFORE + "const spare = 2;\n"
    before = _result(_warn(RULE), text=BEFORE)
    after = _result(_warn(RULE), _warn(RULE, line=6), text=new)
    verdict = dw.task_verdict(REL, BEFORE, new, before, after)
    assert not verdict.passed and "adds ESLint messages" in verdict.reason


def test_a_change_that_does_not_parse_is_refused() -> None:
    new = BEFORE + "const = ;\n"
    after = _result(parse=("Unexpected token",), text=new)
    verdict = dw.task_verdict(REL, BEFORE, new, _result(text=BEFORE), after)
    assert not verdict.passed and "does not parse" in verdict.reason


def test_a_change_that_adds_a_disable_comment_is_refused() -> None:
    new = BEFORE.replace(
        "  const unused", "  // eslint-disable-next-line no-unused-vars\n  const unused"
    )
    before = _result(_warn(RULE), text=BEFORE)
    after = _result(text=new, hidden=(_warn(RULE, line=4),))
    verdict = dw.task_verdict(REL, BEFORE, new, before, after)
    assert not verdict.passed and "disable comment" in verdict.reason


def test_a_change_that_changes_nothing_is_refused() -> None:
    result = _result(_warn(RULE), text=BEFORE)
    verdict = dw.task_verdict(REL, BEFORE, BEFORE, result, result)
    assert not verdict.passed and "changes nothing" in verdict.reason


# ------------------------------------------------- review, commit and report


def _taken(tmp_path, monkeypatch, text=WORDS):
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    tid = led.add_task(REL, text, said_by="operator")
    finding = dw.Finding(REL, dw.TASK_RULE, ())
    pid = led.record_proposal(
        finding,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="writer-a",
        new_text=AFTER,
        verdict=dw.StaticVerdict(True, "ok", 2),
    )
    assert led.take_task(tid, pid)
    return led, tid, pid, finding


def test_the_reviewer_is_shown_the_operators_task_not_a_rule(
    tmp_path, monkeypatch
) -> None:
    led, _tid, pid, finding = _taken(
        tmp_path, monkeypatch, "Drop the unused local. Key AKIAIOSFODNN7EXAMPLE."
    )
    (p,) = [x for x in led.proposals() if x["proposal_id"] == pid]
    prompt = tool.review_evidence(p, finding)
    assert "Drop the unused local" in prompt
    assert "does what the operator's task asks" in prompt
    assert "Warnings it should fix" not in prompt and "Rule:" not in prompt
    assert "AKIAIOSFODNN7EXAMPLE" not in prompt, "his words are scrubbed"
    assert "-  const unused = 1;" in prompt, "and the diff is shown"


def test_the_commit_says_it_was_the_operators_task(tmp_path, monkeypatch) -> None:
    led, tid, pid, _finding = _taken(tmp_path, monkeypatch, WORDS + "\nMore detail.")
    (p,) = [x for x in led.proposals() if x["proposal_id"] == pid]
    reviews = {
        "claude": {"model": "claude-opus-5-5", "verdict": "accept", "reason": "fine"}
    }
    message = tool.commit_message(p, reviews, task=led.task_of_proposal(pid))
    assert message.startswith("GAGOS: the operator's task in " + REL)
    assert tid in message and WORDS in message and "More detail" not in message
    assert "Proposed-by: GAGOS" in message and "Co-authored-by:" in message
    assert "Reviewed-by:" in message


def test_the_report_counts_the_tasks(tmp_path, monkeypatch) -> None:
    led, tid, pid, _finding = _taken(tmp_path, monkeypatch)
    waiting = led.add_task(OTHER, "later", said_by="operator")
    led.cancel_task(led.add_task(OTHER, "never mind", said_by="operator"))
    text = tool.report(led)
    assert "**Tasks**" in text and "open 1, taken 1, refused 0, cancelled 1" in text
    assert f"`{waiting}` in `{OTHER}`: open" in text
    assert f"`{tid}` in `{REL}`: taken, proposal `{pid}`" in text
    assert WORDS not in text, "never his words"


# ------------------------------------------------------------- the command


def test_the_command_line_adds_lists_and_cancels(tmp_path, monkeypatch, capsys) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    assert tool.main(["task", "add", "--file", REL, WORDS]) == 0
    (task,) = led.tasks()
    assert capsys.readouterr().out.strip() == task["task_id"]
    assert task["said_by"] == "the operator (command line)"

    assert tool.main(["task", "list"]) == 0
    line = capsys.readouterr().out.strip()
    assert line.startswith(f"{task['task_id']} open {REL}") and line.endswith(WORDS)

    assert tool.main(["task", "add", "--file", "/etc/passwd", WORDS]) == 2
    assert capsys.readouterr().out.startswith("refused: ")

    assert tool.main(["task", "cancel", task["task_id"]]) == 0
    assert led.task(task["task_id"])["status"] == "cancelled"
    assert tool.main(["task", "cancel", task["task_id"]]) == 2
    assert tool.main(["task", "cancel", "gt-nope"]) == 2


def test_the_list_shows_a_tasks_proposal_and_its_pr(
    tmp_path, monkeypatch, capsys
) -> None:
    led, tid, pid, _finding = _taken(tmp_path, monkeypatch)
    assert tool.main(["task", "list"]) == 0
    assert f"{tid} taken -> proposal {pid} proposed {REL}:" in capsys.readouterr().out
    assert json.dumps(led.task_progress())  # the one read the face and counter share
