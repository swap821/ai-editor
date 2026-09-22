"""A retired reflex comes back when its skill earns it again — and not before.

`cerebellum.py` has promised this since it was written: a decompiled playbook
"cannot recompile without the underlying skill re-earning verification from
scratch". The compile guard excluded `status IN ('compiled','decompiled')` and
NOTHING in the codebase ever cleared 'decompiled', so the first half was
enforced and the second half did not exist. Two replay flakes removed a reflex
permanently. One live skill is in that state today.

The interesting tests here are the ones that must NOT pass. "It can come back"
is easy; "it can come back ONLY by earning it" is the property worth having,
because the alternative is a reflex that a flake retires and a shrug restores.
`decompiled_at_successes` records the skill's promotable success_count at the
moment of retirement, so the guard compares against evidence rather than
against elapsed time or mere activity.
"""

from __future__ import annotations

import pytest

from aios.core.cerebellum import Cerebellum
from aios.core.verification_strength import VerificationStrength
from aios.memory.db import get_connection, init_memory_db
from aios.memory.skills import SkillMemory

GOAL = "read the source and run the tests"
STEPS = ["read_file: a.py", "verify: pytest"]


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "memory.sqlite"
    init_memory_db(path)
    return path


def _earn(db, times=3, strength=VerificationStrength.STRONG) -> int:
    skills = SkillMemory(db_path=db)
    skill_id = 0
    for _ in range(times):
        skill_id = skills.record_attempt(GOAL, STEPS, success=True, strength=strength)
    return skill_id


def _compile_then_retire(db) -> tuple[Cerebellum, int]:
    skill_id = _earn(db)
    cerebellum = Cerebellum(db)
    assert cerebellum.try_compile_all() == 1
    assert cerebellum.invalidate_for_skill(skill_id) is True
    return cerebellum, skill_id


def _live_playbooks(db) -> int:
    with get_connection(db) as conn:
        return conn.execute(
            "SELECT COUNT(*) n FROM compiled_playbooks WHERE status = 'compiled'"
        ).fetchone()["n"]


class TestRecovery:
    def test_new_promotable_successes_bring_the_reflex_back(self, db) -> None:
        _compile_then_retire(db)
        assert _live_playbooks(db) == 0

        _earn(db)  # re-earned: three more STRONG successes
        assert Cerebellum(db).try_compile_all() == 1
        assert _live_playbooks(db) == 1

    def test_the_retirement_records_what_it_had_earned(self, db) -> None:
        """The comparison is against EVIDENCE, not against a timestamp."""
        _compile_then_retire(db)
        with get_connection(db) as conn:
            row = conn.execute(
                "SELECT decompiled_at_successes FROM compiled_playbooks"
            ).fetchone()
        assert row["decompiled_at_successes"] == 3


class TestWhatMustStayBarred:
    """The half that makes the other half safe."""

    def test_no_new_evidence_stays_barred(self, db) -> None:
        _compile_then_retire(db)
        assert Cerebellum(db).try_compile_all() == 0
        assert _live_playbooks(db) == 0

    def test_recompiling_twice_over_does_not_resurrect_it(self, db) -> None:
        """Re-running the compiler is not evidence of anything."""
        _compile_then_retire(db)
        for _ in range(5):
            assert Cerebellum(db).try_compile_all() == 0

    def test_a_below_floor_success_cannot_buy_it_back(self, db) -> None:
        """A WEAK green does not move `success_count`, so it cannot pay.

        This is the one an attacker — or an agent optimising for a green —
        would reach for: the cheapest possible "success" that resets the
        streak and looks like progress.
        """
        _compile_then_retire(db)
        _earn(db, times=3, strength=VerificationStrength.WEAK)
        assert Cerebellum(db).try_compile_all() == 0
        assert _live_playbooks(db) == 0

    def test_a_failure_cannot_buy_it_back(self, db) -> None:
        skills = SkillMemory(db_path=db)
        _compile_then_retire(db)
        skills.record_attempt(GOAL, STEPS, success=False)
        assert Cerebellum(db).try_compile_all() == 0

    def test_a_live_playbook_is_never_duplicated(self, db) -> None:
        """One arc, one reflex — the guard's original job, still intact."""
        _earn(db)
        cerebellum = Cerebellum(db)
        assert cerebellum.try_compile_all() == 1
        _earn(db)  # more successes, but the reflex already exists
        assert Cerebellum(db).try_compile_all() == 0
        with get_connection(db) as conn:
            assert (
                conn.execute("SELECT COUNT(*) n FROM compiled_playbooks").fetchone()[
                    "n"
                ]
                == 1
            )


class TestRowsRetiredBeforeTheColumnExisted:
    def test_a_null_stamp_requires_growth_rather_than_forgiving_or_barring(
        self, db
    ) -> None:
        """Migration backfills NULL to the skill's count at that moment.

        We cannot know what a pre-existing decompiled row had earned, so the
        honest rule is neither "barred forever" (the bug) nor "free pass" (the
        over-correction): it needs MORE than it has today.
        """
        _compile_then_retire(db)
        with get_connection(db) as conn:
            conn.execute("UPDATE compiled_playbooks SET decompiled_at_successes = NULL")

        assert Cerebellum(db).try_compile_all() == 0, (
            "a row with no recorded stamp must not recompile on the strength of "
            "successes it may already have had when it was retired"
        )

        _earn(db)
        assert Cerebellum(db).try_compile_all() == 1
