"""A task the operator writes over several files (2026-11-03, the operator: "plz
honestly do all than we will be ready for D14"), in GAGOS's workshop. Pinned
here, without a model or a network:

* every file of a task must be one GAGOS may edit, readable and within the
  bounds, the files together within one answer; otherwise the whole task is
  refused before any model is asked; a file another change holds makes it wait;
* the writer gets one prompt with every file under its own label and mask, and
  answers with a label and one fenced block per file it changes; the parser
  reads that answer and refuses a block with no label, a label with no block,
  a file that is not the task's, a file given twice;
* a changed file is one proposal, all grouped under the task's id, and the task
  is taken by the first; all or nothing: one refused file refuses every file;
* the tests run once for the group, all its changes in place, and the verdict is
  recorded on every file; one review is of the whole group, recorded on every
  file, never of a member alone;
* delivery needs every file accepted, applies them together, checks them
  together (and again on master), makes ONE commit naming every file, and goes
  stale or fails together;
* a task over one file is exactly what it was.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.maintenance import daily_work as dw
from aios.maintenance import sandbox_tests as st
from tests.test_gagos_daily import AFTER, BEFORE, REL, RULE, _git, _repo, _result, _warn
from tests.test_gagos_workforce import OTHER, _batch
from tools import gagos_daily as tool

WORDS = "Rename the unused local to `spare`, and say why in a comment."
SECRET = "AKIAIOSFODNN7EXAMPLE"


def _answer(*files: tuple[int, str, str]) -> str:
    """A writer's answer: ``(index, name, text)`` for each file it changes."""
    return "\n".join(f"File {n}: {name}\n```jsx\n{text}```" for n, name, text in files)


TWO = _answer((1, "Panel.jsx", AFTER), (2, "Other.jsx", AFTER))


def _writer(monkeypatch, answer, prompts=None):
    """Every writer gives *answer* (a text, or a function of the prompt) and its
    model is kept in the returned list."""
    asked: list = []

    def completer(model, region):
        def complete(prompt, system, request_id):
            asked.append(model)
            if prompts is not None:
                prompts.append((prompt, system))
            return answer(prompt) if callable(answer) else answer

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    return asked


def _many(tmp_path, monkeypatch, answer=TWO, *, also=(OTHER,), prompts=None, **kw):
    led, _batch_asked, args, ids = _batch(tmp_path, monkeypatch, **kw)
    asked = _writer(monkeypatch, answer, prompts)
    tid = led.add_task(REL, WORDS, said_by="operator", also=also)
    args.rules = ["none-such"]
    return led, asked, args, tid


# ------------------------------------------------------------- the answer parser


def test_the_parser_reads_a_block_for_each_labelled_file() -> None:
    got = dw.parse_task_files(TWO, [BEFORE, BEFORE])
    assert got == {0: AFTER, 1: AFTER}


def test_a_file_the_writer_leaves_out_is_unchanged() -> None:
    got = dw.parse_task_files(_answer((2, "Other.jsx", AFTER)), [BEFORE, BEFORE])
    assert got == {1: AFTER}
    assert dw.parse_task_files("I cannot do this in these files.", [BEFORE]) == {}


def test_each_file_keeps_its_own_line_endings() -> None:
    crlf = "a\r\nb\r\n"
    got = dw.parse_task_files(
        _answer((1, "a.py", "x\ny\n"), (2, "b.py", "p\nq\n")), [crlf, "p\nq"]
    )
    assert got == {0: "x\r\ny\r\n", 1: "p\nq"}


@pytest.mark.parametrize(
    "raw, why",
    [
        ("```jsx\nx\n```", "has no `File N` label"),
        ("File 1: Panel.jsx\nI changed it.", "has no fenced code block"),
        (
            "File 1: Panel.jsx\nFile 2: Other.jsx\n```jsx\nx\n```",
            "File 1 is labelled but has no fenced code block",
        ),
        (_answer((3, "Third.jsx", "x\n")), "the task has 2 file(s)"),
        (_answer((0, "Zero.jsx", "x\n")), "the task has 2 file(s)"),
        (
            _answer((1, "Panel.jsx", "x\n"), (1, "Panel.jsx", "y\n")),
            "File 1 is given twice",
        ),
        (_answer((1, "Panel.jsx", "\n")), "empty"),
    ],
)
def test_the_parser_refuses_what_it_cannot_assign(raw: str, why: str) -> None:
    with pytest.raises(dw.ProposalRefused, match=re.escape(why)):
        dw.parse_task_files(raw, [BEFORE, BEFORE])


def test_a_labelled_line_inside_a_file_is_not_a_label() -> None:
    inside = "File 2: not a label, a line of the file\n" + AFTER
    got = dw.parse_task_files(_answer((1, "Panel.jsx", inside)), [BEFORE, BEFORE])
    assert got == {0: inside}


# ------------------------------------------------------------- a task becomes a job


