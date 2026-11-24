"""GAGOS understands itself, step 1: its own honest list of what it is missing.

2026-11-24, the operator: "my jarvis which is GAGOS should understand itself
honestly and then complete itself first". Pinned here: every gap is read from
a record GAGOS already keeps; each is owned by what it asks for (GAGOS's own
work, the operator's conversations or acts, or outside); GAGOS's own come
first, the heaviest first; the hour prints them and never fails the hour.
"""

from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path

from aios.application.observability import aliveness
from aios.application.observability.aliveness import Part, Reading
from aios.operations import self_model as sm

NOW = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)


def _friction(text: str, subject: str) -> dict:
    return {"text": text, "subject": subject, "source": "proposal", "ref": "gd-1"}


def test_refusals_are_grouped_by_what_they_say_and_name_their_files() -> None:
    rows = [
        _friction(
            "file is 58833 characters; the bound for a whole-file proposal is 40000",
            "frontend/src/workbench/GagosChrome.jsx",
        ),
        _friction(
            "file is 50322 characters; the bound for a whole-file proposal is 40000",
            "frontend/src/workbench/GagosChrome.voice.test.tsx",
        ),
        _friction(
            "the proposal breaks tests that pass without it: 3 test(s)",
            "a/NerveMesh.tsx",
        ),
        _friction(
            "the privacy filter would redact this file, so it is not sent", "a/D.tsx"
        ),
        _friction("something nobody has seen before", "a/X.tsx"),
    ]
    gaps = {g.key: g for g in sm.friction_gaps(rows, days=7)}
    whole = gaps["friction:whole-file"]
    assert whole.owner == sm.GAGOS and whole.weight == 2
    assert "GagosChrome.jsx, GagosChrome.voice.test.tsx" in whole.what
    assert "2 in 7 days" in whole.what
    assert gaps["friction:breaks-tests"].weight == 1
    assert "friction:other" in gaps
    assert not any("D.tsx" in g.what for g in gaps.values()), (
        "withheld files are said once, elsewhere"
    )


def test_a_withheld_file_is_gagos_own_unless_the_frozen_core_withholds_it() -> None:
    rows = [
        {
            "rel": "frontend/src/D.tsx",
            "kind": "withheld: the privacy filter",
            "times": 3,
        },
        {
            "rel": "frontend/src/S.test.tsx",
            "kind": "withheld: the secret policy",
            "times": 2,
        },
    ]
    owners = {g.what.split()[4]: g.owner for g in sm.withheld_gaps(rows, days=7)}
    assert owners == {"D.tsx": sm.GAGOS, "S.test.tsx": sm.OPERATOR}


def test_the_hours_own_measures_say_what_is_out_of_reach() -> None:
    gaps = sm.measure_gaps({"waiting": 18, "untested": 25, "warnings": 65})
    assert [g.key for g in gaps] == ["measure:waiting", "measure:untested"]
    assert all(g.owner == sm.GAGOS for g in gaps)
    assert sm.measure_gaps(None) == [] and sm.measure_gaps({"waiting": 0}) == []


def _reading(part: Part, status: str, last=None) -> Reading:
    return Reading(part, status, last, "")


def test_a_dormant_part_is_owned_by_what_wakes_it() -> None:
    readings = [
        _reading(
            Part("curriculum", "Curriculum", wakes=aliveness.WAKES_TURN),
            "stale",
            datetime(2026, 6, 11, tzinfo=timezone.utc),
        ),
        _reading(
            Part("organ-49", "49 Approval", wakes=aliveness.WAKES_OPERATOR), "never"
        ),
        _reading(Part("organ-1", "1 Gateway", events=aliveness.TURN), "never"),
        _reading(
            Part("organ-10", "10 Missions", workers=(aliveness.MISSION,)), "never"
        ),
        _reading(
            Part("organ-4", "4 Audit", tables=("tamper_audit_trail",)),
            "stale",
            datetime(2026, 10, 30, tzinfo=timezone.utc),
        ),
        _reading(Part("organ-12", "12 Foundry"), "live"),
    ]

    def owners(live: bool) -> dict:
        return {
            g.key: (g.owner, g.what)
            for g in sm.dormant_gaps(
                readings,
                turn_events=aliveness.TURN,
                mission=aliveness.MISSION,
                mission_envelope_live=live,
            )
        }

    none_live = owners(False)
    assert none_live["dormant:curriculum"] == (
        sm.OPERATOR,
        "Curriculum silent since 2026-06-11: it wakes only in your conversations",
    )
    assert none_live["dormant:organ-49"][0] == sm.OPERATOR
    assert "your own act" in none_live["dormant:organ-49"][1]
    assert none_live["dormant:organ-1"][0] == sm.OPERATOR
    assert none_live["dormant:organ-10"][0] == sm.OPERATOR, "no envelope: his"
    assert none_live["dormant:organ-4"] == (
        sm.GAGOS,
        "4 Audit silent since 2026-10-30: nothing of mine runs it",
    )
    assert "dormant:organ-12" not in none_live, "a live part is no gap"
    assert owners(True)["dormant:organ-10"][0] == sm.GAGOS, "with an envelope, its own"


