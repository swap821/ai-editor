"""GAGOS's workforce (the operator, 2026-11-02): several Bedrock models write at
once, within his monthly AWS ceiling, and more work goes to the writers whose
work both reviewers accept. Pinned here, without a model or a network:

* every writer still being tried gets work first; after that, work follows the
  accepted record, and the allocation is whole and deterministic;
* each call holds its worst case against the month's total first, atomically
  across threads, and no call is made past the ceiling; a finding not asked
  for stays unattempted;
* a batch spreads its findings across the writers, records each proposal
  under the writer that wrote it, and settles every hold;
* a writer's record counts what it wrote, not a failed call nor a file no
  model was asked about;
* a writer whose last call was refused (AWS refused the account on 2026-11-02)
  is tried on one finding a batch until it answers, and the rest of the work
  goes to writers that answer;
* the Claude writers (Sonnet and Haiku, through Claude Code on the operator's
  plan, 2026-11-03) take at most their share of a batch, cost nothing against
  the AWS ceiling, and run with no tools, no session and only the text.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import threading
from types import SimpleNamespace

import pytest

from aios.maintenance import daily_work as dw
from tests.test_gagos_daily import (
    AFTER,
    BEFORE,
    FINDING,
    REL,
    RULE,
    _git,
    _repo,
    _result,
    _warn,
)
from tests.test_gagos_identity_and_day import _both
from tools import gagos_daily as tool

OTHER = "frontend/src/workbench/Other.jsx"
THIRD = "frontend/src/workbench/Third.jsx"


def test_writers_being_tried_get_work_first() -> None:
    roster = ("a", "b", "c")
    assert tool.allocate(2, {}, roster) == ["a", "b"]
    picks = tool.allocate(7, {}, roster)
    assert sorted(picks) == ["a", "a", "a", "b", "b", "c", "c"]
    assert tool.allocate(0, {}, roster) == []


def test_work_follows_the_accepted_record() -> None:
    roster = ("good", "poor")
    outcomes = {"good": (9, 10), "poor": (1, 10)}
    picks = tool.allocate(10, outcomes, roster)
    assert len(picks) == 10
    assert picks.count("good") > picks.count("poor") > 0, (
        "the better record gets more; the other still gets some"
    )
    assert tool.allocate(10, outcomes, roster) == picks, "deterministic"


def test_no_call_past_the_months_ceiling(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    hold = led.reserve_spend(
        month="2026-11", model="a", purpose="p", usd=0.6, ceiling=1.0
    )
    assert hold is not None
    assert (
        led.reserve_spend(month="2026-11", model="a", purpose="p", usd=0.6, ceiling=1.0)
        is None
    ), "the worst case is held until the call settles"
    led.settle_spend(hold, usd=0.1, chars_in=10, chars_out=10)
    assert led.reserve_spend(
        month="2026-11", model="b", purpose="p", usd=0.6, ceiling=1.0
    )
    assert led.reserve_spend(
        month="2026-12", model="a", purpose="p", usd=0.9, ceiling=1.0
    ), "a new month starts from nothing"
    assert led.month_spend("2026-11") == {"a": 0.1, "b": 0.6}


def test_the_ceiling_holds_across_threads(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    held: list = []

    def take() -> None:
        for _ in range(5):
            hold = led.reserve_spend(
                month="2026-11", model="a", purpose="p", usd=0.1, ceiling=1.0
            )
            if hold is not None:
                held.append(hold)

    threads = [threading.Thread(target=take) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(held) == 10
    assert sum(led.month_spend("2026-11").values()) <= 1.0 + 1e-9


def _two_file_repo(tmp_path):
    root = _repo(tmp_path / "project")
    (root / OTHER).write_bytes(BEFORE.encode())
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "other")
    return root


def _batch(tmp_path, monkeypatch, *, ceiling=100.0, third=False):
    root = _two_file_repo(tmp_path)
    if third:
        (root / THIRD).write_bytes(BEFORE.encode())
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "third")
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
    monkeypatch.setattr(tool, "WORKFORCE", ("writer-a", "writer-b"))
    monkeypatch.setattr(tool, "MONTHLY_AWS_USD", ceiling)
    asked: list = []
    ids: list = []

    def completer(model, region):
        def complete(prompt, system, request_id):
            asked.append(model)
            ids.append(request_id)
            return f"```jsx\n{AFTER}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    args = SimpleNamespace(
        project=str(root),
        budget=10,
        model=None,
        region="r",
        rules=[RULE],
        dry_run=False,
    )
    return led, asked, args, ids


def test_a_batch_spreads_across_the_writers_and_pays_for_each_call(
    tmp_path, monkeypatch
) -> None:
    led, asked, args, ids = _batch(tmp_path, monkeypatch)
    assert tool.cmd_propose(args) == 0
    proposals = led.proposals()
    assert {p["rel"] for p in proposals} == {REL, OTHER}
    assert sorted(p["model"] for p in proposals) == ["writer-a", "writer-b"]
    assert sorted(asked) == ["writer-a", "writer-b"]
    assert all(p["status"] == "proposed" for p in proposals)
    spent = led.month_spend(tool._month())
    assert set(spent) == {"writer-a", "writer-b"} and all(v > 0 for v in spent.values())
    worst = tool.worst_case_usd(1)
    assert all(v < worst for v in spent.values()), "every hold was settled"
    with sqlite3.connect(led.path) as db:
        holds = [row[0] for row in db.execute("SELECT id FROM spend")]
    assert sorted(ids) == sorted(f"gagos:{tool._slot()}:spend-{h}" for h in holds), (
        "Codex's review of #580: each call's request id is its own persisted "
        "spend hold, never reused by a later batch"
    )


def test_past_the_ceiling_no_model_is_asked_and_the_work_waits(
    tmp_path, monkeypatch, capsys
) -> None:
    led, asked, args, _ids = _batch(tmp_path, monkeypatch, ceiling=0.0)
    assert tool.cmd_propose(args) == 0
    assert asked == [] and led.proposals() == []
    assert "AWS ceiling" in capsys.readouterr().out
    assert not led.attempted(REL, RULE, dw.digest(BEFORE)), (
        "a finding not asked for is tried again when there is budget"
    )


def test_a_writers_record_counts_only_what_it_wrote(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")

    def by(model, **kw):
        return led.record_proposal(
            FINDING,
            base_text=BEFORE,
            base_commit="c" * 40,
            model=model,
            new_text=kw.get("new_text", AFTER),
            verdict=kw.get("verdict", dw.StaticVerdict(True, "ok", 1)),
            refusal=kw.get("refusal"),
        )

    _both(led, by("w"))
    rejected = by("w")
    led.record_review(rejected, "codex", model="m", verdict="reject", reason="no")
    by("w", verdict=dw.StaticVerdict(False, "the proposal does not parse", 1))
    by("w", new_text=None, verdict=None, refusal="model call failed: timeout")
    by(dw.NO_MODEL, new_text=None, verdict=None, refusal="file is too long")
    by("w")  # awaiting review: not decided yet
    assert led.model_outcomes() == {"w": (1, 3)}


def test_writers_are_compared_within_one_rule(tmp_path) -> None:
    """Codex's review of #580: raw rates across rules reward easy work."""
    led = dw.DailyLedger(tmp_path / "l.db")
    easy = dw.Finding(rel=REL, rule="easy-rule", warnings=FINDING.warnings)
    accepted = led.record_proposal(
        easy,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="w",
        new_text=AFTER,
        verdict=dw.StaticVerdict(True, "ok", 1),
    )
    _both(led, accepted)
    led.record_proposal(
        FINDING,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="w",
        new_text=AFTER,
        verdict=dw.StaticVerdict(False, "the proposal adds warnings", 1),
    )
    assert led.model_outcomes(rule="easy-rule") == {"w": (1, 1)}
    assert led.model_outcomes(rule=RULE) == {"w": (0, 1)}
    assert led.model_outcomes() == {"w": (1, 2)}


