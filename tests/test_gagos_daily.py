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


def _result(*messages, parse=()):
    return StaticResult(messages=tuple(messages), parse_errors=tuple(parse))


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
        (AFTER + "// eslint-disable-next-line\n", _result(), "disable comment"),
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
    assert "reviewers disagreed: 1" in text


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
    with pytest.raises(dw.ProposalRefused, match="invents"):
        dw.unmask(masked + "GAGOSMASK0099\n", mapping, masked=masked)
    with pytest.raises(dw.ProposalRefused, match="duplicates"):
        dw.unmask(masked + token + "\n", mapping, masked=masked)


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
    monkeypatch.setattr(tool.shutil, "which", lambda name: "codex")
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
    assert argv[:4] == ["codex", "exec", "-s", "read-only"] and "-m" not in argv
    assert kwargs["input"] == "p"


def test_a_codex_failure_is_no_verdict(monkeypatch) -> None:
    monkeypatch.setattr(tool.shutil, "which", lambda name: "codex")
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
    args = SimpleNamespace(reviewer="codex", limit=10, model=None, timeout=5)
    assert tool.cmd_review(args) == 1
    assert led.proposals()[0]["status"] == "proposed" and led.reviews(pid) == {}


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
        tool, "check_texts", lambda r, texts: {k: _result(_warn(RULE)) for k in texts}
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
        lambda r, texts: {
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
        project=str(root), budget=2, model="m", region="r", rules=None, dry_run=False
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
    assert led.proposals()[0]["status"] == "delivered" and checked
    assert _git(work, "rev-parse", "--abbrev-ref", "HEAD") == "gagos/daily-test"
    assert pid in message
    # GAGOS's own work: authored and committed by GAGOS; its reviewers are
    # named as reviewers, the chief first, and never as authors.
    assert (
        _git(work, "log", "-1", "--format=%an <%ae>|%cn")
        == "GAGOS <gagos@localhost>|GAGOS"
    )
    assert "Proposed-by: GAGOS (m)" in message
    assert "Reviewed-by: Claude Code, chief reviewer (opus)" in message
    assert "Reviewed-by: Codex (gpt)" in message
    assert "Co-Authored-By" not in message


def test_a_gagos_pr_says_who_opened_it() -> None:
    assert "no GitHub identity of its own" in tool.PR_FOOTER
    assert "chief" in tool.PR_FOOTER and "both accept" in tool.PR_FOOTER


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

    monkeypatch.setattr(
        smoke,
        "frontend_smoke",
        lambda *a, **k: "the tests related to the frontend targets did not pass",
    )
    _accepted(led)
    head = _git(work, "rev-parse", "HEAD")
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert led.proposals()[0]["status"] == "failed"
    assert (work / REL).read_text(encoding="utf-8") == BEFORE
    assert _git(work, "rev-parse", "HEAD") == head and not _git(
        work, "status", "--porcelain"
    )


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