def test_a_task_over_two_files_is_two_grouped_proposals_and_takes_the_task(
    tmp_path, monkeypatch
) -> None:
    prompts: list = []
    led, asked, args, tid = _many(tmp_path, monkeypatch, prompts=prompts)
    assert tool.cmd_propose(args) == 0
    assert len(asked) == 1, "one writer call for the whole task"
    members = led.group_members(tid)
    assert [(p["rel"], p["rule"], p["status"]) for p in members] == [
        (REL, dw.TASK_RULE, "proposed"),
        (OTHER, dw.TASK_RULE, "proposed"),
    ]
    assert all(p["group_id"] == tid and p["new_text"] == AFTER for p in members)
    task = led.task(tid)
    assert (task["status"], task["proposal_id"]) == ("taken", members[0]["proposal_id"])
    ((prompt, system),) = prompts
    assert WORDS in prompt and "spans several" in system
    assert "File 1: Panel.jsx" in prompt and "File 2: Other.jsx" in prompt
    assert REL not in prompt and OTHER not in prompt, "a name, never a path"
    assert "Warnings to fix" not in prompt, "a task is not a lint fix"
    progress = led.task_progress()[0]
    assert [m["rel"] for m in progress["proposals"]] == [REL, OTHER]
    assert json.dumps(progress)


def test_a_file_the_writer_does_not_change_is_not_a_member(
    tmp_path, monkeypatch
) -> None:
    led, _asked, args, tid = _many(
        tmp_path, monkeypatch, _answer((2, "Other.jsx", AFTER))
    )
    assert tool.cmd_propose(args) == 0
    (only,) = led.group_members(tid)
    assert only["rel"] == OTHER and only["status"] == "proposed"
    assert led.task(tid)["proposal_id"] == only["proposal_id"]


def test_a_task_the_writer_changes_nothing_of_is_one_refused_proposal(
    tmp_path, monkeypatch
) -> None:
    for answer in ("It needs a third file.", _answer((1, "Panel.jsx", BEFORE))):
        led, _asked, args, tid = _many(tmp_path / str(len(answer)), monkeypatch, answer)
        assert tool.cmd_propose(args) == 0
        (p,) = led.proposals()
        assert p["status"] == "refused" and "every file unchanged" in p["refusal"]
        assert led.task(tid)["proposal_id"] == p["proposal_id"]
        assert led.group_members(tid) == []


def test_an_answer_with_a_block_and_no_label_is_refused_and_takes_the_task(
    tmp_path, monkeypatch
) -> None:
    led, _asked, args, tid = _many(tmp_path, monkeypatch, f"```jsx\n{AFTER}```")
    assert tool.cmd_propose(args) == 0
    (p,) = led.proposals()
    assert p["status"] == "refused" and "has no `File N` label" in p["refusal"]
    assert led.task(tid)["status"] == "taken"


def test_a_failed_model_call_leaves_the_several_file_task_open(
    tmp_path, monkeypatch
) -> None:
    def refusing(prompt):
        raise RuntimeError("AWS refused the account")

    led, _asked, args, tid = _many(tmp_path, monkeypatch, refusing)
    assert tool.cmd_propose(args) == 0
    task = led.task(tid)
    assert (task["status"], task["proposal_id"]) == ("open", None)
    (failed,) = led.proposals()
    assert failed["refusal"].startswith("model call failed")
    assert led.group_members(tid) == [], "a failed call is not part of the task"


# ------------------------------------------------------------- refused before any model


@pytest.mark.parametrize("also", [["README.md"], ["frontend/src/nowhere.jsx"]])
def test_one_file_gagos_may_not_edit_refuses_the_whole_task_before_any_model(
    tmp_path, monkeypatch, also
) -> None:
    led, asked, args, tid = _many(tmp_path, monkeypatch, also=also)
    assert tool.cmd_propose(args) == 0
    task = led.task(tid)
    assert task["status"] == "refused" and "may edit" in task["reason"]
    assert also[0] in task["reason"]
    assert asked == [] and led.proposals() == []


def test_the_first_file_may_be_the_one_gagos_may_not_edit(
    tmp_path, monkeypatch
) -> None:
    led, asked, args, _tid = _many(tmp_path, monkeypatch)
    bad = led.add_task("README.md", WORDS, said_by="operator", also=[REL])
    assert tool.cmd_propose(args) == 0
    assert led.task(bad)["status"] == "refused" and asked != []


def test_a_python_file_of_the_frozen_core_refuses_a_mixed_task(
    tmp_path, monkeypatch
) -> None:
    led, asked, args, _tid = _many(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "editable_python_files", lambda root: ["aios/x.py"])
    frozen = led.add_task(
        REL, WORDS, said_by="operator", also=["aios/core/executor.py"]
    )
    assert tool.cmd_propose(args) == 0
    assert led.task(frozen)["status"] == "refused"
    assert "aios/core/executor.py" in led.task(frozen)["reason"]


