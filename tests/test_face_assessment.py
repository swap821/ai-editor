"""GAGOS assesses its own face and writes its own goals (2026-11-17).

The operator: "let GAGOS make its frontend 10/10 and also understand itself
honestly", then chose "GAGOS writes its own". Before this, its hourly
understanding was one stack list, and it had no goals from 11-16 04:53Z, so
his envelope expired unused. Pinned here against GAGOS's own ledger, design
and records, and with stand-ins for what changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios.core.privacy_filter import redact_paths
from aios.maintenance import daily_work as dw
from aios.maintenance import face_assessment as fa
from aios.memory import self_knowledge
from aios.memory.doc_ingest import DocumentIngestor
from tools import gagos_daily as tool

REPO = Path(__file__).resolve().parents[1]
LEDGER = (REPO / fa.LEDGER).read_text(encoding="utf-8")
DESIGN = (REPO / fa.DESIGN).read_text(encoding="utf-8")
BUILT = {
    "rec-01": "REC-01 renderer and backend recovery",
    "perf-01": "PERF-01 desktop frame and input budget",
    "ask-01": "UX-01 ask-to-result and INT-02 turn boundary",
}
NOW = "2026-11-17T04:00:00+00:00"


def test_gagos_reads_its_whole_acceptance_ledger() -> None:
    criteria = fa.read_ledger(LEDGER)
    assert len(criteria) == 29
    assert sum(c.weight for c in criteria) == fa.DENOMINATOR
    assert [(c.id, c.earned) for c in criteria if c.earned] == [("INT-01", 3)]
    body05 = next(c for c in criteria if c.id == "BODY-05")
    assert (body05.weight, body05.stage) == (6, "not-started")


def test_gagos_reads_its_journeys_design_in_the_order_it_builds_them() -> None:
    planned = fa.read_design(DESIGN)
    assert [j.id for j in planned] == [
        "ask-01",
        "decide-01",
        "recover-01",
        "receipt-01",
        "keys-01",
        "body-01",
        "focus-01",
    ]
    recover = next(j for j in planned if j.id == "recover-01")
    assert recover.criteria == ("REC-01", "INT-06")


def test_every_point_not_earned_is_said_with_what_it_needs() -> None:
    a = fa.assess(LEDGER, DESIGN, BUILT, {})
    assert a.earned == 3 and not a.problems
    assert sum(g.criterion.weight - g.criterion.earned for g in a.gaps) == 97
    needs = {g.criterion.id: g.needs for g in a.gaps}
    assert needs["INT-04"] == fa.BUILD
    assert needs["PERF-01"] == needs["UX-01"] == needs["REC-01"] == fa.RUN
    assert needs["BODY-05"] == needs["BODY-02"] == fa.YOURS
    assert needs["BODY-03"] == needs["A11Y-02"] == needs["REL-03"] == fa.PEOPLE
    assert needs["UX-04"] == needs["PERF-03"] == fa.DEVICES
    assert needs["INT-03"] == needs["REL-01"] == fa.UNPLANNED
    assert "INT-01" not in needs
    assert [j.id for j in a.to_build] == [
        "decide-01",
        "recover-01",
        "receipt-01",
        "keys-01",
        "body-01",
        "focus-01",
    ]


def test_a_ledger_that_no_longer_adds_up_is_said() -> None:
    changed = LEDGER.replace(
        "| BODY-05 | Palette/texture canon and visual acceptance (6) |",
        "| BODY-05 | Palette/texture canon and visual acceptance (7) |",
    )
    assert fa.assess(changed, DESIGN, BUILT, {}).problems == [
        "the ledger's criteria weigh 101, not its frozen 100"
    ]
    lines = fa.lines(fa.assess("", DESIGN, BUILT, {}))
    assert any("cannot read itself" in line for line in lines)


def test_the_newest_run_of_each_journey_is_read(tmp_path) -> None:
    for name, started, outcome in (
        ("a.json", "2026-11-15T10:00:00+00:00", "failed"),
        ("b.json", "2026-11-16T10:00:00+00:00", "passed"),
    ):
        (tmp_path / name).write_text(
            json.dumps(
                {"journey": "perf-01", "started_at": started, "outcome": outcome}
            ),
            encoding="utf-8",
        )
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    newest = fa.newest_records(tmp_path)
    assert newest["perf-01"]["outcome"] == "passed"
    a = fa.assess(
        LEDGER,
        DESIGN,
        BUILT,
        {
            "perf-01": dict(
                newest["perf-01"], signed_in=False, measured={"window": "headed"}
            )
        },
    )
    said = "\n".join(fa.lines(a))
    assert (
        "PERF-01: perf-01 passed on 2026-11-16 (signed out, headed, build not recorded)"
        in said
    )
    assert "UX-01: never run" in said


def test_gagos_asks_itself_for_the_next_journey_and_the_goal_reaches_its_writers() -> (
    None
):
    a = fa.assess(LEDGER, DESIGN, BUILT, {})
    journey, text = fa.next_goal(a, DESIGN, [], now=NOW)
    assert journey.id == "decide-01"
    assert text.startswith(
        "[face decide-01] Build the decide-01 journey in gagos_journeys.py"
    )
    assert len(text) <= dw.MAX_TASK_CHARS
    # Path-shaped text is redacted on the way to a cloud writer (2026-11-15).
    assert redact_paths(text) == text
    assert (
        "when the operator clicks Approve, Deny or Stop, the runner never clicks them"
        in text
    )


def _task(jid: str, status: str, created: str, *, by: str = fa.SAID_BY) -> dict:
    return {
        "task_id": f"gt-{jid}",
        "text": f"[face {jid}] Build the {jid} journey",
        "said_by": by,
        "status": status,
        "created_at": created,
        "updated_at": created,
    }


@pytest.mark.parametrize(
    ("tasks", "wanted"),
    [
        # One of its own goals in flight: nothing more is asked.
        ([_task("decide-01", "open", "2026-11-17T01:00:00+00:00")], None),
        ([_task("decide-01", "taken", "2026-11-15T01:00:00+00:00")], None),
        # Taken over a week ago and still unbuilt: the next one is asked beside it.
        ([_task("decide-01", "taken", "2026-11-01T01:00:00+00:00")], "recover-01"),
        # A journey asked for once is never asked again.
        ([_task("decide-01", "refused", "2026-11-16T01:00:00+00:00")], "recover-01"),
        # The operator's own goals are his, never counted as GAGOS's.
        (
            [
                _task(
                    "decide-01", "open", "2026-11-17T01:00:00+00:00", by="the operator"
                )
            ],
            "decide-01",
        ),
    ],
)
def test_one_of_its_own_goals_at_a_time(tasks, wanted) -> None:
    got = fa.next_goal(fa.assess(LEDGER, DESIGN, BUILT, {}), DESIGN, tasks, now=NOW)
    assert (got[0].id if got else None) == wanted


def test_a_built_journey_frees_the_next_goal() -> None:
    built = dict(BUILT, **{"decide-01": "INT-04 approval, denial and Stop authority"})
    tasks = [_task("decide-01", "taken", "2026-11-16T01:00:00+00:00")]
    a = fa.assess(LEDGER, DESIGN, built, {})
    assert next(g for g in a.gaps if g.criterion.id == "INT-04").needs == fa.RUN
    assert fa.next_goal(a, DESIGN, tasks, now=NOW)[0].id == "recover-01"


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "gdw"
    for rel in (fa.LEDGER, fa.DESIGN):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(
            (REPO / rel).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (root / fa.RECORDS).mkdir(parents=True)
    return root


def test_its_hour_says_its_face_and_files_one_goal_through_the_ledger(
    tmp_path, monkeypatch, capsys
) -> None:
    root = _checkout(tmp_path)
    monkeypatch.setattr(tool, "_git", lambda root, *args: "f" * 40)
    led = dw.DailyLedger(tmp_path / "l.db")
    document = tool.face_hour(led, root, built=BUILT, now=NOW)
    said = capsys.readouterr().out
    assert "face: 3 of 100 points accepted" in said
    assert "face: 26 points need a journey GAGOS has not built" in said
    assert "face: GAGOS asks itself for decide-01" in said
    (goal,) = led.tasks(status="open")
    assert goal["said_by"] == fa.SAID_BY and goal["rel"] == fa.RUNNER
    assert "| INT-04 | Approval, denial and Stop authority | 4 |" in document
    # The next hour: its goal is open, so nothing more is asked, and it says so.
    tool.face_hour(led, root, built=BUILT, now=NOW)
    said = capsys.readouterr().out
    assert "asks itself" not in said
    assert "face: GAGOS asked for decide-01 on 2026-11-1" in said
    assert len(led.tasks()) == 1


def test_its_knowledge_base_keeps_the_assessment_it_wrote(tmp_path) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "README.md").write_text("GAGOS.\n", encoding="utf-8")
    ingestor = DocumentIngestor(db_path=tmp_path / "memory.db")
    out = self_knowledge.refresh(
        root, ingestor=ingestor, generated={"face-assessment.md": "# 3 of 100\n"}
    )
    assert out["changed"] == ["README.md", "generated/face-assessment.md"]
    names = {s["filename"] for s in ingestor.list_sources()}
    assert "gagos:generated/face-assessment.md" in names
    again = self_knowledge.refresh(
        root, ingestor=ingestor, generated={"face-assessment.md": "# 3 of 100\n"}
    )
    assert again["kept"] == ["README.md", "generated/face-assessment.md"]
    assert not again["removed"]
