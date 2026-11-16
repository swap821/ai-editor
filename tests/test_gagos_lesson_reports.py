"""Organ 46's two report lessons, built as plain code at the operator's word
(2026-11-16): which files GAGOS's writers could not work on as written, and,
before he signs an envelope, which goals a full envelope turned away. Both
only read; neither prints what a scrubber matched."""

from __future__ import annotations

import argparse

from aios.maintenance import daily_work as dw
from aios.maintenance.daily_work import DailyLedger
from tools import gagos_daily as tool
from tools import gagos_envelope as envelope

SLOTS = "outside the operator's envelope: the envelope's 2 missions are used"
SINCE = "2000-01-01T00:00:00+00:00"
SCRUBBED = (
    "the answer was scrubbed on its way back from the writer (HIGH_ENTROPY): a "
    "scanner took part of the code for a secret, so it is not what the writer wrote"
)


def test_a_full_envelopes_refusals_count_by_goal_and_open_goals_still_wait(tmp_path):
    led = DailyLedger(tmp_path / "ledger.db")
    waiting = led.add_task("frontend/src/a.tsx", "make it better", said_by="operator")
    taken = led.add_task("frontend/src/b.tsx", "and this", said_by="operator")
    for _ in range(3):
        led.record_origination(waiting, {"state": "refused", "reason": SLOTS})
    led.record_origination(taken, {"state": "refused", "reason": SLOTS})
    led.record_origination(
        taken, {"state": "refused", "reason": "the sandbox: unavailable"}
    )
    led.take_task(taken, "gd-1")
    rows = {r["task_id"]: r for r in led.goals_turned_away_by_a_full_envelope(SINCE)}
    assert (rows[waiting]["times"], rows[waiting]["status"]) == (3, "open")
    assert (rows[taken]["times"], rows[taken]["status"]) == (1, "taken")
    lines = envelope.waiting_report(7, led=led)
    assert lines[0].startswith(
        "in the last 7 days a full envelope turned away 2 goal(s), 4 time(s)"
    )
    assert lines[0].endswith("1 still wait:")
    assert lines[1].startswith(f"- {waiting}: turned away 3 time(s) since ")
    assert len(lines) == 2


def test_no_full_envelope_is_said_plainly(tmp_path):
    assert envelope.waiting_report(7, led=DailyLedger(tmp_path / "l.db")) == [
        "no goal found the envelope full in the last 7 days"
    ]


def test_signing_shows_the_waiting_goals_before_anything_is_signed(capsys):
    order: list[str] = []

    class Live:
        def post_stream(self, path, payload, timeout):
            order.append("signed")

            class Reply:
                status_code = 201
                text = ""

                def json(self):
                    return {"envelope": {"live": True}}

            return Reply()

    def connect(base):
        order.append("connected")
        return Live()

    def waiting():
        order.append("shown")
        return ["in the last 7 days a full envelope turned away 1 goal(s)"]

    args = envelope.parser().parse_args(["sign"])
    assert envelope.run(args, connect=connect, waiting=waiting) == 0
    assert order == ["shown", "connected", "signed"]
    assert "turned away 1 goal(s)" in capsys.readouterr().out


def test_revoking_shows_no_report():
    shown = []
    args = envelope.parser().parse_args(["revoke"])

    class Live:
        def post_stream(self, path, payload, timeout):
            class Reply:
                status_code = 200
                text = ""

                def json(self):
                    return {}

            return Reply()

    envelope.run(
        args, connect=lambda base: Live(), waiting=lambda: shown.append(1) or []
    )
    assert shown == []


def test_withholding_kinds_come_from_the_refusals_own_words():
    assert dw.withholding_kind(
        "the secret policy would scrub this file, so it is not sent"
    ) == ("withheld: the secret policy")
    assert (
        dw.withholding_kind(
            "the change cannot be shown to a reviewer: the privacy filter would redact "
            "this file, so it is not sent"
        )
        == "withheld: the privacy filter"
    )
    assert dw.withholding_kind(SCRUBBED) == "answer scrubbed: HIGH_ENTROPY"
    assert dw.withholding_kind("the writer made no edit") is None
    assert dw.withholding_kind(None) is None


def test_withholdings_are_grouped_by_file_and_kind_newest_first(tmp_path):
    led = DailyLedger(tmp_path / "ledger.db")
    finding = dw.Finding(rel="frontend/src/a.tsx", rule="r", warnings=())
    for refusal in (
        "the privacy filter would redact this file, so it is not sent",
        "the privacy filter would redact this file, so it is not sent",
        SCRUBBED,
        "the writer made no edit",
    ):
        led.record_proposal(
            finding,
            base_text="x",
            base_commit="c",
            model="m",
            new_text=None,
            verdict=None,
            refusal=refusal,
        )
    rows = led.writer_withholdings(SINCE)
    assert sorted((r["kind"], r["times"]) for r in rows) == [
        ("answer scrubbed: HIGH_ENTROPY", 1),
        ("withheld: the privacy filter", 2),
    ]
    assert all(r["rel"] == "frontend/src/a.tsx" for r in rows)


def test_a_file_reaches_the_writers_as_it_is_masked_or_withheld():
    def hide_token(text):
        return text.replace("tokenvalue", "[CREDENTIAL REDACTED]")

    assert tool.file_reach("const a = 1;\n", redact=lambda t: t) == "sent as it is"
    assert tool.file_reach(
        "const k = tokenvalue;\n",
        redact=hide_token,
        mask=lambda t: dw.mask_lines(t, hide_token),
    ) == ("sent with 1 placeholder(s)")
    assert tool.file_reach(
        "const k = 1;\n",
        redact=lambda t: t + "!",
        mask=lambda t: (t, {}),
    ) == ("withheld: still altered after masking")

    def cannot(text):
        raise dw.MaskingFailed("no exact restore")

    assert tool.file_reach("x\n", redact=lambda t: "y\n", mask=cannot) == (
        "withheld: it cannot be masked"
    )


def test_the_report_prints_kinds_and_counts_never_the_match(
    tmp_path, monkeypatch, capsys
):
    led = DailyLedger(tmp_path / "ledger.db")
    rel = "frontend/src/a.tsx"
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    (tmp_path / rel).write_text("export const a = 1;\n", encoding="utf-8")
    led.record_proposal(
        dw.Finding(rel=rel, rule="r", warnings=()),
        base_text="x",
        base_commit="c",
        model="m",
        new_text=None,
        verdict=None,
        refusal=SCRUBBED,
    )
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool, "file_reach", lambda text: "sent as it is")
    args = argparse.Namespace(days=7, project=str(tmp_path))
    assert tool.cmd_withheld(args) == 0
    out = capsys.readouterr().out
    assert f"- {rel}: answer scrubbed: HIGH_ENTROPY, 1 time(s)" in out
    assert "today: sent as it is" in out


def test_an_empty_report_says_nothing_was_withheld(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tool, "ledger", lambda: DailyLedger(tmp_path / "ledger.db"))
    assert tool.cmd_withheld(argparse.Namespace(days=7, project=None)) == 0
    assert "no file was withheld from a writer" in capsys.readouterr().out