def test_the_parts_that_wake_in_his_turns_are_declared_on_the_map() -> None:
    """The wake sources measured on 2026-11-24 live on the pulse's own map, so
    the pulse and the self-model read one declaration."""
    by_key = {p.key: p for p in aliveness.PARTS}
    for key in (
        "curriculum",
        "self-analysis",
        "reflex",
        "memory",
        "organ-57",
        "organ-58",
        "organ-29",
        "organ-30",
        "organ-27",
    ):
        assert by_key[key].wakes == aliveness.WAKES_TURN, key
    for key in ("organ-45", "organ-49", "organ-53"):
        assert by_key[key].wakes == aliveness.WAKES_OPERATOR, key


def test_an_organ_not_green_is_owned_by_what_its_reason_asks_for() -> None:
    organs = [
        {
            "organ_id": 44,
            "name": "Golden",
            "status": "yellow",
            "known_blockers": ["Operator attestation of the cohort at 09022036"],
        },
        {
            "organ_id": 46,
            "name": "Learning",
            "status": "yellow",
            "known_blockers": ["Outside-machine residual: a human red-team"],
        },
        {
            "organ_id": 55,
            "name": "Reel",
            "status": "yellow",
            "known_blockers": ["STALE ATTESTATION (recorded 3619eea9)"],
        },
        {
            "organ_id": 60,
            "name": "New",
            "status": "yellow",
            "known_blockers": ["its tests fail"],
        },
        {"organ_id": 9, "name": "Caps", "status": "green", "known_blockers": []},
    ]
    owners = {g.key: g.owner for g in sm.organ_gaps(organs)}
    assert owners == {
        "organ:44": sm.OPERATOR,
        "organ:46": sm.OUTSIDE,
        "organ:55": sm.OPERATOR,
        "organ:60": sm.GAGOS,
    }


def test_gagos_own_gaps_come_first_and_the_heaviest_first() -> None:
    model = sm.compose(
        [sm.Gap("organ:44", "o", "e", sm.OPERATOR)],
        [
            sm.Gap("friction:a", "a", "e", sm.GAGOS, 2),
            sm.Gap("friction:b", "b", "e", sm.GAGOS, 18),
        ],
        [sm.Gap("organ:46", "x", "e", sm.OUTSIDE)],
    )
    assert [g.key for g in model.gaps] == [
        "friction:b",
        "friction:a",
        "organ:44",
        "organ:46",
    ]
    lines = sm.report_lines(model, shown=1)
    assert (
        lines[0]
        == "self-model: 2 gap(s) I can work on, 1 that need the operator, 1 outside us"
    )
    assert lines[1:] == ["  - b", "  - and 1 more"]


class _Ledger:
    def friction(self, since):
        return [_friction("the bound for a whole-file proposal is 40000", "a/Big.jsx")]

    def writer_withholdings(self, since):
        return []

    def measures(self):
        return [{"values": {"waiting": 18, "untested": 25}}]


#: A consistency audit with nothing to say.
CLEAN = {"rows": 58, "covered": 58, "open": [], "errors": []}


class _Envelope:
    def status(self):
        return {"live": False, "reason": "the envelope has expired"}


def test_the_hour_prints_gagos_own_list(tmp_path, capsys) -> None:
    from tools import gagos_daily

    model = gagos_daily.self_model_hour(
        _Ledger(),
        Path(tmp_path),
        now=NOW,
        readings=[],
        envelope=_Envelope(),
        consistency=CLEAN,
    )
    out = capsys.readouterr().out
    assert (
        "self-model: 3 gap(s) I can work on, 0 that need the operator, 0 outside us"
        in out
    )
    assert "25 of my files have no test" in out
    assert "Big.jsx" in out
    assert len(model.owned(sm.GAGOS)) == 3


# -- harmony: GAGOS reads its own consistency audit (2026-11-24) -------------------


def test_a_clean_audit_is_no_gap_and_drift_is_gagos_own() -> None:
    assert sm.consistency_gaps(CLEAN) == []
    unheld = sm.consistency_gaps({**CLEAN, "covered": 56, "open": ["a", "b"]})
    assert [(g.key, g.owner, g.weight) for g in unheld] == [
        ("consistency:open", sm.GAGOS, 2)
    ]
    assert "a, b" in unheld[0].what
    wrong = sm.consistency_gaps(
        {**CLEAN, "errors": ["row x: its guard does not exist"]}
    )
    assert (
        wrong[0].key == "consistency:errors"
        and "its guard does not exist" in wrong[0].what
    )
    unread = sm.consistency_gaps(None)
    assert unread[0].key == "consistency:unread" and unread[0].owner == sm.GAGOS


def test_the_hour_reads_the_audit_the_operator_runs() -> None:
    """One derivation, two callers: the hour's summary of this tree is the
    audit's own result, read by loading scripts/consistency_audit.py itself."""
    import importlib.util

    from tools import gagos_daily

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "audit_here", root / "scripts" / "consistency_audit.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    result = module.audit(module.load(), root)
    summary = gagos_daily.consistency_summary(root)
    assert summary == {
        "rows": len(result.rows),
        "covered": len(result.covered),
        "open": [row.id for row in result.open],
        "errors": list(result.errors),
    }
    assert gagos_daily.consistency_summary(root / "no-such-tree") is None


def test_the_hour_says_when_its_parts_may_disagree(tmp_path, capsys) -> None:
    from tools import gagos_daily

    gagos_daily.self_model_hour(
        _Ledger(),
        Path(tmp_path),
        now=NOW,
        readings=[],
        envelope=_Envelope(),
        consistency={**CLEAN, "open": ["brief-inputs"]},
    )
    assert (
        "neither held to one source nor guarded: brief-inputs"
        in capsys.readouterr().out
    )
