"""GAGOS's daily work on its own frontend (D14, 2026-10-30).

Pinned here, without a model or a network:

* the day's work is one file and one rule, only rules whose fix is
  behaviour-preserving by nature, never a file the port owns;
* the model's answer is used only as one whole file, in the original's line
  endings;
* the unattended checks refuse what does not parse, leaves the warnings, adds
  any other warning, silences a rule, or changes too much -- and execute
  nothing;
* a proposal is accepted only when BOTH Codex and Claude Code accept; one
  rejection rejects; every refusal reason is fed back for the rule;
* the reviewers run read-only and tool-less, and no verdict is never a verdict;
* propose obeys GAGOS's egress law, and deliver applies only accepted
  proposals to a file unchanged since, checks each, and commits each alone.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.maintenance import daily_work as dw
from aios.maintenance.frontend_static import (
    Comment,
    LintMessage,
    StaticResult,
    editable_frontend_files,
)
from tools import gagos_daily as tool

RULE = "no-unused-vars"
BEFORE = (
    "import { useMemo } from 'react';\n"
    "export function Panel({ value }) {\n"
    "  const unused = 1;\n"
    "  return useMemo(() => value, [value]);\n"
    "}\n"
)
AFTER = (
    "import { useMemo } from 'react';\n"
    "export function Panel({ value }) {\n"
    "  return useMemo(() => value, [value]);\n"
    "}\n"
)
REL = "frontend/src/workbench/Panel.jsx"


def _warn(rule, line=3, message="'unused' is assigned a value but never used."):
    return LintMessage(rule=rule, severity=1, line=line, column=9, message=message)


def _result(*messages, parse=(), hidden=(), text=""):
    """A lint result; ``hidden`` are messages only the inline-off lint shows,
    and the comments are *text*'s."""
    return StaticResult(
        messages=tuple(messages),
        parse_errors=tuple(parse),
        inline_off=tuple(messages) + tuple(hidden),
        comments=_comments(text),
    )


def _comments(text: str) -> tuple[Comment, ...]:
    """A fixture's comments, found as a JavaScript lexer finds them: a string
    or a template literal is not a comment. For fixtures only (no regular
    expression literals, no apostrophes in JSX text); the product reads the
    comments ESLint's own parser found."""
    out, i, line, n = [], 0, 1, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"`":
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            line += text.count("\n", i, j + 1)
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(Comment("Line", text[i + 2 : j], line, line))
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j
            end = line + text.count("\n", i, j)
            out.append(Comment("Block", text[i + 2 : j], line, end))
            line, i = end, j + 2
        else:
            line += ch == "\n"
            i += 1
    return tuple(out)


FINDING = dw.Finding(
    rel=REL,
    rule=RULE,
    warnings=((3, 9, "'unused' is assigned a value but never used."),),
)


# --------------------------------------------------------------------- the work


def test_the_days_work_is_one_file_and_one_allowed_rule() -> None:
    results = {
        "frontend/src/b.tsx": _result(
            _warn("@typescript-eslint/no-explicit-any"), _warn(RULE)
        ),
        "frontend/src/a.jsx": _result(_warn(RULE), _warn(RULE, line=9)),
        "frontend/src/c.jsx": _result(_warn("react-hooks/exhaustive-deps")),
    }
    work = dw.findings(results)
    assert [(f.rel, f.rule, len(f.warnings)) for f in work] == [
        ("frontend/src/a.jsx", RULE, 2),
        ("frontend/src/b.tsx", RULE, 1),
        ("frontend/src/b.tsx", "@typescript-eslint/no-explicit-any", 1),
    ], "react-hooks rules change behaviour: not in the first rules"


def test_files_the_port_owns_are_never_work(tmp_path) -> None:
    for rel in (
        "frontend/src/workbench/Mine.jsx",
        "frontend/src/superbrain/lib/Owned.ts",
        "frontend/src/superbrain/ProductOnly.tsx",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / "frontend/superbrain-source.json").write_text(
        json.dumps({"files": {"lib/Owned.ts": "d"}}), encoding="utf-8"
    )
    assert sorted(editable_frontend_files(tmp_path)) == [
        "frontend/src/superbrain/ProductOnly.tsx",
        "frontend/src/workbench/Mine.jsx",
    ]


# --------------------------------------------------------------------- the answer


def test_the_answer_is_one_whole_file_in_the_originals_line_endings() -> None:
    raw = f"Here you go:\n```jsx\n{AFTER}```\n"
    assert dw.parse_proposal(raw, original=BEFORE) == AFTER
    crlf = BEFORE.replace("\n", "\r\n")
    assert dw.parse_proposal(raw, original=crlf) == AFTER.replace("\n", "\r\n")
    with pytest.raises(dw.ProposalRefused, match="exactly one"):
        dw.parse_proposal(f"```\n{AFTER}```\n```\nmore\n```\n", original=BEFORE)
    with pytest.raises(dw.ProposalRefused, match="exactly one"):
        dw.parse_proposal(AFTER, original=BEFORE)


# --------------------------------------------------------------------- the checks


def test_a_clean_fix_passes_the_unattended_checks() -> None:
    verdict = dw.static_verdict(FINDING, BEFORE, AFTER, _result(_warn(RULE)), _result())
    assert verdict.passed, verdict.reason
    assert verdict.changed_lines == 1


@pytest.mark.parametrize(
    ("after_text", "after", "reason"),
    [
        (BEFORE, _result(_warn(RULE)), "changes nothing"),
        (AFTER, _result(parse=("Unexpected token",)), "does not parse"),
        (
            AFTER,
            _result(LintMessage("react/jsx-key", 2, 3, 1, "Missing key")),
            "ESLint error",
        ),
        (AFTER, _result(_warn(RULE)), "warnings remain"),
        (AFTER, _result(_warn("@typescript-eslint/no-explicit-any")), "adds warnings"),
        (
            AFTER + "// eslint-disable-next-line\n",
            _result(text=AFTER + "// eslint-disable-next-line\n"),
            "disable comment",
        ),
        (
            AFTER + "".join(f"// line {i}\n" for i in range(60)),
            _result(),
            "changes 61 lines",
        ),
    ],
)
def test_the_unattended_checks_refuse(after_text, after, reason) -> None:
    verdict = dw.static_verdict(
        FINDING, BEFORE, after_text, _result(_warn(RULE)), after
    )
    assert not verdict.passed and reason in verdict.reason


def test_a_warning_the_file_already_had_is_not_counted_as_new() -> None:
    other = _warn("@typescript-eslint/no-explicit-any", line=1)
    verdict = dw.static_verdict(
        FINDING, BEFORE, AFTER, _result(_warn(RULE), other), _result(other)
    )
    assert verdict.passed, verdict.reason


# --------------------------------------------------------------------- the ledger


def _proposal(led, finding=FINDING, *, passed=True):
    verdict = dw.StaticVerdict(
        passed, "ok" if passed else "the proposal adds warnings: x +1", 1
    )
    return led.record_proposal(
        finding,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="m",
        new_text=AFTER,
        verdict=verdict,
    )