def _failed_call(led, model: str) -> None:
    led.record_proposal(
        dw.Finding(
            rel="frontend/src/Elsewhere.jsx", rule=RULE, warnings=FINDING.warnings
        ),
        base_text=BEFORE,
        base_commit="c" * 40,
        model=model,
        new_text=None,
        verdict=None,
        refusal="model call failed: ValidationException: Error 002: Access to "
        "Bedrock models is not allowed for this account",
    )


def test_refused_writers_are_those_whose_last_call_failed(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    _failed_call(led, "a")
    _failed_call(led, "b")
    led.record_proposal(
        FINDING,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="c",
        new_text=AFTER,
        verdict=dw.StaticVerdict(True, "ok", 1),
    )
    assert led.refused_writers(("a", "b", "c", "never-asked")) == ["a", "b"], (
        "the longest refused first; one answered or never asked is not refused"
    )
    led.record_proposal(
        FINDING,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="a",
        new_text=AFTER,
        verdict=dw.StaticVerdict(False, "the proposal adds warnings", 1),
    )
    assert led.refused_writers(("a", "b", "c")) == ["b"], (
        "an answer, even a refused proposal, ends the refusal"
    )


def test_a_refused_writer_is_tried_on_one_finding_and_the_rest_goes_elsewhere(
    tmp_path, monkeypatch, capsys
) -> None:
    led, asked, args, _ids = _batch(tmp_path, monkeypatch, third=True)
    _failed_call(led, "writer-a")
    assert tool.cmd_propose(args) == 0
    assert sorted(asked) == ["writer-a", "writer-b", "writer-b"], (
        "untried, writer-a would have taken two of the three"
    )
    assert "their last call was refused: writer-a" in capsys.readouterr().out
    assert led.refused_writers(tool.WORKFORCE) == [], "it answered: it is back"


def test_the_operators_plan_takes_at_most_its_share_and_costs_no_aws(
    tmp_path, monkeypatch, capsys
) -> None:
    led, asked, args, _ids = _batch(tmp_path, monkeypatch, ceiling=0.0)
    monkeypatch.setattr(tool, "WORKFORCE", tool.CLAUDE_WRITERS)
    monkeypatch.setattr(tool, "PLAN_PROPOSALS_PER_BATCH", 1)
    assert tool.cmd_propose(args) == 0
    assert len(asked) == 1 and asked[0] in tool.CLAUDE_WRITERS, (
        "asked although the AWS ceiling is spent: the plan is not AWS"
    )
    [p] = led.proposals()
    assert p["status"] == "proposed"
    assert led.month_spend(tool._month()) == {asked[0]: 0.0}
    assert "the operator's Claude plan takes 1 a batch" in capsys.readouterr().out
    waiting = OTHER if p["rel"] == REL else REL
    assert not led.attempted(waiting, RULE, dw.digest(BEFORE)), (
        "the finding over the plan's share waits for a later hour"
    )


class _Run:
    def __init__(self, stdout="", returncode=0, codex_answer=None):
        self.calls: list = []
        self.stdout, self.returncode, self.codex_answer = (
            stdout,
            returncode,
            codex_answer,
        )

    def __call__(self, argv, **kw):
        from pathlib import Path

        self.calls.append((argv, kw))
        if "-o" in argv and self.codex_answer is not None:
            Path(argv[argv.index("-o") + 1]).write_text(
                self.codex_answer, encoding="utf-8"
            )
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "")


