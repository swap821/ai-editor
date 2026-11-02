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
  model was asked about.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

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


def _batch(tmp_path, monkeypatch, *, ceiling=100.0):
    root = _two_file_repo(tmp_path)
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

    def completer(model, region):
        def complete(prompt, system, request_id):
            asked.append(model)
            return f"```jsx\n{AFTER}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    args = SimpleNamespace(
        project=str(root), budget=10, model=None, region="r", rules=None, dry_run=False
    )
    return led, asked, args


def test_a_batch_spreads_across_the_writers_and_pays_for_each_call(
    tmp_path, monkeypatch
) -> None:
    led, asked, args = _batch(tmp_path, monkeypatch)
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


def test_past_the_ceiling_no_model_is_asked_and_the_work_waits(
    tmp_path, monkeypatch, capsys
) -> None:
    led, asked, args = _batch(tmp_path, monkeypatch, ceiling=0.0)
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