def test_both_reviewers_must_accept(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    pid = _proposal(led)
    assert [p["proposal_id"] for p in led.awaiting("codex")] == [pid]
    assert (
        led.record_review(pid, "codex", model="gpt", verdict="accept", reason="ok")
        == "proposed"
    )
    assert led.awaiting("codex") == [] and len(led.awaiting("claude")) == 1
    assert (
        led.record_review(pid, "claude", model="opus", verdict="accept", reason="ok")
        == "accepted"
    )
    other = _proposal(led)
    led.record_review(
        other, "claude", model="opus", verdict="reject", reason="drops a side effect"
    )
    assert led.proposals(status="rejected")[0]["proposal_id"] == other
    # Still reviewed by the other: D14 reports how often the two disagree.
    assert [p["proposal_id"] for p in led.awaiting("codex")] == [other]
    assert (
        led.record_review(other, "codex", model="gpt", verdict="accept", reason="ok")
        == "rejected"
    )
    assert led.awaiting("codex") == [] and led.awaiting("claude") == []


def test_the_project_facts_come_from_its_own_configuration(tmp_path) -> None:
    assert dw.project_facts(tmp_path) == ()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend/tsconfig.json").write_text(
        '{ "compilerOptions": { "jsx": "react-jsx" } }', encoding="utf-8"
    )
    [fact] = dw.project_facts(tmp_path)
    assert "automatic runtime" in fact
    prompt = dw.review_prompt(FINDING, BEFORE, "diff", facts=(fact,))
    assert fact in prompt and fact in dw.proposal_prompt(FINDING, BEFORE, facts=(fact,))


def test_the_daily_report_shows_the_days_misses_too(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    shipped = _accepted(led)
    missed = _proposal(led)
    led.record_review(
        missed, "codex", model="gpt", verdict="reject", reason="JSX runtime unproven"
    )
    led.record_review(missed, "claude", model="opus", verdict="accept", reason="fine")
    text = tool.report(led, in_pr=[shipped])
    assert "(in this PR)" in text and "JSX runtime unproven" in text
    assert "disagreed (while both reviewed, until 2026-11-02): 1" in text


def test_the_reviewer_sees_only_what_the_proposal_changed() -> None:
    """2026-11-02, gd-a9f57600cf: a value the original held on several lines
    had one placeholder per line there and one for all in the proposal, so a
    correct two-line fix was rejected for class names it never touched."""
    redact = lambda text: text.replace("hiddenclass", "[R]")  # noqa: E731
    base = (
        '<a className="hiddenclass" />\n'
        "} catch (err) {\n"
        '<b className="hiddenclass" />\n'
        '<c className="hiddenclass" />\n'
    )
    new = base.replace("catch (err)", "catch")
    masked, mapping = dw.mask_lines(base, redact)
    assert len(mapping) == 3, "one placeholder per line"
    shown = dw.mask_aligned(new, base, masked, mapping)
    diff = dw.unified_diff("Panel.jsx", masked, shown)
    changed = [
        line
        for line in diff.splitlines()
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]
    assert changed == ["-} catch (err) {", "+} catch {"]
    assert "hiddenclass" not in shown
    assert dw.unmask(shown, mapping, masked=masked) == new


def test_a_verdict_given_on_wrong_evidence_is_given_again(
    tmp_path, monkeypatch
) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (True, ""))
    wronged = _proposal(led)
    led.record_review(wronged, "claude", model="opus", verdict="reject", reason="x")
    other = _proposal(led)
    led.record_review(other, "claude", model="opus", verdict="reject", reason="y")
    seen: list = []

    def runner(prompt, *, model, timeout_s):
        seen.append(prompt)
        return "accept", "only the warning is fixed", "opus"

    monkeypatch.setitem(tool.REVIEWER_RUNNERS, "claude", runner)
    args = SimpleNamespace(
        reviewer="claude", limit=10, model=None, timeout=5, again=[wronged]
    )
    assert tool.cmd_review(args) == 0
    assert len(seen) == 1
    assert {p["proposal_id"]: p["status"] for p in led.proposals()} == {
        wronged: "accepted",
        other: "rejected",
    }


def test_a_fix_that_reaches_beyond_its_warnings_is_refused_before_review() -> None:
    base = "".join(f"line {n}\n" for n in range(1, 41))
    near = base.replace("line 3\n", "line three\n")
    far = near.replace("line 20\n", "line twenty\n")
    f = dw.Finding(rel=REL, rule="no-unused-vars", warnings=((3, 9, "x"),))
    assert dw.beyond_reach(dw.unified_diff("f", base, near), [3]) == []
    assert dw.beyond_reach(dw.unified_diff("f", base, far), [3]) == [(20, 17)]
    clean = _result()
    verdict = dw.static_verdict(f, base, far, clean, clean)
    assert not verdict.passed
    assert "line 20, 17 lines from the nearest warning" in verdict.reason


def test_the_report_says_what_an_accepted_change_costs_and_where_work_is_lost(
    tmp_path,
) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    _accepted(led)
    led.record_proposal(
        FINDING,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="m",
        new_text=None,
        verdict=None,
        refusal="expected exactly one fenced code block, got 0",
    )
    text = tool.report(led)
    assert "accepted by review: 1 of 2 proposals" in text
    assert "the answer's form 1" in text and "the reviewer 0" in text


def test_placeholders_never_look_like_secrets_and_never_occur_in_the_file() -> None:
    from aios.runtime.secret_policy import SecretPolicy

    redact = lambda text: text.replace("hiddenclass", "[R]")  # noqa: E731
    base = "".join(f'<div className="hiddenclass" id="{n}" />\n' for n in range(30))
    masked, mapping = dw.mask_lines(base, redact)
    assert all(t.startswith("GAGOSMASKQ_") for t in mapping)
    assert SecretPolicy().inspect_text(masked).scrubbed == masked
    taken = "GAGOSMASKQ_ is already here\n" + base
    _masked, again = dw.mask_lines(taken, redact)
    assert all(t.startswith("GAGOSMASKQQ_") for t in again)


def test_a_call_the_provider_refused_does_not_use_up_its_finding(tmp_path) -> None:
    """2026-11-02 20:50 UTC: Bedrock refused the account; ten findings were
    recorded as proposals no model ever wrote."""
    led = dw.DailyLedger(tmp_path / "ledger.db")
    common = dict(base_text=BEFORE, base_commit="c" * 40, model="m", new_text=None)
    led.record_proposal(
        FINDING,
        **common,
        verdict=None,
        refusal="model call failed: ValidationException: Access to Bedrock models "
        "is not allowed for this account",
    )
    assert not led.attempted(FINDING.rel, FINDING.rule, dw.digest(BEFORE))
    led.record_proposal(
        FINDING,
        **common,
        verdict=None,
        refusal="expected exactly one fenced code block",
    )
    assert led.attempted(FINDING.rel, FINDING.rule, dw.digest(BEFORE))