@pytest.fixture(autouse=True)
def _no_plan_tools_installed(monkeypatch):
    """As on CI (2026-11-03): neither Claude Code nor Codex is installed, so a
    writer built here never depends on this laptop having them."""
    from aios.core import plan_cli

    monkeypatch.setattr(plan_cli, "claude_executable", lambda: None)
    monkeypatch.setattr(plan_cli, "codex_executable", lambda: None)


def _writer(model, run):
    writer = tool.plan_writer(model)
    assert writer.model == model, "the configured writer, installed or not"
    writer.claude, writer.codex, writer._run = "claude-bin", "codex-bin", run
    if model in tool.CLAUDE_WRITERS:
        writer.claude_models, writer.codex_models = (model,), ()
    else:
        writer.claude_models, writer.codex_models = (), (model,)
    return writer


def test_a_plan_writer_is_sent_only_the_text_as_written() -> None:
    """The workshop's writers are the counter's plan client: one sealed path
    for Claude Code and Codex (aios/core/plan_cli.py, pinned in
    tests/test_plan_cli.py)."""
    from aios.core import model_calls

    answer = "```jsx\nconst a = 1;\n```"
    claude = _Run(stdout=json.dumps({"is_error": False, "result": answer}))
    codex = _Run(codex_answer=answer)
    with model_calls.gateway_scope("route"):
        assert (
            _writer("claude-haiku-5-5", claude).complete("PROMPT", system="SYSTEM")
            == answer
        )
        assert (
            _writer("gpt-6-luna", codex).complete("PROMPT", system="SYSTEM") == answer
        )
    [(argv, kw)] = claude.calls
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert argv[argv.index("--system-prompt") + 1] == "SYSTEM"
    assert kw["input"] == "PROMPT", "GAGOS's prompt, as written"
    [(argv, kw)] = codex.calls
    assert (
        argv[:2] == ["codex-bin", "exec"] and argv[argv.index("-m") + 1] == "gpt-6-luna"
    )
    assert kw["input"] == "SYSTEM\n\nPROMPT"