def test_a_file_over_the_bound_refuses_the_task(tmp_path, monkeypatch) -> None:
    led, asked, args, tid = _many(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "MAX_FILE_CHARS", 10)
    assert tool.cmd_propose(args) == 0
    assert "bound" in led.task(tid)["reason"] and led.task(tid)["status"] == "refused"
    assert asked == [] and led.proposals() == []


def test_files_that_are_too_long_together_for_one_answer_refuse_the_task(
    tmp_path, monkeypatch
) -> None:
    led, asked, args, tid = _many(tmp_path, monkeypatch)
    each = len(BEFORE)
    monkeypatch.setattr(tool, "MAX_TASK_TOTAL_CHARS", 2 * each - 1)
    assert tool.cmd_propose(args) == 0
    task = led.task(tid)
    assert task["status"] == "refused"
    assert f"{2 * each} characters together" in task["reason"]
    assert str(2 * each - 1) in task["reason"]
    assert asked == [] and led.proposals() == []
    # And exactly at the bound the task goes.
    led2, asked2, args2, tid2 = _many(tmp_path / "ok", monkeypatch)
    monkeypatch.setattr(tool, "MAX_TASK_TOTAL_CHARS", 2 * each)
    assert tool.cmd_propose(args2) == 0 and len(asked2) == 1
    assert led2.task(tid2)["status"] == "taken"


def test_the_bound_is_measured_on_the_files_as_sent(tmp_path, monkeypatch) -> None:
    """A reviewer of D14 (2026-11-03): a placeholder can be longer than what it
    hides, so files that fit unmasked could overflow the answer once masked."""
    led, asked, args, tid = _many(tmp_path, monkeypatch)
    each = len(BEFORE)
    monkeypatch.setattr(tool, "MAX_TASK_TOTAL_CHARS", 2 * each)
    real = tool.mask_lines

    def longer(text, redact, **kw):
        masked, mapping = real(text, redact, **kw)
        return masked + "/" * 10, mapping

    monkeypatch.setattr(tool, "mask_lines", longer)
    assert tool.cmd_propose(args) == 0
    task = led.task(tid)
    assert (
        task["status"] == "refused" and f"{2 * each + 20} characters" in task["reason"]
    )
    assert asked == []


def test_the_total_bound_fits_one_answer() -> None:
    answer_chars = tool.MAX_OUTPUT_TOKENS * tool.CHARS_PER_TOKEN
    assert dw.MAX_TASK_TOTAL_CHARS < answer_chars, (
        "a change that rewrites every file whole still fits one answer"
    )


def test_a_file_a_change_holds_makes_the_task_wait_and_nothing_is_asked(
    tmp_path, monkeypatch, capsys
) -> None:
    led, asked, args, tid = _many(tmp_path, monkeypatch)
    args.skip = [OTHER]
    assert tool.cmd_propose(args) == 0
    assert (led.task(tid)["status"], asked) == ("open", [])
    assert f"waits: another GAGOS change holds {OTHER}" in capsys.readouterr().out


def test_a_file_an_earlier_task_of_the_batch_holds_makes_a_later_one_wait(
    tmp_path, monkeypatch
) -> None:
    led, _asked, args, tid = _many(tmp_path, monkeypatch, also=())
    other = led.add_task(OTHER, "second", said_by="operator", also=[REL])
    assert tool.cmd_propose(args) == 0
    assert led.task(tid)["status"] == "taken"
    assert led.task(other)["status"] == "open", "its REL is held; next hour"


def test_a_file_a_several_file_task_takes_gets_no_lint_fix_in_the_batch(
    tmp_path, monkeypatch
) -> None:
    led, _asked, args, tid = _many(tmp_path, monkeypatch)
    args.rules = [RULE]
    assert tool.cmd_propose(args) == 0
    assert {p["rule"] for p in led.proposals()} == {dw.TASK_RULE}
    assert len(led.group_members(tid)) == 2


def test_a_refused_file_trumps_a_held_one(tmp_path, monkeypatch) -> None:
    led, _asked, args, tid = _many(tmp_path, monkeypatch, also=["README.md"])
    args.skip = [REL]
    assert tool.cmd_propose(args) == 0
    assert led.task(tid)["status"] == "refused", "waiting would never end"


# ------------------------------------------------------------- the masks


def _with_secret(args) -> None:
    root = Path(args.project)
    for rel in (REL, OTHER):
        (root / rel).write_text(
            BEFORE + f'const key = "{SECRET}";\n', encoding="utf-8", newline="\n"
        )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "keys")


def _file_text(prompt: str, n: int) -> str:
    return re.search(rf"File {n}: \w+\.jsx\n```\n(.*?)\n```", prompt, re.S).group(1)