def test_only_a_proposal_refused_for_how_it_was_shown_is_reopened(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    shown = _proposal(led)
    led.refuse(shown, f"{dw.UNSHOWABLE}: the secret policy would scrub this file")
    other = _proposal(led)
    led.refuse(other, "the privacy filter would redact this file")
    assert led.reopen(shown) and not led.reopen(other) and not led.reopen(shown)
    assert {p["proposal_id"]: p["status"] for p in led.proposals()} == {
        shown: "proposed",
        other: "refused",
    }


def test_proposals_claude_code_accepted_while_codex_was_required_are_accepted(
    tmp_path, monkeypatch
) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(dw, "REQUIRED_REVIEWERS", ("codex", "claude"))
    waiting = _proposal(led)
    led.record_review(waiting, "claude", model="opus", verdict="accept", reason="ok")
    unreviewed = _proposal(led)
    assert led.proposals(status="proposed") != []
    monkeypatch.setattr(dw, "REQUIRED_REVIEWERS", ("claude",))
    assert led.resettle() == [waiting]
    assert {p["proposal_id"]: p["status"] for p in led.proposals()} == {
        waiting: "accepted",
        unreviewed: "proposed",
    }
    assert led.resettle() == [], "once"


def test_claude_codes_acceptance_is_enough_and_any_reject_still_rejects(
    tmp_path,
) -> None:
    """The operator, 2026-11-02: "forget codex now we both r available so
    that's enough". Claude Code reviews, the operator merges."""
    led = dw.DailyLedger(tmp_path / "ledger.db")
    alone = _proposal(led)
    assert (
        led.record_review(alone, "claude", model="opus", verdict="accept", reason="ok")
        == "accepted"
    )
    vetoed = _proposal(led)
    led.record_review(vetoed, "codex", model="gpt", verdict="reject", reason="no")
    assert (
        led.record_review(vetoed, "claude", model="opus", verdict="accept", reason="ok")
        == "rejected"
    )
    text = tool.report(led)
    assert "Codex: not yet reviewed" not in text, "Codex is no longer awaited"


def test_a_refused_proposal_is_never_reviewed_and_teaches_the_rule(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    refused = _proposal(led, passed=False)
    assert led.awaiting("codex") == [] and led.awaiting("claude") == []
    with pytest.raises(ValueError, match="not reviewable"):
        led.record_review(refused, "codex", model="gpt", verdict="accept", reason="x")
    rejected = _proposal(led)
    led.record_review(
        rejected, "codex", model="gpt", verdict="reject", reason="renames an export"
    )
    assert led.refusal_reasons(RULE) == [
        "codex: renames an export",
        "the proposal adds warnings: x +1",
    ]
    assert led.attempted(REL, RULE, dw.digest(BEFORE))
    assert not led.attempted(REL, RULE, dw.digest(AFTER))


def test_the_prompt_carries_the_rules_refusals_and_never_the_path() -> None:
    prompt = dw.proposal_prompt(
        FINDING, BEFORE, prior_refusals=["codex: renames an export"]
    )
    assert "Do not repeat them" in prompt and "codex: renames an export" in prompt
    assert BEFORE in prompt and "3:9" in prompt
    assert "File: Panel.jsx" in prompt and "workbench" not in prompt


def _redact(text: str) -> str:
    """A stand-in scrubber: paths and one 'secret'."""
    import re

    return re.sub(r"/[a-zA-Z]+/[a-zA-Z]+", "[PATH REDACTED]", text).replace(
        "s3cr3t-value", "[SENSITIVE: x]"
    )


def test_what_may_not_leave_is_masked_and_restored_exactly() -> None:
    text = (
        "import { a, b } from '../living/commands';\r\n"
        "const k = 's3cr3t-value';\r\n"
        "export const c = a;\r\n"
    )
    masked, mapping = dw.mask_lines(text, _redact)
    assert "living/commands" not in masked and "s3cr3t" not in masked
    assert masked.count("\r\n") == 3 and _redact(masked) == masked
    assert dw.unmask(masked, mapping, masked=masked) == text
    # The model removed the unused import name and kept the placeholder.
    answer = masked.replace("{ a, b }", "{ a }")
    assert dw.unmask(answer, mapping, masked=masked) == text.replace(
        "{ a, b }", "{ a }"
    )


def test_an_answer_may_not_invent_or_duplicate_a_placeholder() -> None:
    masked, mapping = dw.mask_lines("const k = 's3cr3t-value';\n", _redact)
    [token] = mapping
    assert dw.MASK_TOKEN.fullmatch(token)
    with pytest.raises(dw.ProposalRefused, match="invents"):
        dw.unmask(masked + token[:-4] + "0099\n", mapping, masked=masked)
    with pytest.raises(dw.ProposalRefused, match="duplicates"):
        dw.unmask(masked + token + "\n", mapping, masked=masked)


def test_a_placeholder_never_collides_with_text_already_in_the_file() -> None:
    """Codex's review of #566: a file already holding a placeholder-shaped
    literal had it restored as the private span."""
    text = "const tag = 'GAGOSMASK0000';\nconst k = 's3cr3t-value';\n"
    masked, mapping = dw.mask_lines(text, _redact)
    [token] = mapping
    assert token not in text and "GAGOSMASK0000" in masked
    assert dw.unmask(masked, mapping, masked=masked) == text
    # An unchanged answer restores exactly, the literal untouched.
    assert dw.unmask(masked, mapping, masked=masked).count("s3cr3t-value") == 1


def test_both_reviewers_read_the_same_whole_evidence() -> None:
    diff = dw.unified_diff(REL, BEFORE, AFTER)
    prompt = dw.review_prompt(FINDING, BEFORE, diff)
    assert BEFORE in prompt and diff in prompt and RULE in prompt
    assert dw.parse_review('{"verdict": "accept", "reason": " fine "}') == (
        "accept",
        "fine",
    )
    with pytest.raises(ValueError):
        dw.parse_review({"verdict": "maybe", "reason": "x"})


# --------------------------------------------------------------------- reviewers


def _fake_run(stdout="", stderr="", returncode=0, write=None, seen=None):
    def run(argv, **kwargs):
        if seen is not None:
            seen.append((argv, kwargs))
        if write is not None:
            Path(argv[argv.index("-o") + 1]).write_text(write, encoding="utf-8")
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    return run


def test_codex_reviews_read_only_and_its_model_is_recorded(monkeypatch) -> None:
    seen: list = []
    monkeypatch.setattr(tool, "_codex_executable", lambda: "codex")
    monkeypatch.setattr(
        tool,
        "codex_settings",
        lambda: {"model": "gpt-6.1-sol", "model_reasoning_effort": "xhigh"},
    )
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        _fake_run(
            stdout="model: gpt-6.1-sol\n",
            write='{"verdict":"accept","reason":"ok"}',
            seen=seen,
        ),
    )
    assert tool.run_codex("p", model=None, timeout_s=5) == (
        "accept",
        "ok",
        "gpt-6.1-sol",
    )
    argv, kwargs = seen[0]
    assert argv[:4] == ["codex", "exec", "-s", "read-only"]
    assert kwargs["input"] == "p"
    # His model, and nothing that lets the reviewer act (Codex's review of #566).
    assert argv[argv.index("-m") + 1] == "gpt-6.1-sol"
    assert "--ignore-user-config" in argv and "--ignore-rules" in argv
    disabled = {argv[i + 1] for i, a in enumerate(argv) if a == "--disable"}
    assert {"shell_tool", "unified_exec", "apps", "plugins", "browser_use"} <= disabled


def test_a_codex_failure_is_no_verdict(monkeypatch) -> None:
    monkeypatch.setattr(tool, "_codex_executable", lambda: "codex")
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        _fake_run(
            stderr="rmcp::transport noise\nERROR: model_not_found\n", returncode=1
        ),
    )
    with pytest.raises(tool.ReviewUnavailable, match="model_not_found"):
        tool.run_codex("p", model=None, timeout_s=5)


