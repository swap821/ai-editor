"""GAGOS proposes governance lessons from the friction it keeps meeting (2026-11-15).

Organ 46 turns a governance lesson into an amendment proposal, never further,
and nothing ever proposed one: the organ was idle. The operator's word of
2026-11-15 ("yes on organ46"): GAGOS proposes them itself, from the refusals
its own ledger keeps. Pinned here: a friction becomes a lesson only when it
recurs (often enough in a week, and still in the last day); each is proposed
once, through organ 46's own authority and its screen, into the store its
routes read; and a lesson the operator has already ruled on is never proposed
again.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import pytest

from aios.application.governance.constitutional_learning import (
    ConstitutionalLearningAuthority,
    ConstitutionalLearningError,
)
from aios.infrastructure.governance.sqlite_store import GovernanceAmendmentStore
from aios.maintenance.daily_work import DailyLedger
from aios.operations import governance_lessons as gl
from tools import gagos_daily as tool

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
WITHHELD = "the privacy filter would redact this file, so it is not sent"
SCRUBBED = (
    "the answer was scrubbed on its way back from the writer (HIGH_ENTROPY): a "
    "scanner took part of the code for a secret, so it is not what the writer wrote"
)
SLOTS = "outside the operator's envelope: the envelope's 2 missions are used"


def _row(text, hours_ago, *, source="proposal", ref=None, subject="a.tsx"):
    return {
        "source": source,
        "ref": ref or f"gd-{hours_ago:04d}",
        "subject": subject,
        "text": text,
        "created_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
    }


@pytest.fixture()
def store(tmp_path):
    return GovernanceAmendmentStore(tmp_path / "governance.db")


def test_a_friction_seen_often_and_lately_recurs():
    rows = [
        _row(WITHHELD, h, subject=f"f{i % 3}.tsx")
        for i, h in enumerate((1, 20, 40, 70, 100))
    ]
    [found] = gl.recurring(rows, now=NOW)
    assert found.friction.key == "privacy-withheld-file"
    assert found.count == 5 and found.subjects == 3
    assert found.last == rows[0]["created_at"]
    assert found.refs[0] == "gagos-ledger:proposal:gd-0001"


def test_too_few_too_old_or_not_lately_is_not_recurring():
    four = [_row(WITHHELD, h) for h in (1, 2, 3, 4)]
    stale = [_row(WITHHELD, h) for h in (30, 40, 50, 60, 70)]
    old = [_row(WITHHELD, h) for h in (1, 2, 3, 4)] + [_row(WITHHELD, 24 * 8)]
    assert gl.recurring(four, now=NOW) == []
    # Five in the week, none in the last day: it stopped, nothing to learn now.
    assert gl.recurring(stale, now=NOW) == []
    # Older than the week does not count.
    assert gl.recurring(old, now=NOW) == []


def test_each_friction_is_recognised_and_others_are_not():
    rows = (
        [_row(SCRUBBED, h) for h in range(1, 6)]
        + [_row(SLOTS, h, source="goal_mission", subject="gt-1") for h in range(1, 6)]
        # Already governed elsewhere (resting and refused writers): no lesson.
        + [
            _row("model call failed: LLMError: You've hit your limit", h)
            for h in range(1, 9)
        ]
        + [
            _row("model call failed: LLMError: Bedrock Converse failed", h)
            for h in range(1, 9)
        ]
    )
    keys = sorted(r.friction.key for r in gl.recurring(rows, now=NOW))
    assert keys == ["envelope-slots-used", "names-scrubbed-as-secrets"]


def test_evidence_is_capped_and_newest_first():
    rows = [_row(WITHHELD, h) for h in range(1, 40)]
    [found] = gl.recurring(rows, now=NOW)
    assert found.count == 39
    assert len(found.refs) == gl.MAX_EVIDENCE
    assert found.refs[0].endswith("gd-0001")


@pytest.mark.parametrize("friction", gl.FRICTIONS, ids=lambda f: f.key)
def test_every_lesson_passes_organ_46s_screen(friction):
    authority = ConstitutionalLearningAuthority()
    for text in (friction.current_rule, friction.harm, friction.improvement):
        authority.assert_never_reduces_human_authority(text)


def test_a_recurring_friction_is_proposed_once_through_organ_46(store):
    rows = [_row(WITHHELD, h, subject=f"f{h}.tsx") for h in range(1, 7)]
    first = gl.propose_lessons(rows, now=NOW, store=store)
    assert [(r.friction.key, outcome) for r, outcome in first] == [
        ("privacy-withheld-file", "proposed")
    ]
    lesson = store.get_current_lesson("gagos-friction-privacy-withheld-file")
    assert lesson.status == "proposed"
    assert lesson.problem_class == "privacy_denial"
    assert "6 times in the last 7 days" in lesson.observed_harm
    assert "6 files" in lesson.observed_harm
    assert lesson.evidence_refs[0] == "gagos-ledger:proposal:gd-0001"
    assert 0.5 <= lesson.confidence <= 0.9
    # The next hour proposes nothing new: one lesson, one revision.
    again = gl.propose_lessons(rows, now=NOW, store=store)
    assert [outcome for _r, outcome in again] == ["already with organ 46 (proposed)"]
    assert len(store.get_lesson_history("gagos-friction-privacy-withheld-file")) == 1


def test_a_lesson_the_operator_ruled_on_is_never_proposed_again(store):
    rows = [_row(WITHHELD, h) for h in range(1, 7)]
    gl.propose_lessons(rows, now=NOW, store=store)
    lesson = store.get_current_lesson("gagos-friction-privacy-withheld-file")
    store.save_lesson(lesson.model_copy(update={"status": "rejected"}))
    [(_r, outcome)] = gl.propose_lessons(rows, now=NOW, store=store)
    assert outcome == "already with organ 46 (rejected)"
    assert store.get_current_lesson(lesson.lesson_id).status == "rejected"


def test_a_lesson_organ_46_refuses_is_said_and_not_kept(store):
    class Refusing(ConstitutionalLearningAuthority):
        def assert_never_reduces_human_authority(self, text):
            raise ConstitutionalLearningError("an authority-reduction marker")

    rows = [_row(WITHHELD, h) for h in range(1, 7)]
    [(_r, outcome)] = gl.propose_lessons(
        rows, now=NOW, store=store, authority=Refusing()
    )
    assert outcome.startswith("refused by organ 46's screen")
    assert store.get_current_lesson("gagos-friction-privacy-withheld-file") is None


def test_the_ledger_gives_its_refusals_since_a_time(tmp_path):
    led = DailyLedger(tmp_path / "ledger.db")
    tid = led.add_task("frontend/src/a.tsx", "make it better", said_by="operator")
    led.record_origination(tid, {"state": "refused", "reason": SLOTS})
    led.record_origination(tid, {"state": "awaiting_approval", "mission_id": "m-1"})
    rows = led.friction(since="2000-01-01T00:00:00+00:00")
    assert [(r["source"], r["subject"], r["text"]) for r in rows] == [
        ("goal_mission", tid, SLOTS)
    ]
    assert led.friction(since="2999-01-01T00:00:00+00:00") == []


def test_the_hour_proposes_and_says_so(tmp_path, monkeypatch, capsys, store):
    led = DailyLedger(tmp_path / "ledger.db")
    rows = [_row(SLOTS, h, source="goal_mission", subject="gt-1") for h in range(1, 6)]
    monkeypatch.setattr(led, "friction", lambda since: rows)
    tool.governance_hour(led, now=NOW, store=store)
    out = capsys.readouterr().out
    assert (
        "governance: lesson gagos-friction-envelope-slots-used proposed to organ 46"
        in out
    )
    tool.governance_hour(led, now=NOW, store=store)
    assert "already with organ 46 (proposed)" in capsys.readouterr().out


def test_the_hour_says_when_nothing_recurs(tmp_path, capsys, store):
    led = DailyLedger(tmp_path / "ledger.db")
    tool.governance_hour(led, now=NOW, store=store)
    assert "governance: no friction recurred" in capsys.readouterr().out


def test_lessons_lists_gagos_lessons_for_the_operator(monkeypatch, capsys, store):
    rows = [_row(WITHHELD, h) for h in range(1, 7)]
    gl.propose_lessons(rows, now=NOW, store=store)
    monkeypatch.setattr(gl, "lesson_store", lambda: store)
    assert tool.cmd_lessons(argparse.Namespace()) == 0
    out = capsys.readouterr().out
    assert "gagos-friction-privacy-withheld-file (proposed, privacy_denial)" in out
    assert "draft-amendment" in out
    assert "envelope-slots-used: not proposed" in out
