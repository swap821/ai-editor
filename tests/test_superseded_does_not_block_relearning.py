"""A retired skill row must not stop the system relearning that skill.

`procedural_skills` carries two identity columns that disagree about what
superseding means. `signature_v2`'s unique index is PARTIAL --
`WHERE status != 'superseded'` -- so a retired row steps aside. The legacy
`signature` column is `NOT NULL UNIQUE` at table level with no such exemption.

So `record_attempt` finds no active row (correct), tries to INSERT (correct),
and dies on `UNIQUE constraint failed: procedural_skills.signature`. Not a
wrong number -- a crash, mid-learning, for a skill the system is entitled to
relearn. Found live: a ladder run superseded its own arcs to re-measure with a
fixed instrument, and the next attempt raised IntegrityError after the model
had already done the work.

Nothing reads a skill by the legacy column; it is lineage. These tests pin
that the lineage survives, that relearning works, and -- the part that matters
most -- that an ACTIVE row is still protected from duplication.
"""

from __future__ import annotations

import pytest

from aios.memory.db import get_connection, init_memory_db
from aios.memory.skills import SkillMemory

GOAL = "pin the behaviour of calc.py::add"
STEPS = ["read_file: calc.py", "create_file: test_calc.py", "verify: pytest"]


@pytest.fixture()
def skills(tmp_path):
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    return SkillMemory(db_path=db)


def _supersede_all(skills) -> None:
    with get_connection(skills.db_path) as conn:
        conn.execute("UPDATE procedural_skills SET status = 'superseded'")


class TestRelearningAfterSupersede:
    def test_the_same_arc_can_be_recorded_again(self, skills) -> None:
        skills.record_attempt(GOAL, STEPS, success=True)
        _supersede_all(skills)

        skills.record_attempt(GOAL, STEPS, success=True)  # must not raise

        live = [r for r in skills.list() if r["status"] != "superseded"]
        assert len(live) == 1
        assert live[0]["success_count"] == 1, (
            "the fresh arc must start from zero, not inherit the retired row's "
            "counts -- the whole point of superseding was to re-measure"
        )

    def test_the_retired_row_is_kept_and_still_readable(self, skills) -> None:
        skills.record_attempt(GOAL, STEPS, success=True)
        _supersede_all(skills)
        skills.record_attempt(GOAL, STEPS, success=False)

        with get_connection(skills.db_path) as conn:
            rows = conn.execute(
                "SELECT id, signature, status FROM procedural_skills ORDER BY id"
            ).fetchall()
        assert len(rows) == 2, "history must be preserved, not overwritten"
        retired, live = rows
        assert retired["status"] == "superseded"
        assert retired["signature"].endswith(f":superseded:{retired['id']}"), (
            "the retired row keeps its original identity in readable form"
        )
        assert live["signature"] == retired["signature"].split(":superseded:")[0], (
            "the live row takes the TRUE legacy signature, so lineage stays "
            "meaningful for the row that is actually the arc now"
        )

    def test_repeated_supersede_cycles_do_not_collide(self, skills) -> None:
        """Two retired generations must not collide with each other either."""
        for _ in range(3):
            skills.record_attempt(GOAL, STEPS, success=True)
            _supersede_all(skills)
        skills.record_attempt(GOAL, STEPS, success=True)

        with get_connection(skills.db_path) as conn:
            sigs = [
                r["signature"]
                for r in conn.execute("SELECT signature FROM procedural_skills")
            ]
        assert len(sigs) == len(set(sigs)) == 4


class TestWhatMustNotChange:
    def test_an_ACTIVE_duplicate_is_still_one_row(self, skills) -> None:
        """The constraint's real job is untouched: one active row per arc.

        If this ever fails, the repair has become a way to fragment a live
        trail into duplicates, which is the exact defect `signature_v2` was
        introduced to end.
        """
        for _ in range(3):
            skills.record_attempt(GOAL, STEPS, success=True)

        rows = skills.list()
        assert len(rows) == 1
        assert rows[0]["success_count"] == 3

    def test_a_different_arc_is_not_disturbed(self, skills) -> None:
        skills.record_attempt(GOAL, STEPS, success=True)
        skills.record_attempt("a completely different goal", STEPS, success=True)
        _supersede_all(skills)
        skills.record_attempt(GOAL, STEPS, success=True)

        with get_connection(skills.db_path) as conn:
            untouched = conn.execute(
                "SELECT signature FROM procedural_skills "
                "WHERE goal_pattern = 'a completely different goal'"
            ).fetchone()
        assert ":superseded:" not in untouched["signature"], (
            "only the colliding signature may be freed; rewriting every "
            "retired row would destroy lineage nobody asked about"
        )