def test_claude_reviews_without_tools(monkeypatch) -> None:
    seen: list = []
    monkeypatch.setattr(tool, "_claude_executable", lambda: "claude.exe")
    payload = {
        "is_error": False,
        "structured_output": {"verdict": "reject", "reason": "no"},
        "modelUsage": {"claude-opus-5-5": {}},
    }
    monkeypatch.setattr(
        tool.subprocess, "run", _fake_run(stdout=json.dumps(payload), seen=seen)
    )
    assert tool.run_claude("p", model=None, timeout_s=5) == (
        "reject",
        "no",
        "claude-opus-5-5",
    )
    argv = seen[0][0]
    assert argv[argv.index("--tools") + 1] == "" and "--no-session-persistence" in argv


def test_a_reviewer_without_a_verdict_leaves_the_proposal_open(
    tmp_path, monkeypatch
) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    pid = _proposal(led)

    def down(prompt, *, model, timeout_s):
        raise tool.ReviewUnavailable("model refused")

    monkeypatch.setitem(tool.REVIEWER_RUNNERS, "codex", down)
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (True, ""))
    args = SimpleNamespace(reviewer="codex", limit=10, model=None, timeout=5)
    assert tool.cmd_review(args) == 1
    assert led.proposals()[0]["status"] == "proposed" and led.reviews(pid) == {}


def test_reviews_obey_the_egress_law(tmp_path, monkeypatch) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    _proposal(led)
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (False, "none"))
    monkeypatch.setitem(
        tool.REVIEWER_RUNNERS,
        "codex",
        lambda *a, **k: pytest.fail("nothing may be sent"),
    )
    args = SimpleNamespace(reviewer="codex", limit=10, model=None, timeout=5)
    assert tool.cmd_review(args) == 2


def test_a_reviewer_sees_the_file_under_the_same_mask(tmp_path, monkeypatch) -> None:
    """Codex's review of #566: reviews sent the unmasked file to two clouds."""
    led = dw.DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (True, ""))
    monkeypatch.setattr(tool, "egress_redact", _redact)
    monkeypatch.setattr(tool, "would_be_altered", lambda prompt, system: None)
    secret_before = "const k = 's3cr3t-value';\nconst unused = 1;\nexport default k;\n"
    secret_after = "const k = 's3cr3t-value';\nexport default k;\n"
    verdict = dw.StaticVerdict(True, "ok", 1)
    pid = led.record_proposal(
        FINDING,
        base_text=secret_before,
        base_commit="c" * 40,
        model="m",
        new_text=secret_after,
        verdict=verdict,
    )
    seen: list = []

    def runner(prompt, *, model, timeout_s):
        seen.append(prompt)
        return "accept", "fine", "m"

    monkeypatch.setitem(tool.REVIEWER_RUNNERS, "codex", runner)
    tool.cmd_review(SimpleNamespace(reviewer="codex", limit=10, model=None, timeout=5))
    [prompt] = seen
    assert "s3cr3t-value" not in prompt and "GAGOSMASK" in prompt
    assert "-const unused = 1;" in prompt
    assert led.reviews(pid)["codex"]["verdict"] == "accept"


# --------------------------------------------------------------------- propose


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "master")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    _git(path, "config", "core.autocrlf", "false")
    (path / REL).parent.mkdir(parents=True)
    (path / REL).write_bytes(BEFORE.encode())
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


def test_propose_obeys_the_egress_law(tmp_path, monkeypatch, capsys) -> None:
    root = _repo(tmp_path / "project")
    monkeypatch.setattr(tool, "ledger", lambda: dw.DailyLedger(tmp_path / "l.db"))
    monkeypatch.setattr(
        tool,
        "check_texts",
        lambda r, texts, **kw: {k: _result(_warn(RULE)) for k in texts},
    )
    monkeypatch.setattr(
        tool, "cloud_coding_allowed", lambda: (False, "cloud tasks in force []")
    )
    monkeypatch.setattr(
        tool, "governed_completer", lambda *a: pytest.fail("no model may be asked")
    )
    args = SimpleNamespace(
        project=str(root), budget=2, model="m", region="r", rules=None, dry_run=False
    )
    assert tool.cmd_propose(args) == 2
    assert "egress law" in capsys.readouterr().out


def test_propose_records_a_checked_proposal_and_never_repeats_it(
    tmp_path, monkeypatch
) -> None:
    root = _repo(tmp_path / "project")
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(
        tool,
        "check_texts",
        lambda r, texts, **kw: {
            k: _result() if v == AFTER else _result(_warn(RULE))
            for k, v in texts.items()
        },
    )
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (True, ""))
    asked: list = []

    def completer(model, region):
        def complete(prompt, system, request_id):
            asked.append(prompt)
            return f"```jsx\n{AFTER}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    args = SimpleNamespace(
        project=str(root), budget=2, model="m", region="r", rules=[RULE], dry_run=False
    )
    assert tool.cmd_propose(args) == 0
    [p] = led.proposals()
    assert (
        p["status"] == "proposed"
        and p["new_text"] == AFTER
        and p["base_text"] == BEFORE
    )
    assert tool.cmd_propose(args) == 0 and len(asked) == 1, (
        "the same file is never asked twice"
    )


def test_a_refused_writer_never_takes_the_only_finding_from_one_that_answers(
    tmp_path, monkeypatch
) -> None:
    """2026-11-09: one finding was left, and each hour it went to the refused
    Bedrock writer being tried again, while the plans' writers stood idle."""
    from aios.core import bedrock

    root = _repo(tmp_path / "project")
    led = dw.DailyLedger(tmp_path / "l.db")
    refused = tool.BEDROCK_WRITERS[0]
    monkeypatch.setattr(led, "refused_writers", lambda models: [refused])
    monkeypatch.setattr(led, "resting_writers", lambda models: [])
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(bedrock, "credentials_available", lambda region: True)
    monkeypatch.setattr(
        tool,
        "check_texts",
        lambda r, texts, **kw: {
            k: _result() if v == AFTER else _result(_warn(RULE))
            for k, v in texts.items()
        },
    )
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (True, ""))
    asked: list[str] = []

    def completer(model, region):
        def complete(prompt, system, request_id):
            asked.append(model)
            return f"```jsx\n{AFTER}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    args = SimpleNamespace(
        project=str(root), budget=2, model=None, region="r", rules=[RULE], dry_run=False
    )
    assert tool.cmd_propose(args) == 0
    assert len(asked) == 1 and asked[0] != refused, asked
    assert asked[0] in tool.WORKFORCE


# --------------------------------------------------------------------- deliver


@pytest.fixture()
def origin_and_worktree(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "master", str(origin)], check=True
    )
    seed = _repo(tmp_path / "seed")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "master")
    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", "-q", "-c", "core.autocrlf=false", str(origin), str(work)],
        check=True,
    )
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    _git(work, "config", "core.autocrlf", "false")
    return seed, work