def test_a_plan_writer_that_gives_no_answer_is_a_failed_call() -> None:
    from aios.core import model_calls
    from aios.core.llm import LLMError

    run = _Run(
        stdout=json.dumps(
            {"is_error": True, "result": "Claude AI usage limit reached"}
        ),
        returncode=1,
    )
    with model_calls.gateway_scope("route"):
        try:
            _writer("claude-sonnet-5-5", run).complete("PROMPT", system="SYSTEM")
        except LLMError as exc:
            assert "usage limit" in str(exc)
        else:
            raise AssertionError("a call with no answer must raise")


def test_each_plan_takes_its_own_share_and_neither_costs_aws(
    tmp_path, monkeypatch, capsys
) -> None:
    """2026-11-03: the GPT models the operator named write too, on his OpenAI
    plan, which has its own share of a batch."""
    led, asked, args, _ids = _batch(tmp_path, monkeypatch, ceiling=0.0, third=True)
    monkeypatch.setattr(
        tool, "WORKFORCE", (tool.CLAUDE_WRITERS[0], tool.CODEX_WRITERS[0])
    )
    monkeypatch.setattr(tool, "PLAN_PROPOSALS_PER_BATCH", 1)
    monkeypatch.setattr(tool, "CODEX_PROPOSALS_PER_BATCH", 1)
    assert tool.cmd_propose(args) == 0
    assert sorted(asked) == sorted([tool.CLAUDE_WRITERS[0], tool.CODEX_WRITERS[0]])
    assert set(led.month_spend(tool._month()).values()) == {0.0}
    assert "the operator's Claude plan takes 1 a batch" in capsys.readouterr().out


def test_without_a_bedrock_key_the_other_writers_still_work(
    tmp_path, monkeypatch, capsys
) -> None:
    from aios.core import bedrock

    led, asked, args, _ids = _batch(tmp_path, monkeypatch)
    monkeypatch.setattr(
        tool, "WORKFORCE", (tool.CLAUDE_WRITERS[0], tool.BEDROCK_WRITERS[0])
    )
    monkeypatch.setattr(bedrock, "credentials_available", lambda region: False)
    assert tool.cmd_propose(args) == 0
    assert asked == [tool.CLAUDE_WRITERS[0]] * 2
    assert "the Bedrock writers wait" in capsys.readouterr().out
