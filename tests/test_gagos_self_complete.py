"""GAGOS completing itself (2026-11-04, the operator: "I want GAGOS HONESTLY
100% complete itself"): the warnings whose fix can change behaviour become its
work. Pinned here, without a model or a network:

* such a fix may reach further than a lint fix (a rename reaches every use),
  but must still remove its warnings, add none and stay within the line bound;
* its writer is told that behaviour must not change and its tests will run;
* it reaches a reviewer only when the sandbox ran tests that exercise its file
  and they passed: no test refuses it, and a sandbox that could not run leaves
  it waiting, never reviewed untested.
"""

from __future__ import annotations

from types import SimpleNamespace

from aios.maintenance import daily_work as dw
from aios.maintenance import sandbox_tests as st
from tests.test_gagos_daily import _result, _warn
from tools import gagos_daily as tool

REL = "frontend/src/workbench/Panel.jsx"
HOOK = "react-hooks/set-state-in-effect"
BEFORE = "".join(f"const line{i} = {i};\n" for i in range(1, 21))


def _changed_at(line: int) -> str:
    rows = BEFORE.splitlines(keepends=True)
    rows[line - 1] = rows[line - 1].replace(";", "; // moved")
    return "".join(rows)


def _verdict(rule: str, warning_line: int, changed_line: int):
    finding = dw.Finding(rel=REL, rule=rule, warnings=((warning_line, 1, "x"),))
    before = _result(_warn(rule, line=warning_line), text=BEFORE)
    after_text = _changed_at(changed_line)
    after = _result(text=after_text)
    return dw.static_verdict(finding, BEFORE, after_text, before, after)


def test_a_behaviour_fix_may_reach_further_than_a_lint_fix() -> None:
    assert not _verdict("no-unused-vars", 3, 11).passed, "a lint fix stays near"
    assert _verdict(HOOK, 3, 11).passed, "an effect's body sits a few lines away"
    far = _verdict(HOOK, 3, 19)
    assert not far.passed and "within 12 lines" in far.reason
    assert _verdict("E741", 1, 20).passed, "a rename reaches every use"


def test_its_writer_is_told_behaviour_must_not_change() -> None:
    finding = dw.Finding(rel=REL, rule=HOOK, warnings=((3, 1, "x"),))
    assert "tests that exercise this file" in dw.proposal_prompt(finding, BEFORE)
    lint = dw.Finding(rel=REL, rule="no-unused-vars", warnings=((3, 1, "x"),))
    assert "tests that exercise this file" not in dw.proposal_prompt(lint, BEFORE)


class _Trees:
    def __init__(self, root) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        pass


def _proposed(led, rule=HOOK) -> str:
    finding = dw.Finding(rel=REL, rule=rule, warnings=((3, 1, "x"),))
    return led.record_proposal(
        finding,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="claude-sonnet-5-5",
        new_text=_changed_at(4),
        verdict=dw.StaticVerdict(True, "ok", 2),
    )


def _tested(tmp_path, monkeypatch, verdict, rule=HOOK):
    led = dw.DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool, "BaseTrees", _Trees)
    monkeypatch.setattr(tool, "run_change_tests", lambda trees, **kw: verdict)
    pid = _proposed(led, rule)
    assert tool.cmd_test(SimpleNamespace(project=str(tmp_path), again=None)) == 0
    return led, led.proposals()[0], pid


def test_a_behaviour_fix_with_no_test_is_refused(tmp_path, monkeypatch) -> None:
    led, p, _pid = _tested(
        tmp_path, monkeypatch, st.SandboxVerdict(st.UNTESTED, "no test exercises it")
    )
    assert p["status"] == "refused" and p["refusal"].startswith(dw.UNTESTED_BEHAVIOUR)


def test_a_lint_fix_with_no_test_still_goes_to_review(tmp_path, monkeypatch) -> None:
    _led, p, _pid = _tested(
        tmp_path,
        monkeypatch,
        st.SandboxVerdict(st.UNTESTED, "no test exercises it"),
        rule="no-unused-vars",
    )
    assert p["status"] == "proposed"


def test_a_behaviour_fix_waits_when_the_sandbox_cannot_run(
    tmp_path, monkeypatch, capsys
) -> None:
    led, p, _pid = _tested(
        tmp_path, monkeypatch, st.SandboxVerdict(st.UNAVAILABLE, "image not built")
    )
    assert p["status"] == "proposed" and p["sandbox"] is None, "nothing recorded"
    assert "waits" in capsys.readouterr().out
    assert [x["proposal_id"] for x in led.awaiting_tests()] == [p["proposal_id"]]
    assert tool.awaits_tests(p), "and no reviewer reads it"


def test_only_a_passed_behaviour_fix_reaches_a_reviewer(tmp_path, monkeypatch) -> None:
    _led, p, _pid = _tested(
        tmp_path, monkeypatch, st.SandboxVerdict(st.PASSED, "8 tests in 2 files pass")
    )
    assert p["status"] == "proposed" and not tool.awaits_tests(p)
    seen: list = []

    def runner(prompt, *, model, timeout_s):
        seen.append(prompt)
        return "accept", "fine", "claude-opus-5-5"

    monkeypatch.setitem(tool.REVIEWER_RUNNERS, "claude", runner)
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (True, ""))
    tool.cmd_review(
        SimpleNamespace(reviewer="claude", limit=10, model=None, timeout=5, again=None)
    )
    assert len(seen) == 1 and "8 tests in 2 files pass" in seen[0]