def test_each_file_is_masked_under_a_prefix_of_its_own_and_restored_by_its_own(
    tmp_path, monkeypatch
) -> None:
    prompts: list = []

    def answer(prompt):
        return _answer(
            (1, "Panel.jsx", _file_text(prompt, 1) + "\n// one\n"),
            (2, "Other.jsx", _file_text(prompt, 2) + "\n// two\n"),
        )

    led, _asked, args, tid = _many(tmp_path, monkeypatch, answer, prompts=prompts)
    _with_secret(args)
    assert tool.cmd_propose(args) == 0
    ((prompt, _system),) = prompts
    assert SECRET not in prompt
    first, second = _file_text(prompt, 1), _file_text(prompt, 2)
    assert "GAGOSMASKQ_0000" in first and "GAGOSMASKQQ_0000" in second
    a, b = led.group_members(tid)
    assert a["status"] == b["status"] == "proposed"
    assert SECRET in a["new_text"] and SECRET in b["new_text"], "each restored"
    assert a["new_text"].endswith("// one\n") and b["new_text"].endswith("// two\n")


def test_a_placeholder_moved_into_another_file_is_refused(
    tmp_path, monkeypatch
) -> None:
    def answer(prompt):
        return _answer(
            (
                1,
                "Panel.jsx",
                _file_text(prompt, 1) + '\nconst moved = "GAGOSMASKQQ_0000";\n',
            )
        )

    led, _asked, args, tid = _many(tmp_path, monkeypatch, answer)
    _with_secret(args)
    assert tool.cmd_propose(args) == 0
    (p,) = led.proposals()
    assert p["status"] == "refused" and "placeholder of another file" in p["refusal"]
    assert led.task(tid)["status"] == "taken"


# ------------------------------------------------------------- the checks, all or nothing


def _parse_fails_on(marker: str):
    return lambda root, texts, **kw: {
        k: _result(parse=("Unexpected token",))
        if marker in v
        else _result()
        if v == AFTER
        else _result(_warn(RULE))
        for k, v in texts.items()
    }


def test_one_refused_file_refuses_every_file_of_the_task(tmp_path, monkeypatch) -> None:
    answer = _answer((1, "Panel.jsx", AFTER), (2, "Other.jsx", BEFORE + "// BROKEN\n"))
    led, _asked, args, tid = _many(tmp_path, monkeypatch, answer)
    monkeypatch.setattr(tool, "check_texts", _parse_fails_on("BROKEN"))
    assert tool.cmd_propose(args) == 0
    good, bad = led.group_members(tid)
    assert (good["rel"], bad["rel"]) == (REL, OTHER)
    assert good["status"] == bad["status"] == "refused"
    assert "does not parse" in bad["refusal"]
    assert OTHER in good["refusal"] and "does not parse" in good["refusal"]
    assert "all or nothing" in good["refusal"]
    assert led.task(tid)["proposal_id"] == good["proposal_id"], "the first takes it"
    assert led.awaiting_tests() == [] and led.awaiting("claude") == []


def test_a_failing_file_is_named_when_it_is_the_first(tmp_path, monkeypatch) -> None:
    answer = _answer((1, "Panel.jsx", BEFORE + "// BROKEN\n"), (2, "Other.jsx", AFTER))
    led, _asked, args, tid = _many(tmp_path, monkeypatch, answer)
    monkeypatch.setattr(tool, "check_texts", _parse_fails_on("BROKEN"))
    assert tool.cmd_propose(args) == 0
    first, second = led.group_members(tid)
    assert "does not parse" in first["refusal"]
    assert REL in second["refusal"] and "all or nothing" in second["refusal"]


def test_a_file_that_adds_a_disable_comment_refuses_the_group(
    tmp_path, monkeypatch
) -> None:
    sneaky = AFTER.replace(
        "  return", "  // eslint-disable-next-line no-unused-vars\n  return"
    )
    answer = _answer((1, "Panel.jsx", AFTER), (2, "Other.jsx", sneaky))
    led, _asked, args, tid = _many(tmp_path, monkeypatch, answer)

    def lint(root, texts, **kw):
        return {
            rel: _result(text=text, hidden=(_warn(RULE, line=4),))
            if "eslint-disable" in text
            else _result(text=text)
            if text == AFTER
            else _result(_warn(RULE), text=text)
            for rel, text in texts.items()
        }

    monkeypatch.setattr(tool, "check_texts", lint)
    assert tool.cmd_propose(args) == 0
    good, bad = led.group_members(tid)
    assert good["status"] == bad["status"] == "refused"
    assert "disable comment" in bad["refusal"]
    assert OTHER in good["refusal"] and "all or nothing" in good["refusal"]


# ------------------------------------------------------------- the tests, once


class _Trees:
    def __init__(self, root) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        pass


def _proposed_group(tmp_path, monkeypatch):
    led, asked, args, tid = _many(tmp_path, monkeypatch)
    assert tool.cmd_propose(args) == 0
    return led, tid


