"""GAGOS completes itself, step 2: the goals it takes on itself from its own gaps.

2026-11-24, the operator's step 2. Pinned here: only findings refused because
their file is over the whole-file bound become goals; only while the file is
byte-for-byte the one refused (still true); only inside a live mission
envelope's folders and kinds; never on a file a goal already claims or GAGOS's
own unmerged work touches; one an hour; never without an envelope; the words
reach a writer as written.
"""

from __future__ import annotations

import json
from pathlib import Path

from aios.domain.capabilities.envelope import EnvelopeTerms, is_test_file
from aios.maintenance.daily_work import DailyLedger, digest
from aios.operations import self_goals as sg

REL = "frontend/src/workbench/Big.jsx"
OTHER = "frontend/src/workbench/Other.jsx"
RULES = ("no-unused-vars", "react-hooks/set-state-in-effect")


def _refusal(
    rel=REL,
    rule="no-unused-vars",
    base="d1",
    at="2026-11-23T10:00:00+00:00",
    warnings=(
        (25, 3, "'x' is defined but never used. Allowed unused vars must match /^_/u."),
    ),
    refusal="file is 58833 characters; the bound for a whole-file proposal is 40000",
):
    return {
        "rel": rel,
        "rule": rule,
        "base_digest": base,
        "created_at": at,
        "refusal": refusal,
        "warnings": json.dumps([list(w) for w in warnings]),
    }


def test_only_size_refusals_still_true_become_candidates() -> None:
    rows = [
        _refusal(),
        _refusal(
            rule="react-hooks/set-state-in-effect",
            warnings=((547, 7, "Error: setState in effect\nmore"),),
        ),
        _refusal(rel=OTHER, base="old"),  # the file changed since
        _refusal(
            rel=OTHER, refusal="the privacy filter would redact this file"
        ),  # not size
        _refusal(rule="gagos/missing-test"),  # not a rule it may attempt
    ]
    now = {REL: "d1", OTHER: "new"}
    found = sg.candidates(rows, digest_now=now.get, rules=RULES)
    assert [c.rel for c in found] == [REL]
    assert found[0].findings == (
        (
            "no-unused-vars",
            25,
            "'x' is defined but never used. Allowed unused vars must match /^_/u.",
        ),
        ("react-hooks/set-state-in-effect", 547, "Error: setState in effect"),
    )
    assert found[0].marker == "base d1"


def test_the_latest_refusal_of_a_finding_is_the_one_that_counts() -> None:
    rows = [
        _refusal(base="old", at="2026-11-20T00:00:00+00:00"),
        _refusal(base="d1", at="2026-11-23T00:00:00+00:00"),
    ]
    assert [
        c.base_digest
        for c in sg.candidates(rows, digest_now={REL: "d1"}.get, rules=RULES)
    ] == ["d1"]
    assert sg.candidates(rows, digest_now={REL: "old"}.get, rules=RULES) == []
    assert sg.candidates(rows, digest_now=lambda rel: None, rules=RULES) == [], (
        "gone: none"
    )


def _candidate() -> sg.Candidate:
    return sg.candidates([_refusal()], digest_now={REL: "d1"}.get, rules=RULES)[0]


def test_a_file_a_goal_claims_is_not_taken_again() -> None:
    c = _candidate()
    assert sg.unclaimed(c, [])
    assert not sg.unclaimed(
        c, [{"files": [REL], "status": "open", "created_at": "2026-01-01"}]
    )
    assert not sg.unclaimed(
        c,
        [
            {
                "files": [OTHER, REL],
                "status": "taken",
                "created_at": "2026-11-24T00:00:00+00:00",
            }
        ],
    ), "a goal set since the refusal, as an extra file"
    assert not sg.unclaimed(
        c,
        [
            {
                "rel": REL,
                "also": "[]",
                "status": "taken",
                "created_at": "2026-11-01",
                "said_by": f"{sg.SAID_BY}, base d1",
            }
        ],
    ), "GAGOS already took this same base on itself"
    assert sg.unclaimed(
        c, [{"files": [REL], "status": "taken", "created_at": "2026-11-01"}]
    )


def test_the_goal_says_what_to_change_and_what_not_to() -> None:
    text = sg.goal_text(_candidate(), size=58833, bound=40000)
    assert text.startswith(
        "Clear 1 lint finding(s) in Big.jsx without changing what it does."
    )
    assert "58833 characters, over my 40000-character bound" in text
    assert "- no-unused-vars, near line 25:" in text
    assert "Do not silence a rule" in text and "make no edit and say why" in text
    assert "frontend/src" not in text, "a file is named by its basename"