def _accepted(led):
    pid = _proposal(led)
    led.record_review(
        pid,
        "codex",
        model="gpt",
        verdict="accept",
        reason="removes only the unused const",
    )
    led.record_review(
        pid, "claude", model="opus", verdict="accept", reason="behaviour unchanged"
    )
    return pid


def _deliver_args(work, **kw):
    return SimpleNamespace(
        worktree=str(work),
        branch="gagos/daily-test",
        check_timeout=60,
        open_pr=False,
        pr_footer="",
        **kw,
    )


def test_deliver_commits_each_accepted_change_with_both_reviews(
    tmp_path, monkeypatch, origin_and_worktree
) -> None:
    _seed, work = origin_and_worktree
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    checked: list = []
    monkeypatch.setattr(
        smoke, "frontend_smoke", lambda root, paths, **kw: checked.append(paths) or None
    )
    pid = _accepted(led)
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert (work / REL).read_text(encoding="utf-8") == AFTER
    message = _git(work, "log", "-1", "--format=%B")
    assert (
        "removes only the unused const" in message and "behaviour unchanged" in message
    )
    # Committed, not delivered: no PR was opened (Codex's review of #566).
    assert led.proposals()[0]["status"] == "committed" and checked
    assert led.pending_publication() == {"gagos/daily-test": [pid]}
    assert _git(work, "rev-parse", "--abbrev-ref", "HEAD") == "gagos/daily-test"
    assert pid in message
    # GAGOS's own work: authored and committed by GAGOS; its reviewers are
    # named as reviewers, the chief first, and never as authors.
    assert (
        _git(work, "log", "-1", "--format=%an <%ae>|%cn")
        == "GAGOS <gagos@localhost>|GAGOS"
    )
    assert (
        "Proposed-by: GAGOS" in message
        and "Co-authored-by: m <m@models.invalid>" in message
    )
    assert "Reviewed-by: Claude Code, chief reviewer, opus" in message
    assert "Reviewed-by: Codex, gpt" in message
    assert [
        line
        for line in message.splitlines()
        if line.lower().startswith("co-authored-by")
    ] == ["Co-authored-by: m <m@models.invalid>"], (
        "the model that wrote it is credited; no reviewer is an author"
    )


def test_a_gagos_pr_says_who_opened_it() -> None:
    assert "no GitHub identity of its own" in tool.PR_FOOTER
    assert "accepted by its reviewer, Claude Code" in tool.PR_FOOTER
    assert "The operator merges" in tool.PR_FOOTER


def test_deliver_never_applies_to_a_file_that_changed(
    tmp_path, monkeypatch, origin_and_worktree
) -> None:
    seed, work = origin_and_worktree
    (seed / REL).write_text(BEFORE + "// changed on master\n", encoding="utf-8")
    _git(seed, "commit", "-qam", "master moved")
    _git(seed, "push", "-q", "origin", "master")
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    _accepted(led)
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert led.proposals()[0]["status"] == "stale"
    assert "changed on master" in (work / REL).read_text(encoding="utf-8")


def test_a_change_that_fails_its_checks_on_master_is_not_delivered(
    tmp_path, monkeypatch, origin_and_worktree
) -> None:
    _seed, work = origin_and_worktree
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    # The check fails with the change and passes without it: the change's doing.
    monkeypatch.setattr(
        smoke,
        "frontend_smoke",
        lambda root, paths, **k: (
            "the tests related to the frontend targets did not pass"
            if paths[0].read_text(encoding="utf-8") == AFTER
            else None
        ),
    )
    _accepted(led)
    head = _git(work, "rev-parse", "HEAD")
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert led.proposals()[0]["status"] == "failed"
    assert (work / REL).read_text(encoding="utf-8") == BEFORE
    assert _git(work, "rev-parse", "HEAD") == head and not _git(
        work, "status", "--porcelain"
    )


def test_a_check_that_fails_on_master_without_the_change_too_is_not_its_doing(
    tmp_path, monkeypatch, origin_and_worktree
) -> None:
    """2026-11-02: gd-8b79700958 (an unused React import) was failed at
    delivery by a test that times out on this laptop with or without it."""
    _seed, work = origin_and_worktree
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    seen: list[str] = []

    def both(root, paths, **k):
        seen.append(paths[0].read_text(encoding="utf-8"))
        return "the tests related to the frontend targets did not pass"

    monkeypatch.setattr(smoke, "frontend_smoke", both)
    _accepted(led)
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert seen == [AFTER, BEFORE], "checked with the change, then without it"
    assert led.proposals()[0]["status"] == "committed"
    assert (work / REL).read_text(encoding="utf-8") == AFTER
    message = _git(work, "log", "-1", "--format=%B")
    assert "fails on master without it too" in message and "CI judges it" in message
    assert "the tests that import it pass" not in message


# --------------------------------------------------------------------- the real toolchain


def test_the_real_toolchain_lints_and_parses_text_without_running_it(tmp_path) -> None:
    from aios import config
    from aios.maintenance.frontend_static import check_texts

    repo = Path(config.PROJECT_ROOT)
    if (
        shutil.which("node") is None
        or not (repo / "frontend/node_modules/eslint").is_dir()
    ):
        pytest.skip("no node or no frontend toolchain here")
    results = check_texts(
        repo,
        {
            REL: BEFORE,
            "frontend/src/workbench/Broken.jsx": "export function (\n",
            "frontend/src/workbench/Boom.jsx": "process.exit(7);\nthrow new Error('ran');\n",
        },
    )
    assert [m.rule for m in results[REL].warnings()] == [RULE]
    assert results["frontend/src/workbench/Broken.jsx"].parse_errors
    assert results["frontend/src/workbench/Boom.jsx"].errors == [], (
        "linted, never executed"
    )


def test_an_ordinary_change_can_be_shown_to_the_reviewers() -> None:
    """With the REAL scrubbers: the evidence names the file, never its path,
    so an ordinary change passes GAGOS's own egress check unaltered (the first
    version put the path in the prompt and the diff, and the privacy filter
    would have refused every review)."""
    verdict = dw.StaticVerdict(True, "ok", 1)
    p = {
        "base_text": BEFORE,
        "new_text": AFTER,
        "facts": "[]",
    }
    prompt = tool.review_evidence(p, FINDING)
    assert "Panel.jsx" in prompt and "frontend/src/workbench" not in prompt
    assert tool.would_be_altered(prompt, "") is None
    assert verdict.passed


# --------------------------------------------------------------------- completion