def _test_args(tmp_path):
    return SimpleNamespace(project=str(tmp_path), again=None)


def test_the_group_is_tested_once_with_every_change_and_recorded_on_every_file(
    tmp_path, monkeypatch
) -> None:
    led, tid = _proposed_group(tmp_path, monkeypatch)
    seen: list = []
    monkeypatch.setattr(tool, "BaseTrees", _Trees)
    monkeypatch.setattr(
        tool,
        "run_change_tests",
        lambda trees, **kw: (
            seen.append(kw) or st.SandboxVerdict(st.PASSED, "9 tests in 2 files pass")
        ),
    )
    assert tool.cmd_test(_test_args(tmp_path)) == 0
    ((kw,),) = [(k,) for k in seen]
    assert len(seen) == 1, "once for the group"
    assert kw["changes"] == {REL: AFTER, OTHER: AFTER}
    members = led.group_members(tid)
    assert [st.SandboxVerdict.from_json(p["sandbox"]).outcome for p in members] == [
        st.PASSED,
        st.PASSED,
    ]
    assert led.awaiting_tests() == []
    assert {p["status"] for p in members} == {"proposed"}


def test_a_refusal_of_the_tests_refuses_every_file(tmp_path, monkeypatch) -> None:
    led, tid = _proposed_group(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "BaseTrees", _Trees)
    monkeypatch.setattr(
        tool,
        "run_change_tests",
        lambda trees, **kw: st.SandboxVerdict(
            st.BROKE,
            "1 test(s) pass without it and fail with it: test_x.py::test_a",
            ("tests/test_x.py",),
            ("tests/test_x.py::test_a",),
        ),
    )
    assert tool.cmd_test(_test_args(tmp_path)) == 0
    members = led.group_members(tid)
    assert {p["status"] for p in members} == {"refused"}
    assert all(p["refusal"].startswith(st.BROKE_PREFIX) for p in members)
    assert led.awaiting("claude") == []


def test_a_single_proposal_goes_through_the_same_entry_as_a_set(
    tmp_path, monkeypatch
) -> None:
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)
    args.budget = 1
    assert tool.cmd_propose(args) == 0
    seen: list = []
    monkeypatch.setattr(tool, "BaseTrees", _Trees)
    monkeypatch.setattr(
        tool,
        "run_change_tests",
        lambda trees, **kw: seen.append(kw) or st.SandboxVerdict(st.PASSED, "ok"),
    )
    assert tool.cmd_test(_test_args(tmp_path)) == 0
    (kw,) = seen
    (p,) = led.proposals()
    assert kw["changes"] == {p["rel"]: AFTER} and kw["base_commit"] == p["base_commit"]


def test_the_frontend_files_tests_say_why_they_do_not_run(
    tmp_path, monkeypatch
) -> None:
    """The tool has no frontend branch of its own any more: what the sandbox
    cannot run it says, and the proposal goes on to review."""
    led, tid = _proposed_group(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "BaseTrees", _Trees)
    assert tool.cmd_test(_test_args(tmp_path)) == 0
    for p in led.group_members(tid):
        verdict = st.SandboxVerdict.from_json(p["sandbox"])
        assert verdict.outcome == st.UNAVAILABLE and p["status"] == "proposed"


# ------------------------------------------------------------- one review per group


def _review_args(**kw):
    return SimpleNamespace(
        reviewer="claude", model=None, limit=10, timeout=1, again=None, **kw
    )


def test_a_group_is_reviewed_once_and_the_verdict_is_on_every_file(
    tmp_path, monkeypatch
) -> None:
    led, tid = _proposed_group(tmp_path, monkeypatch)
    prompts: list = []

    def runner(prompt, *, model, timeout_s):
        prompts.append(prompt)
        return "accept", "both files agree and do what he asked", "claude-x"

    monkeypatch.setitem(tool.REVIEWER_RUNNERS, "claude", runner)
    assert tool.cmd_review(_review_args()) == 0
    assert len(prompts) == 1, "never a member alone"
    (prompt,) = prompts
    assert WORDS in prompt and "spans 2 files" in prompt
    assert "File 1: Panel.jsx" in prompt and "File 2: Other.jsx" in prompt
    assert prompt.count("-  const unused = 1;") == 2, "both diffs are shown"
    assert REL not in prompt and OTHER not in prompt
    members = led.group_members(tid)
    assert {p["status"] for p in members} == {"accepted"}
    for p in members:
        assert led.reviews(p["proposal_id"])["claude"]["verdict"] == "accept"
    assert led.awaiting("claude") == []


def test_a_reject_rejects_every_file(tmp_path, monkeypatch) -> None:
    led, tid = _proposed_group(tmp_path, monkeypatch)
    monkeypatch.setitem(
        tool.REVIEWER_RUNNERS,
        "claude",
        lambda prompt, *, model, timeout_s: ("reject", "the files disagree", "m"),
    )
    assert tool.cmd_review(_review_args()) == 0
    assert {p["status"] for p in led.group_members(tid)} == {"rejected"}


