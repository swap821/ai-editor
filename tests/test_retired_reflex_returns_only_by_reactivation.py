"""A reflex the machine retired comes back ONLY when the operator re-activates it.

Operator decision, 2026-09-29. Before it, a retired (decompiled) reflex came
back once its skill had earned more successes than it had when it was retired
-- inside the operator's original activation, but with no human seeing it
again. Now every machine retirement (a permanent abstention, a streak of
replay failures, a demoted source) suspends the skill in the institutional
library -- ``active -> suspended``, an automatic, reviewable withdrawal the
emergency stop allows -- and retires the row. Only the operator's
capability-backed re-activation (``suspended -> human_reviewed -> active``)
brings it back; earning more restores nothing.

If the suspension cannot be recorded the row stays ``decompiled``, which blocks
its arc outright, and each compile sweep retries the suspension. Nothing in
this file lets a machine-retired reflex back without the operator.

These tests replaced ``tests/test_decompiled_reflex_can_recover.py``, which
pinned the old rule ("it comes back by re-earning"); its evidence-only
properties (weak greens and failures buy nothing, one live reflex per arc, the
library's count recorded at retirement) are kept below.
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


def _record(library):
    records = [
        r for r in library.repository.list_skills() if r.problem_signature == GOAL
    ]
    return min(records, key=lambda r: r.version)


def _activate(library) -> None:
    """The operator's act, in a test. Live, only the capability route does it."""
    record = _record(library)
    library.repository.transition_state(
        record.skill_id, record.version, "human_reviewed"
    )
    library.repository.transition_state(record.skill_id, record.version, "active")


def _state(library) -> str:
    return str(_record(library).state)


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


def _rows(db) -> list[tuple[str, object]]:
    with get_connection(db) as conn:
        return [
            (str(r["status"]), r["retired_reason"])
            for r in conn.execute(
                "SELECT status, retired_reason FROM compiled_playbooks ORDER BY id"
            ).fetchall()
        ]


def _live_playbooks(db) -> int:
    return sum(1 for status, _ in _rows(db) if status == "compiled")


class TestRetiringSuspendsTheSkill:
    def test_the_skill_is_suspended_and_the_row_retired(self, db, library) -> None:
        _compile_then_retire(db, library)
        assert _state(library) == "suspended"
        [(status, reason)] = _rows(db)
        assert status == "retired"
        assert "operator re-activation" in str(reason)

    def test_the_retirement_records_what_it_had_earned(self, db, library) -> None:
        """Bookkeeping: the library's count at retirement, not a timestamp."""
        _compile_then_retire(db, library)
        with get_connection(db) as conn:
            row = conn.execute(
                "SELECT decompiled_at_successes FROM compiled_playbooks"
            ).fetchone()
        assert row["decompiled_at_successes"] == 3

    @pytest.mark.parametrize("path", ["decompile", "failures"])
    def test_every_machine_retirement_suspends(self, db, library, path) -> None:
        _earn(library)
        _activate(library)
        cerebellum = _cerebellum(db, library)
        assert cerebellum.try_compile_all() == 1
        [pb] = list(cerebellum._cache.values())
        if path == "decompile":
            cerebellum.decompile(pb.id)
        else:
            for _ in range(cerebellum.max_consecutive_failures):
                cerebellum._record_replay_failure(pb.id)
        assert _state(library) == "suspended"
        assert [s for s, _ in _rows(db)] == ["retired"]


class TestOnlyReactivationBringsItBack:
    def test_the_operators_reactivation_brings_it_back(self, db, library) -> None:
        _compile_then_retire(db, library)
        _activate(library)  # suspended -> human_reviewed -> active
        assert _cerebellum(db, library).try_compile_all() == 1
        assert [s for s, _ in _rows(db)] == ["retired", "compiled"]

    def test_new_promotable_successes_do_not_bring_it_back(self, db, library) -> None:
        """The rule this replaced: re-earning used to restore it."""
        _compile_then_retire(db, library)
        _earn(library)  # three more STRONG successes
        assert _cerebellum(db, library).try_compile_all() == 0
        assert _live_playbooks(db) == 0

    def test_recompiling_twice_over_does_not_resurrect_it(self, db, library) -> None:
        _compile_then_retire(db, library)
        for _ in range(5):
            assert _cerebellum(db, library).try_compile_all() == 0

    def test_a_below_floor_success_cannot_buy_it_back(self, db, library) -> None:
        _compile_then_retire(db, library)
        _earn(library, times=3, strength=VerificationStrength.WEAK)
        assert _cerebellum(db, library).try_compile_all() == 0
        assert _live_playbooks(db) == 0

    def test_a_failure_cannot_buy_it_back(self, db, library) -> None:
        _compile_then_retire(db, library)
        library.record_attempt(GOAL, STEPS, success=False)
        assert _cerebellum(db, library).try_compile_all() == 0

    def test_a_live_playbook_is_never_duplicated(self, db, library) -> None:
        """One arc, one live reflex -- the guard's original job, still intact."""
        _earn(library)
        _activate(library)
        assert _cerebellum(db, library).try_compile_all() == 1
        _earn(library)
        assert _cerebellum(db, library).try_compile_all() == 0
        assert len(_rows(db)) == 1


class TestFailClosed:
    """An unrecordable suspension never lets the reflex back on its own."""

    def _unsuspendable(self, library, monkeypatch) -> None:
        def refuse(trail_id):
            raise OSError("library unwritable")

        monkeypatch.setattr(library, "withdraw_reflex_source", refuse)

    def test_the_row_stays_decompiled_and_blocks(
        self, db, library, monkeypatch
    ) -> None:
        _earn(library)
        _activate(library)
        cerebellum = _cerebellum(db, library)
        assert cerebellum.try_compile_all() == 1
        self._unsuspendable(library, monkeypatch)
        [pb] = list(cerebellum._cache.values())
        cerebellum.decompile(pb.id)
        assert _state(library) == "active", "the suspension was refused"
        assert [s for s, _ in _rows(db)] == ["decompiled"]
        _earn(library)
        assert cerebellum.try_compile_all() == 0, "a decompiled row blocks outright"

    def test_a_later_sweep_suspends_it_and_only_reactivation_returns_it(
        self, db, library, monkeypatch
    ) -> None:
        _earn(library)
        _activate(library)
        cerebellum = _cerebellum(db, library)
        assert cerebellum.try_compile_all() == 1
        self._unsuspendable(library, monkeypatch)
        [pb] = list(cerebellum._cache.values())
        cerebellum.decompile(pb.id)
        monkeypatch.undo()  # the library is writable again
        assert cerebellum.try_compile_all() == 0
        assert _state(library) == "suspended"
        assert [s for s, _ in _rows(db)] == ["retired"]
        _activate(library)
        assert cerebellum.try_compile_all() == 1

    def test_an_unreadable_count_at_retirement_is_recorded_as_null(
        self, db, library, monkeypatch
    ) -> None:
        cerebellum, skill_id = _compile_then_retire(db, library)
        with get_connection(db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
        _activate(library)
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