def _measured_repo(tmp_path: Path) -> Path:
    """A project with one untested module, a Python test and a frontend test
    that can skip, and an organ ledger of one green organ in two."""
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "core.autocrlf", "false")
    files = {
        REL: BEFORE,
        "frontend/src/workbench/Other.test.jsx": "it.skip('later', () => {});\n",
        "tests/test_slow.py": "import pytest\n\n\n@pytest.mark.skip(reason='x')\ndef test_x():\n    pass\n",
        "tests/test_fine.py": "def test_y():\n    assert True\n",
        ".aios/state/ORGAN_GREEN_LEDGER.json": json.dumps(
            [{"status": "green"}, {"status": "yellow"}]
        ),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(text.encode())
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def test_each_batch_measures_how_complete_gagos_is_before_any_model(
    tmp_path, monkeypatch
) -> None:
    """The completion scoreboard (2026-11-10): measured on master before the
    egress law is asked, so an hour the cloud is refused is measured too."""
    root = _measured_repo(tmp_path)
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(
        tool,
        "check_texts",
        lambda r, texts, **kw: {
            k: _result(_warn(RULE), _warn("react-hooks/exhaustive-deps", line=4))
            if k == REL
            else _result()
            for k in texts
        },
    )
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (False, "no cloud"))
    monkeypatch.setattr(
        tool, "governed_completer", lambda *a: pytest.fail("no model may be asked")
    )
    args = SimpleNamespace(
        project=str(root), budget=2, model="m", region="r", rules=[RULE], dry_run=True
    )
    assert tool.cmd_propose(args) == 0
    assert led.measures() == [], "a dry run records nothing"
    args.dry_run = False
    assert tool.cmd_propose(args) == 2
    [row] = led.measures()
    assert row["head"] == _git(root, "rev-parse", "HEAD")
    assert row["values"] == {
        "warnings": 2,
        "in_reach": 1,
        "waiting": 1,
        "untested": 1,
        "can_skip": 2,
        "organs_green": 1,
        "organs": 2,
        "python": 0,
    }
    assert tool.cmd_propose(args) == 2 and len(led.measures()) == 1, (
        "one measure an hour: a second run in the same hour replaces it"
    )


def test_an_organ_count_is_never_guessed(tmp_path) -> None:
    assert tool.organ_counts(tmp_path) is None
    state = tmp_path / ".aios" / "state"
    state.mkdir(parents=True)
    (state / "ORGAN_GREEN_LEDGER.json").write_text("{broken", encoding="utf-8")
    assert tool.organ_counts(tmp_path) is None
    measured = tool.completion_measures(
        tmp_path, {}, tool.Counter(), (RULE,), python_checked=True
    )
    assert "organs" not in measured and "organs_green" not in measured