def test_a_group_is_one_of_the_limit(tmp_path, monkeypatch) -> None:
    led, tid = _proposed_group(tmp_path, monkeypatch)
    other = led.add_task(OTHER, "later", said_by="operator")
    pid = led.record_proposal(
        dw.Finding(OTHER, dw.TASK_RULE, ()),
        base_text=BEFORE,
        base_commit="c" * 40,
        model="writer-a",
        new_text=AFTER,
        verdict=dw.StaticVerdict(True, "ok", 2),
    )
    led.take_task(other, pid)
    calls: list = []
    monkeypatch.setitem(
        tool.REVIEWER_RUNNERS,
        "claude",
        lambda prompt, *, model, timeout_s: calls.append(1) or ("accept", "ok", "m"),
    )
    args = _review_args()
    args.limit = 1
    assert tool.cmd_review(args) == 0
    assert len(calls) == 1
    assert {p["status"] for p in led.group_members(tid)} == {"accepted"}


def test_a_group_that_cannot_be_shown_is_refused_whole_and_reopened_whole(
    tmp_path, monkeypatch
) -> None:
    led, tid = _proposed_group(tmp_path, monkeypatch)
    real = tool.would_be_altered
    monkeypatch.setattr(
        tool, "would_be_altered", lambda p, s: "a span would be redacted"
    )
    monkeypatch.setitem(
        tool.REVIEWER_RUNNERS, "claude", lambda *a, **k: pytest.fail("not shown")
    )
    assert tool.cmd_review(_review_args()) == 0
    members = led.group_members(tid)
    assert {p["status"] for p in members} == {"refused"}
    assert all(p["refusal"].startswith(dw.UNSHOWABLE) for p in members)
    monkeypatch.setattr(tool, "would_be_altered", real)
    monkeypatch.setitem(
        tool.REVIEWER_RUNNERS,
        "claude",
        lambda prompt, *, model, timeout_s: ("accept", "fine", "m"),
    )
    # Asking again for ONE member brings the whole group back and reviews it once.
    args = _review_args()
    args.again = [members[1]["proposal_id"]]
    assert tool.cmd_review(args) == 0
    assert {p["status"] for p in led.group_members(tid)} == {"accepted"}


def test_a_group_with_a_member_out_of_the_work_is_not_reviewed(
    tmp_path, monkeypatch
) -> None:
    led, tid = _proposed_group(tmp_path, monkeypatch)
    first, second = led.group_members(tid)
    led.refuse(first["proposal_id"], "gone")
    monkeypatch.setitem(
        tool.REVIEWER_RUNNERS, "claude", lambda *a, **k: pytest.fail("a member alone")
    )
    assert tool.cmd_review(_review_args()) == 0
    after = {p["rel"]: p for p in led.group_members(tid)}
    assert (
        after[OTHER]["status"] == "refused"
        and "all or nothing" in (after[OTHER]["refusal"])
    )


# ------------------------------------------------------------- delivery


