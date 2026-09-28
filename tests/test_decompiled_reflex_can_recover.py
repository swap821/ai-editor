"""A retired reflex comes back when its skill earns it again — and not before.

`cerebellum.py` has promised this since it was written: a decompiled playbook
cannot recompile until the underlying skill has earned more. The compile guard
excluded `status IN ('compiled','decompiled')` and NOTHING in the codebase ever
cleared 'decompiled', so the first half was enforced and the second half did
not exist. Two replay flakes removed a reflex permanently.

The interesting tests here are the ones that must NOT pass. "It can come back"
is easy; "it can come back ONLY by earning it" is the property worth having,
because the alternative is a reflex that a flake retires and a shrug restores.
`decompiled_at_successes` records the skill's promotable success count at the
moment of retirement, so the guard compares against evidence rather than
against elapsed time or mere activity.

Since Phase 2 slice 2.4c-B the skill is an operator-ACTIVATED skill in the
institutional library and the count is the library's; these tests use the real
library, because the count is the thing under test.
"""

from __future__ import annotations

import pytest

from aios.application.memory.institutional_skills import (
    InstitutionalSkillAdapter,
    SkillTrailIndex,
)
from aios.core.cerebellum import Cerebellum
from aios.core.verification_strength import VerificationStrength
from aios.domain.learning.repository import SkillRepository
from aios.memory.db import get_connection, init_memory_db

GOAL = "read the source and run the tests"
STEPS = ["read_file: a.py", "verify: pytest"]


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "memory.sqlite"
    init_memory_db(path)
    return path


@pytest.fixture()
def library(tmp_path) -> InstitutionalSkillAdapter:
    operational = tmp_path / "operational.sqlite"
    return InstitutionalSkillAdapter(
        SkillRepository(operational), SkillTrailIndex(operational)
    )


def _earn(library, times=3, strength=VerificationStrength.STRONG) -> int:
    skill_id = 0
    for _ in range(times):
        skill_id = library.record_attempt(GOAL, STEPS, success=True, strength=strength)
    return skill_id


def _activate(library) -> None:
    """The operator's act, in a test. Live, only the capability route does it."""
    (record,) = library.repository.list_skills()
    library.repository.transition_state(
        record.skill_id, record.version, "human_reviewed"
    )
    library.repository.transition_state(record.skill_id, record.version, "active")


def _cerebellum(db, library) -> Cerebellum:
    cerebellum = Cerebellum(db)
    cerebellum.attach_reflex_gate(library)
    return cerebellum


def _compile_then_retire(db, library) -> tuple[Cerebellum, int]:
    skill_id = _earn(library)
    _activate(library)
    cerebellum = _cerebellum(db, library)
    assert cerebellum.try_compile_all() == 1
    assert cerebellum.invalidate_for_skill(skill_id) is True
    return cerebellum, skill_id


def _live_playbooks(db) -> int:
    with get_connection(db) as conn:
        return conn.execute(
            "SELECT COUNT(*) n FROM compiled_playbooks WHERE status = 'compiled'"
        ).fetchone()["n"]


class TestRecovery:
    def test_new_promotable_successes_bring_the_reflex_back(self, db, library) -> None:
        _compile_then_retire(db, library)
        assert _live_playbooks(db) == 0

        _earn(library)  # re-earned: three more STRONG successes
        assert _cerebellum(db, library).try_compile_all() == 1
        assert _live_playbooks(db) == 1

    def test_the_retirement_records_what_it_had_earned(self, db, library) -> None:
        """The comparison is against EVIDENCE, not against a timestamp."""
        _compile_then_retire(db, library)
        with get_connection(db) as conn:
            row = conn.execute(
                "SELECT decompiled_at_successes FROM compiled_playbooks"
            ).fetchone()
        assert row["decompiled_at_successes"] == 3


class TestWhatMustStayBarred:
    """The half that makes the other half safe."""

    def test_no_new_evidence_stays_barred(self, db, library) -> None:
        _compile_then_retire(db, library)
        assert _cerebellum(db, library).try_compile_all() == 0
        assert _live_playbooks(db) == 0

    def test_recompiling_twice_over_does_not_resurrect_it(self, db, library) -> None:
        """Re-running the compiler is not evidence of anything."""
        _compile_then_retire(db, library)
        for _ in range(5):
            assert _cerebellum(db, library).try_compile_all() == 0

    def test_a_below_floor_success_cannot_buy_it_back(self, db, library) -> None:
        """A WEAK green is not evidence in the library, so it cannot pay.

        This is the one an attacker — or an agent optimising for a green —
        would reach for: the cheapest possible "success" that looks like
        progress.
        """
        _compile_then_retire(db, library)
        _earn(library, times=3, strength=VerificationStrength.WEAK)
        assert _cerebellum(db, library).try_compile_all() == 0
        assert _live_playbooks(db) == 0

    def test_a_failure_cannot_buy_it_back(self, db, library) -> None:
        _compile_then_retire(db, library)
        library.record_attempt(GOAL, STEPS, success=False)
        assert _cerebellum(db, library).try_compile_all() == 0

    def test_a_live_playbook_is_never_duplicated(self, db, library) -> None:
        """One arc, one reflex — the guard's original job, still intact."""
        _earn(library)
        _activate(library)
        assert _cerebellum(db, library).try_compile_all() == 1
        _earn(library)  # more successes, but the reflex already exists
        assert _cerebellum(db, library).try_compile_all() == 0
        with get_connection(db) as conn:
            assert (
                conn.execute("SELECT COUNT(*) n FROM compiled_playbooks").fetchone()[
                    "n"
                ]
                == 1
            )


class TestUnstampedRows:
    def test_a_null_stamp_requires_growth_rather_than_forgiving_or_barring(
        self, db, library
    ) -> None:
        """A decompiled row with no recorded count -- the library was unreadable
        when it was decompiled -- is stamped with the library's count at first
        sight. The honest rule is neither "barred forever" (the old bug) nor
        "free pass" (the over-correction): it needs MORE than it has today.
        """
        _compile_then_retire(db, library)
        with get_connection(db) as conn:
            conn.execute("UPDATE compiled_playbooks SET decompiled_at_successes = NULL")

        assert _cerebellum(db, library).try_compile_all() == 0, (
            "a row with no recorded stamp must not recompile on the strength of "
            "successes it may already have had when it was retired"
        )

        _earn(library)
        assert _cerebellum(db, library).try_compile_all() == 1

    def test_an_unreadable_library_at_decompile_stamps_null_not_a_guess(
        self, db, library, monkeypatch
    ) -> None:
        cerebellum, skill_id = _compile_then_retire(db, library)
        with get_connection(db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
        assert cerebellum.try_compile_all() == 1

        def unreadable(trail_id):
            raise OSError("library unreadable")

        monkeypatch.setattr(library, "successes", unreadable)
        assert cerebellum.invalidate_for_skill(skill_id) is True
        with get_connection(db) as conn:
            (stamp,) = conn.execute(
                "SELECT decompiled_at_successes FROM compiled_playbooks"
            ).fetchone()
        assert stamp is None