def test_the_scoreboard_shows_the_latest_against_the_first_hour(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    assert tool.score_lines(led.measures()) == [
        "- not measured yet: GAGOS's next hourly batch records the first"
    ]
    base = {"warnings": 70, "in_reach": 40, "waiting": 30, "untested": 20}
    led.record_measures(
        "2026-11-10T04",
        "a" * 40,
        {**base, "organs_green": 51, "organs": 59, "python": 1},
    )
    led.record_measures(
        "2026-11-10T05",
        "b" * 40,
        {**base, "warnings": 69, "organs_green": 51, "organs": 59, "python": 1},
    )
    led.record_measures(
        "2026-11-10T06",
        "c" * 40,
        {
            **base,
            "warnings": 60,
            "untested": 22,
            "organs_green": 52,
            "organs": 59,
            "python": 0,
        },
    )
    lines = tool.score_lines(led.measures())
    text = "\n".join(lines)
    assert "measured 3 time(s): first 2026-11-10T04 at `aaaaaaaaaaaa`" in lines[0]
    assert (
        "warnings the checks find in GAGOS's editable files: 60 (first 70, -10, better); the hour before: 69"
        in text
    )
    assert "frontend modules with no test beside them: 22 (first 20, +2, worse)" in text
    assert "organs green in the organ ledger: 52 (first 51, +1, better)" in text
    assert "organs in the organ ledger: 59 (first 59, +0)" in text
    assert (
        "test files with a skip in them (a skip may be conditional): not measured"
        in text
    )
    assert "the Python checks did not run in the latest hour" in text
    assert "**Completion**" in tool.report(led) and lines[1] in tool.report(led)


def test_the_score_command_prints_the_scoreboard(tmp_path, monkeypatch, capsys) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    led.record_measures("2026-11-10T04", "a" * 40, {"warnings": 3, "python": 1})
    monkeypatch.setattr(tool, "ledger", lambda: led)
    assert tool.main(["score"]) == 0
    out = capsys.readouterr().out
    assert (
        "GAGOS's completion" in out
        and "warnings the checks find in GAGOS's editable files: 3" in out
    )


# --------------------------------------------------------------------- claims and the Foundry


def test_files_are_claimed_all_or_none_and_a_dead_batchs_claim_lapses(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    assert led.claim_files(["a.jsx", "b.jsx"], "batch:1")
    assert led.claim_files(["a.jsx"], "batch:1"), (
        "a holder may claim again what it holds"
    )
    assert not led.claim_files(["b.jsx", "c.jsx"], "batch:2"), (
        "one held file refuses all"
    )
    assert led.claimed_files() == {"a.jsx", "b.jsx"}, "c.jsx was not claimed either"
    assert led.release_claims("batch:1") == 2 and led.claimed_files() == set()
    assert led.claim_files(["b.jsx", "c.jsx"], "batch:2")
    import sqlite3

    with sqlite3.connect(tmp_path / "l.db") as db:
        db.execute("UPDATE claims SET claimed_at = '2000-01-01T00:00:00+00:00'")
    assert led.claimed_files() == set(), "a claim older than a batch can live lapses"
    assert led.claim_files(["c.jsx"], "batch:3")


def test_two_ledgers_racing_for_a_file_never_both_win(tmp_path) -> None:
    """Atomic across processes: two ledgers on one file, as two batches would be."""
    import threading

    wins: list[str] = []
    start = threading.Barrier(8)

    def race(holder: str) -> None:
        led = dw.DailyLedger(tmp_path / "l.db")
        start.wait()
        if led.claim_files(["a.jsx"], holder):
            wins.append(holder)

    dw.DailyLedger(tmp_path / "l.db")
    threads = [threading.Thread(target=race, args=(f"b{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(wins) == 1


def _propose_setup(tmp_path, monkeypatch, asked):
    root = _repo(tmp_path / "project")
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(
        tool,
        "check_texts",
        lambda r, texts, **kw: {
            k: _result() if v == AFTER else _result(_warn(RULE))
            for k, v in texts.items()
        },
    )
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (True, ""))

    def completer(model, region):
        def complete(prompt, system, request_id):
            asked.append(model)
            return f"```jsx\n{AFTER}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    args = SimpleNamespace(
        project=str(root), budget=2, model="m", region="r", rules=[RULE], dry_run=False
    )
    return led, args


class _Stop:
    def __init__(self, error=None) -> None:
        self.error = error

    def assert_operational(self) -> None:
        if self.error is not None:
            raise self.error


class _Bus:
    def __init__(self) -> None:
        self.events: list = []

    def append(self, event) -> None:
        self.events.append(event)


def test_a_batchs_writers_are_workers_the_foundry_admits(tmp_path, monkeypatch) -> None:
    from aios.application.workers.workshop_foundry import WorkshopFoundry

    asked: list[str] = []
    led, args = _propose_setup(tmp_path, monkeypatch, asked)
    bus = _Bus()
    monkeypatch.setattr(
        tool,
        "writers_foundry",
        lambda: WorkshopFoundry(emergency_stop=_Stop(), bus=bus, writers_at_once=2),
    )
    assert tool.cmd_propose(args) == 0
    assert asked == ["m"] and len(led.proposals()) == 1
    kinds = [e.event_type for e in bus.events]
    assert kinds[0] == "worker.requested" and kinds[-1] == "worker.dissolved"
    assert "worker.completed" in kinds
    assert {e.payload["scope"]["files"][0] for e in bus.events} == {REL}
    assert led.claimed_files() == set(), "the batch releases its claims"


def test_an_engaged_emergency_stop_asks_no_writer(
    tmp_path, monkeypatch, capsys
) -> None:
    from aios.application.governance.emergency_stop import EmergencyStopError
    from aios.application.workers.workshop_foundry import WorkshopFoundry

    asked: list[str] = []
    led, args = _propose_setup(tmp_path, monkeypatch, asked)
    stop = _Stop(
        EmergencyStopError("emergency stop is engaged; side effects are disabled")
    )
    monkeypatch.setattr(
        tool, "writers_foundry", lambda: WorkshopFoundry(emergency_stop=stop)
    )
    assert tool.cmd_propose(args) == 0
    assert asked == [] and led.proposals() == [], "the finding stays for a later hour"
    assert "not admitted: emergency stop is engaged" in capsys.readouterr().out
    assert led.claimed_files() == set()


def test_a_file_another_batch_claimed_is_left_alone(
    tmp_path, monkeypatch, capsys
) -> None:
    asked: list[str] = []
    led, args = _propose_setup(tmp_path, monkeypatch, asked)
    assert led.claim_files([REL], "batch:another")
    assert tool.cmd_propose(args) == 0
    assert asked == [] and led.proposals() == []
    assert led.claimed_files() == {REL}, "another batch's claim is not ours to release"
    led.release_claims("batch:another")
    assert tool.cmd_propose(args) == 0 and asked == ["m"]


def test_a_claimed_file_is_in_flight(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    assert led.claim_files([REL], "batch:another")
    assert REL in tool.in_flight(led, [])


def test_a_writers_spend_is_settled_from_the_tokens_its_provider_reported(
    tmp_path, monkeypatch
) -> None:
    """2026-11-10: the workshop's own ceiling settles each call from the tokens
    the provider reported (cloud_spend), not from its character estimate."""
    from aios.core import cloud_spend

    asked: list[str] = []
    led, args = _propose_setup(tmp_path, monkeypatch, asked)

    def completer(model, region):
        def complete(prompt, system, request_id):
            cloud_spend.record_usage("bedrock", model, 1_000_000, 0)  # $1.00
            return f"```jsx\n{AFTER}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    assert tool.cmd_propose(args) == 0
    assert led.month_spend(tool._month()) == {"m": pytest.approx(1.0)}


# --------------------------------------------------------------------- D15: a playbook per rule


def _decided(led, rel, *, outcome, rule=RULE, arm=None, seen=(), active=0, model="m"):
    finding = dw.Finding(rel=rel, rule=rule, warnings=((3, 9, "x"),))
    pid = led.record_proposal(
        finding,
        base_text=BEFORE + rel,
        base_commit="c" * 40,
        model=model,
        new_text=AFTER,
        verdict=dw.StaticVerdict(True, "ok", 1),
        arm=arm,
        playbook_seen=seen,
        playbook_active=active,
    )
    led.record_review(
        pid,
        "claude",
        model="opus",
        verdict="accept" if outcome else "reject",
        reason="keeps behaviour" if outcome else "drops a used name",
    )
    led.resettle()
    return pid


def test_a_findings_arm_is_fixed_and_the_arms_are_balanced() -> None:
    arms = [dw.d15_arm(f"src/f{i}.js", RULE, "d" * 8) for i in range(2000)]
    assert 0.45 < arms.count(dw.ARM_ON) / len(arms) < 0.55
    assert dw.d15_arm("a.js", RULE, "x") == dw.d15_arm("a.js", RULE, "x"), (
        "a retry keeps its arm"
    )


def test_a_finding_never_accepted_may_be_tried_again_a_day_later(tmp_path) -> None:
    import sqlite3
    from datetime import datetime, timedelta, timezone

    led = dw.DailyLedger(tmp_path / "l.db")
    base = dw.digest(BEFORE)
    assert led.may_attempt(REL, RULE, base), "never attempted"
    _proposal(led, passed=False)  # refused by the checks
    assert not led.may_attempt(REL, RULE, base), "not within a day"

    def age(hours):
        when = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(tmp_path / "l.db") as db:
            db.execute("UPDATE proposals SET created_at = ?", (when,))

    age(25)
    assert led.may_attempt(REL, RULE, base), "never accepted, a day later"
    _proposal(led, passed=False)
    _proposal(led, passed=False)
    age(25)
    assert not led.may_attempt(REL, RULE, base), f"at most {dw.MAX_ATTEMPTS} attempts"


def test_an_awaiting_finding_is_not_tried_again(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    _proposal(led)  # proposed, awaiting review
    assert not led.may_attempt(REL, RULE, dw.digest(BEFORE))


def test_the_curator_keeps_only_general_new_entries_and_rewrites_none(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    first = "Remove only the unused binding; keep every side effect of its initializer."
    added, dropped = led.add_playbook_entries(
        RULE,
        [
            ("strategy", first),
            ("pitfall", "Do not touch frontend/src/x.js"),
            ("advice", "Something"),
        ],
        sources=["gd-1"],
    )
    assert len(added) == 1 and len(dropped) == 2
    again, dropped = led.add_playbook_entries(
        RULE,
        [("strategy", first.replace(";", ","))],
        sources=["gd-2"],
    )
    assert again == [] and "repeats" in dropped[0]
    for i in range(dw.PLAYBOOK_MAX_ACTIVE + 2):
        led.add_playbook_entries(
            RULE,
            [("pitfall", f"Distinct pitfall number {i} {'z' * (i + 1)}")],
            sources=[],
        )
    assert len(led.playbook(RULE)) == dw.PLAYBOOK_MAX_ACTIVE
    oldest = led.playbook(RULE, active_only=False)[0]
    assert oldest["text"] == first, "never rewritten"


def test_credit_goes_to_the_entries_shown_once_and_a_harmful_entry_retires(
    tmp_path,
) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    [eid], _ = led.add_playbook_entries(
        RULE, [("strategy", "Keep the diff to the warned lines.")], sources=[]
    )
    _decided(led, "a.js", outcome=1, arm=dw.ARM_ON, seen=[eid], active=1)
    _decided(led, "b.js", outcome=0, arm=dw.ARM_OFF, seen=[], active=1)
    assert led.settle_playbook_credit() == 1 and led.settle_playbook_credit() == 0
    [entry] = led.playbook(RULE)
    assert (entry["helpful"], entry["harmful"]) == (1, 0), (
        "OFF proposals credit nothing"
    )
    for i in range(4):
        _decided(led, f"c{i}.js", outcome=0, arm=dw.ARM_ON, seen=[eid], active=1)
    led.settle_playbook_credit()
    [entry] = led.playbook(RULE, active_only=False)
    assert entry["status"] == "retired" and entry["harmful"] == 4


def test_a_reflection_reads_reasons_not_code_and_keeps_what_the_curator_allows(
    tmp_path,
) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    _decided(led, "a.js", outcome=1)
    _decided(led, "b.js", outcome=0)
    assert led.rules_awaiting_reflection() == [RULE]
    seen = {}

    def complete(prompt, system, request_id):
        seen["prompt"] = prompt
        return json.dumps(
            {
                "add": [
                    {
                        "kind": "pitfall",
                        "text": "Never remove a name another statement still reads.",
                    },
                    {"kind": "strategy", "text": "Edit src/a.js only"},
                ],
                "retire": ["pb-unknown"],
            }
        )

    summary = tool.reflect(led, RULE, complete)
    assert "1 added" in summary and "1 not kept" in summary
    assert "drops a used name" in seen["prompt"] and "keeps behaviour" in seen["prompt"]
    assert AFTER not in seen["prompt"], "no code reaches the reflector"
    assert led.rules_awaiting_reflection() == [], "marked reflected"
    _decided(led, "c.js", outcome=0)
    assert led.rules_awaiting_reflection() == [RULE], "a new verdict waits again"


def test_a_failed_reflection_changes_nothing_and_is_tried_again(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    _decided(led, "a.js", outcome=1)

    def broken(prompt, system, request_id):
        raise RuntimeError("usage limit")

    assert "tried next batch" in tool.reflect(led, RULE, broken)
    assert led.playbook(RULE) == [] and led.rules_awaiting_reflection() == [RULE]
    assert "no entry could be read" in tool.reflect(led, RULE, lambda *a: "sorry")
    assert led.rules_awaiting_reflection() == [RULE], (
        "D16: an answer with nothing readable is tried next batch, like a failed call"
    )


def test_only_the_on_arms_writer_is_shown_the_playbook(tmp_path, monkeypatch) -> None:
    asked: list[str] = []
    led, args = _propose_setup(tmp_path, monkeypatch, asked)
    [eid], _ = led.add_playbook_entries(
        RULE, [("strategy", "Keep the diff to the warned lines.")], sources=[]
    )
    prompts: list[str] = []

    def completer(model, region):
        def complete(prompt, system, request_id):
            prompts.append(prompt)
            return f"```jsx\n{AFTER}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    assert tool.cmd_propose(args) == 0
    [p] = led.proposals()
    arm = dw.d15_arm(REL, RULE, dw.digest(BEFORE))
    assert p["arm"] == arm and p["playbook_active"] == 1
    shown = "Keep the diff to the warned lines." in prompts[0]
    assert shown is (arm == dw.ARM_ON)
    assert json.loads(p["playbook_seen"]) == ([eid] if arm == dw.ARM_ON else [])


def test_the_analysis_is_the_pre_registered_one(tmp_path) -> None:
    rows = [
        {
            "arm": dw.ARM_ON,
            "outcome": 1,
            "rel": f"a{i}",
            "rule": RULE,
            "base_digest": "x",
        }
        for i in range(30)
    ] + [
        {
            "arm": dw.ARM_OFF,
            "outcome": int(i < 10),
            "rel": f"b{i}",
            "rule": RULE,
            "base_digest": "x",
        }
        for i in range(30)
    ]
    result = tool.d15_analysis(rows)
    assert result["on"] == {"n": 30, "accepted": 30, "rate": 1.0}
    assert result["off"]["accepted"] == 10
    assert result["H1"]["met"] and result["H1c"]["met"]
    assert not result["harm"]["seen"]
    led = dw.DailyLedger(tmp_path / "l.db")
    _decided(led, "a.js", outcome=1, arm=dw.ARM_ON, active=1)
    _decided(led, "b.js", outcome=0, arm=dw.ARM_OFF, active=0)  # nothing withheld: out
    assert tool.d15_counts(led) == {dw.ARM_ON: 1, dw.ARM_OFF: 0}
    text = tool.report(led)
    assert "**D15**" in text and "ON 1, OFF 0" in text


def test_the_off_arms_writer_is_not_shown_the_playbook(tmp_path, monkeypatch) -> None:
    asked: list[str] = []
    led, args = _propose_setup(tmp_path, monkeypatch, asked)
    led.add_playbook_entries(
        RULE, [("strategy", "Keep the diff to the warned lines.")], sources=[]
    )
    monkeypatch.setattr(tool, "d15_arm", lambda *a: dw.ARM_OFF)
    prompts: list[str] = []

    def completer(model, region):
        def complete(prompt, system, request_id):
            prompts.append(prompt)
            return f"```jsx\n{AFTER}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    assert tool.cmd_propose(args) == 0
    [p] = led.proposals()
    assert p["arm"] == dw.ARM_OFF and p["playbook_active"] == 1
    assert "Keep the diff" not in prompts[0] and json.loads(p["playbook_seen"]) == []


# --------------------------------------------------------------------- D16


#: The reflector's answer for E402 at the first seed, 2026-11-11 03:2x UTC: a
#: stray `","` after the first entry made it invalid JSON (7 of 9 answers).
MALFORMED = (
    '{"add":[{"kind":"strategy","text":"Fix E402 by actually moving the module-level '
    'imports to the top of the file.","},{"kind":"pitfall","text":"Never wrap late '
    'imports in a dead conditional such as `if True:` to hide E402."},{"kind":"pitfall",'
    '"text":"Don\'t move imports above a path bootstrap that they rely on."}],"retire":[]}'
)


def test_a_malformed_answer_is_read_entry_by_entry() -> None:
    adds, retires = dw.parse_reflection(MALFORMED)
    assert [k for k, _ in adds] == ["strategy", "pitfall", "pitfall"]
    assert adds[0][1].startswith("Fix E402 by actually moving")
    assert adds[1][1].endswith("to hide E402.") and retires == []
    adds, retires = dw.parse_reflection(
        '{"add":[{"kind":"pitfall","text":"one"}],"retire":["pb-0a1b2c3d"],}'
    )
    assert adds == [("pitfall", "one")] and retires == ["pb-0a1b2c3d"]


def test_each_reflection_has_its_own_request_id(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    _decided(led, "a.js", outcome=1)
    ids: list[str] = []

    def complete(prompt, system, request_id):
        ids.append(request_id)
        return "sorry"

    tool.reflect(led, RULE, complete)
    tool.reflect(led, RULE, complete)
    assert len(set(ids)) == 2, "the gateway refuses a request id twice"


def test_a_finding_waits_until_its_rule_has_been_reflected_on(
    tmp_path, monkeypatch
) -> None:
    asked: list[str] = []
    led, args = _propose_setup(tmp_path, monkeypatch, asked)
    _decided(led, "other.js", outcome=0)  # the rule has a verdict, no reflection
    assert led.awaits_first_reflection(RULE)
    assert tool.cmd_propose(args) == 0
    assert asked == [], "no attempt is spent before the rule's playbook exists"
    led.mark_reflected(RULE)
    assert not led.awaits_first_reflection(RULE)
    assert tool.cmd_propose(args) == 0 and asked == ["m"]


def test_a_rule_with_no_verdict_does_not_wait(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    assert not led.awaits_first_reflection(RULE), "nothing to reflect on: no wait"