@pytest.fixture()
def project(tmp_path):
    """An origin and a worktree of it holding REL and OTHER."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "master", str(origin)], check=True
    )
    seed = _repo(tmp_path / "seed")
    (seed / OTHER).write_bytes(BEFORE.encode())
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "other")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "master")
    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", "-q", "-c", "core.autocrlf=false", str(origin), str(work)],
        check=True,
    )
    for key, value in (
        ("user.email", "t@example.com"),
        ("user.name", "t"),
        ("core.autocrlf", "false"),
    ):
        _git(work, "config", key, value)
    return seed, work


def _group(led, *, accept=(True, True)):
    tid = led.add_task(REL, WORDS, said_by="operator", also=[OTHER])
    ids = []
    for rel in (REL, OTHER):
        ids.append(
            led.record_proposal(
                dw.Finding(rel, dw.TASK_RULE, ()),
                base_text=BEFORE,
                base_commit="c" * 40,
                model="writer-a",
                new_text=AFTER,
                verdict=dw.StaticVerdict(True, "ok", 2),
                group_id=tid,
            )
        )
    led.take_task(tid, ids[0])
    for pid, yes in zip(ids, accept):
        if yes:
            led.record_review(
                pid, "claude", model="opus", verdict="accept", reason="both agree"
            )
    return tid, ids


def _deliver_args(work):
    return SimpleNamespace(
        worktree=str(work),
        branch="gagos/daily-test",
        check_timeout=60,
        open_pr=False,
        pr_footer="",
    )


def _commits(work) -> int:
    return int(_git(work, "rev-list", "--count", "origin/master..HEAD"))


def test_both_files_are_one_commit_naming_every_file_when_both_are_accepted(
    tmp_path, monkeypatch, project
) -> None:
    _seed, work = project
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    front: list = []
    monkeypatch.setattr(
        smoke, "frontend_smoke", lambda root, paths, **kw: front.append(paths) or None
    )
    tid, ids = _group(led)
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert _commits(work) == 1, "ONE commit"
    assert sorted(_git(work, "show", "--name-only", "--format=", "HEAD").split()) == (
        sorted([OTHER, REL])
    )
    assert (work / REL).read_text(encoding="utf-8") == AFTER
    assert (work / OTHER).read_text(encoding="utf-8") == AFTER
    message = _git(work, "log", "-1", "--format=%B")
    assert message.startswith("GAGOS: the operator's task in 2 files: Rename")
    assert REL in message and OTHER in message and tid in message
    assert all(pid in message for pid in ids) and "both agree" in message
    assert "Proposed-by: GAGOS" in message and "Reviewed-by: Claude Code" in message
    assert len(front) == 1 and len(front[0]) == 2, "checked together, once"
    members = led.group_members(tid)
    assert {p["status"] for p in members} == {"committed"}
    shas = {led.commit_of(pid) for pid in ids}
    assert shas == {_git(work, "rev-parse", "HEAD")}
    assert led.pending_publication() == {"gagos/daily-test": ids}


def test_a_python_file_and_a_frontend_file_are_each_checked_by_their_own(
    tmp_path, monkeypatch, project
) -> None:
    seed, work = project
    (seed / "aios").mkdir()
    (seed / "aios" / "x.py").write_bytes(b"x = 1\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "py")
    _git(seed, "push", "-q", "origin", "master")
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    seen: dict = {}
    monkeypatch.setattr(
        smoke,
        "frontend_smoke",
        lambda root, paths, **kw: seen.update(front=[p.name for p in paths]),
    )
    monkeypatch.setattr(
        smoke,
        "python_smoke",
        lambda root, rels, **kw: (
            seen.update(py=list(rels)) or SimpleNamespace(passed=True, reason="")
        ),
    )
    tid = led.add_task(REL, WORDS, said_by="operator", also=["aios/x.py"])
    ids = []
    for rel, base, new in ((REL, BEFORE, AFTER), ("aios/x.py", "x = 1\n", "x = 2\n")):
        ids.append(
            led.record_proposal(
                dw.Finding(rel, dw.TASK_RULE, ()),
                base_text=base,
                base_commit="c" * 40,
                model="m",
                new_text=new,
                verdict=dw.StaticVerdict(True, "ok", 1),
                group_id=tid,
            )
        )
        led.record_review(
            ids[-1], "claude", model="opus", verdict="accept", reason="fine"
        )
    seen.clear()
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert seen == {"front": ["Panel.jsx"], "py": ["aios/x.py"]}
    assert _commits(work) == 1
    message = _git(work, "log", "-1", "--format=%B")
    assert "the Python files compile, the frontend files parse" in message


def test_nothing_is_delivered_until_every_file_is_accepted(
    tmp_path, monkeypatch, project
) -> None:
    _seed, work = project
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    monkeypatch.setattr(smoke, "frontend_smoke", lambda *a, **k: None)
    tid, _ids = _group(led, accept=(True, False))
    head = _git(work, "rev-parse", "HEAD")
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert _git(work, "rev-parse", "HEAD") == head
    assert sorted(p["status"] for p in led.group_members(tid)) == [
        "accepted",
        "proposed",
    ]
    assert (work / REL).read_text(encoding="utf-8") == BEFORE


def test_a_task_goes_stale_when_any_one_file_changed(
    tmp_path, monkeypatch, project
) -> None:
    seed, work = project
    (seed / OTHER).write_text(BEFORE + "// changed on master\n", encoding="utf-8")
    _git(seed, "commit", "-qam", "master moved")
    _git(seed, "push", "-q", "origin", "master")
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    tid, _ids = _group(led)
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert {p["status"] for p in led.group_members(tid)} == {"stale"}
    assert (work / REL).read_text(encoding="utf-8") == BEFORE, "REL was not applied"
    assert _commits(work) == 0


def test_a_task_that_fails_its_checks_fails_together_and_leaves_both_files(
    tmp_path, monkeypatch, project
) -> None:
    _seed, work = project
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    # Fails with the change, passes without it: the change's doing.
    monkeypatch.setattr(
        smoke,
        "frontend_smoke",
        lambda root, paths, **k: (
            "the tests related to the frontend targets did not pass"
            if paths[0].read_text(encoding="utf-8") == AFTER
            else None
        ),
    )
    tid, _ids = _group(led)
    head = _git(work, "rev-parse", "HEAD")
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert {p["status"] for p in led.group_members(tid)} == {"failed"}
    assert _git(work, "rev-parse", "HEAD") == head and not _git(
        work, "status", "--porcelain"
    )
    for rel in (REL, OTHER):
        assert (work / rel).read_text(encoding="utf-8") == BEFORE


def test_a_check_failing_on_master_too_is_judged_over_the_whole_set(
    tmp_path, monkeypatch, project
) -> None:
    _seed, work = project
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    seen: list = []

    def both(root, paths, **k):
        seen.append([p.read_text(encoding="utf-8") for p in paths])
        return "the tests related to the frontend targets did not pass"

    monkeypatch.setattr(smoke, "frontend_smoke", both)
    tid, _ids = _group(led)
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert seen == [[AFTER, AFTER], [BEFORE, BEFORE]], "with them, then without them"
    assert {p["status"] for p in led.group_members(tid)} == {"committed"}
    assert _commits(work) == 1
    message = _git(work, "log", "-1", "--format=%B")
    assert "fails on master without them too" in message and "CI judges it" in message


# ------------------------------------------------------------- the report and the list


def test_the_report_and_the_list_show_a_tasks_files_and_their_status(
    tmp_path, monkeypatch, capsys
) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    tid, ids = _group(led)
    text = tool.report(led)
    assert f"`{tid}` in `{REL}`, `{OTHER}`: taken, proposals" in text
    assert f"`{ids[0]}` ({REL}) accepted" in text and f"`{ids[1]}` ({OTHER})" in text
    assert f"one of the files of task `{tid}`" in text
    assert WORDS not in text, "never his words"
    waiting = led.add_task(OTHER, "later", said_by="operator", also=[REL])
    assert f"`{waiting}` in `{OTHER}`, `{REL}`: open" in tool.report(led)
    assert tool.main(["task", "list"]) == 0
    out = capsys.readouterr().out
    assert (
        f"{tid} taken -> proposals {ids[0]} accepted, {ids[1]} accepted {REL},{OTHER}:"
    ) in out
    assert f"{waiting} open {OTHER},{REL}: later" in out


def test_the_command_line_adds_a_task_over_several_files(
    tmp_path, monkeypatch, capsys
) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    assert tool.main(["task", "add", "--file", REL, "--also", OTHER, WORDS]) == 0
    (task,) = led.tasks()
    assert task["files"] == [REL, OTHER]
    assert capsys.readouterr().out.strip() == task["task_id"]
    too_many = ["--also", "a.py", "--also", "b.py", "--also", "c.py", "--also", "d.py"]
    assert (
        tool.main(["task", "add", "--file", REL, *too_many, "--also", "e.py", WORDS])
        == 2
    )
    assert "at most 5 files" in capsys.readouterr().out
    assert tool.main(["task", "add", "--file", REL, "--also", REL, WORDS]) == 2
    assert "named twice" in capsys.readouterr().out


def test_a_task_over_several_files_is_found_from_any_of_its_proposals(
    tmp_path,
) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    tid, ids = _group(led)
    assert [led.task_of_proposal(pid)["task_id"] for pid in ids] == [tid, tid]
    assert led.task_of_proposal("gd-nope") is None


# ------------------------------------------------------------- one file is as it was


def test_a_task_over_one_file_keeps_its_prompt_its_answer_and_its_record(
    tmp_path, monkeypatch
) -> None:
    prompts: list = []
    led, asked, args, _ids = _batch(tmp_path, monkeypatch)
    _writer(monkeypatch, f"```jsx\n{AFTER}```", prompts)
    tid = led.add_task(REL, WORDS, said_by="operator")
    args.rules = ["none-such"]
    assert tool.cmd_propose(args) == 0
    ((prompt, system),) = prompts
    masked_text = BEFORE.rstrip("\n")
    assert prompt == dw.task_prompt(
        REL, WORDS, masked_text + "\n", facts=_facts(prompt)
    )
    assert system == dw.task_system(REL)
    assert "File 1:" not in prompt
    (p,) = led.proposals()
    assert p["group_id"] is None and p["status"] == "proposed"
    assert led.task(tid)["proposal_id"] == p["proposal_id"]
    message = tool.commit_message(p, {}, task=led.task_of_proposal(p["proposal_id"]))
    assert message.startswith(f"GAGOS: the operator's task in {REL}:")
    assert "Files:" not in message


def _facts(prompt: str) -> tuple[str, ...]:
    block = prompt.split("Facts about this project, and the operator's direction:\n")
    if len(block) == 1:
        return ()
    lines = block[1].split("\n\n")[0].splitlines()
    return tuple(line.removeprefix("  - ") for line in lines)


def test_the_writers_instruction_says_what_kinds_of_files_the_task_spans() -> None:
    mixed = dw.task_files_system([REL, "aios/x.py"])
    assert "Python and React" in mixed and "ESLint" in mixed and "ruff" in mixed
    py = dw.task_files_system(["aios/a.py", "aios/b.py"])
    assert "ESLint" not in py and "ruff" in py
    assert "File N: name" in py and "Leave out every file you do not change" in py