def _status(**terms) -> dict:
    base = dict(
        folders=["frontend/src/workbench/"],
        kinds=["code"],
        max_missions=2,
        hours=24,
        days=30,
    )
    return {
        "live": True,
        "terms": EnvelopeTerms.build(**{**base, **terms}).as_payload(),
    }


def test_only_inside_a_live_envelope_folders_and_kinds() -> None:
    def inside(status, rel):
        return sg.within(
            status, rel, terms_from=EnvelopeTerms.from_payload, is_test=is_test_file
        )

    assert inside(_status(), REL)
    assert not inside(_status(folders=["frontend/src/superbrain/"]), REL)
    assert not inside(_status(kinds=["tests"]), REL), (
        "code outside a tests-only envelope"
    )
    assert not inside({"live": False, "reason": "expired"}, REL)


# -- the hour ----------------------------------------------------------------------


class _Envelope:
    def __init__(self, status) -> None:
        self._status = status

    def status(self):
        return self._status


def _hour_setup(tmp_path: Path):
    root = tmp_path / "repo"
    big = root / REL
    big.parent.mkdir(parents=True)
    body = "x".join("" for _ in range(2)) + ("// line\n" * 6000)
    big.write_bytes(body.encode("utf-8"))
    other = root / OTHER
    other.write_bytes(body.encode("utf-8"))
    led = DailyLedger(tmp_path / "ledger.db")
    with led._db() as db:
        for rel in (REL, OTHER):
            db.execute(
                "INSERT INTO proposals (proposal_id, day, created_at, rel, rule, warnings, "
                "base_digest, base_commit, base_text, model, status, refusal) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"gd-{rel[-9:-4]}",
                    "2026-11-23",
                    "2026-11-23T10:00:00+00:00",
                    rel,
                    "no-unused-vars",
                    json.dumps([[25, 3, "'x' is defined but never used."]]),
                    digest(body),
                    "c0ffee",
                    body,
                    "none",
                    "refused",
                    "file is 48000 characters; the bound for a whole-file proposal is 40000",
                ),
            )
    return root, led


def test_without_a_live_envelope_it_takes_nothing_on_itself(tmp_path, capsys) -> None:
    from tools import gagos_daily

    root, led = _hour_setup(tmp_path)
    taken = gagos_daily.self_goals_hour(
        led,
        root,
        envelope=_Envelope({"live": False, "reason": "the envelope has expired"}),
    )
    assert taken == [] and led.tasks() == []
    assert (
        "no live mission envelope (the envelope has expired)" in capsys.readouterr().out
    )


def test_inside_an_envelope_it_takes_one_goal_an_hour_and_not_again(
    tmp_path, capsys
) -> None:
    from tools import gagos_daily

    root, led = _hour_setup(tmp_path)
    envelope = _Envelope(_status())
    first = gagos_daily.self_goals_hour(led, root, envelope=envelope)
    assert len(first) == 1, "one an hour"
    task = led.task(first[0])
    assert task["said_by"].startswith(sg.SAID_BY) and "base " in task["said_by"]
    assert task["status"] == "open"
    second = gagos_daily.self_goals_hour(led, root, envelope=envelope)
    assert len(second) == 1 and second != first, "the next file, the next hour"
    third = gagos_daily.self_goals_hour(led, root, envelope=envelope)
    assert third == [], "both files are claimed now"
    assert "self-goals: none this hour" in capsys.readouterr().out


def test_a_file_its_own_unmerged_work_touches_is_left_alone(tmp_path, capsys) -> None:
    from tools import gagos_daily

    root, led = _hour_setup(tmp_path)
    taken = gagos_daily.self_goals_hour(
        led, root, envelope=_Envelope(_status()), busy={REL, OTHER}
    )
    assert taken == []
    assert "my unmerged work touches it" in capsys.readouterr().out


def test_a_goal_whose_words_a_writer_would_not_see_is_not_set(
    tmp_path, monkeypatch, capsys
) -> None:
    """The check is the very filter a goal's text passes to every writer
    (egress_redact), not a narrower one that could let an altered goal through."""
    from tools import gagos_daily

    root, led = _hour_setup(tmp_path)
    monkeypatch.setattr(
        gagos_daily, "egress_redact", lambda text: text.replace("Clear", "[REDACTED]")
    )
    taken = gagos_daily.self_goals_hour(led, root, envelope=_Envelope(_status()))
    assert taken == [] and led.tasks() == []
    assert "its words would not reach a writer" in capsys.readouterr().out
