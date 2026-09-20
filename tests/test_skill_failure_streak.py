"""One flake must not be a life sentence — and recovery must be earned.

Reflex compilation was gated on a skill having ZERO failures in its lifetime.
`failure_count` only ever grows, so the guard was unrecoverable by
construction: an arc that failed once in June could succeed a hundred times
afterwards and still never compile, with nothing anywhere reporting why. It
read as a high standard; it was actually a trapdoor.

`consecutive_failures` replaces it — failures since the last success, the same
shape the replay side already uses to decompile. These tests pin the counter's
behaviour at the source, because the compile guard is only as honest as the
number it reads.
"""

from __future__ import annotations

import json

import pytest

from aios.core.verification_strength import VerificationStrength
from aios.memory.db import get_connection, init_memory_db
from aios.memory.skills import SkillMemory

STEPS = ["read_file: src/foo.py", "verify: pytest tests/"]
GOAL = "run the test suite"


@pytest.fixture()
def skills(tmp_path) -> SkillMemory:
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    return SkillMemory(db_path=db)


def _streak(skills: SkillMemory) -> int:
    with get_connection(skills.db_path) as conn:
        row = conn.execute(
            "SELECT consecutive_failures, failure_count FROM procedural_skills"
        ).fetchone()
    return int(row["consecutive_failures"])


def _lifetime_failures(skills: SkillMemory) -> int:
    with get_connection(skills.db_path) as conn:
        row = conn.execute("SELECT failure_count FROM procedural_skills").fetchone()
    return int(row["failure_count"])


def test_a_first_failure_starts_the_streak(skills) -> None:
    skills.record_attempt(GOAL, STEPS, success=False)
    assert _streak(skills) == 1


def test_failures_accumulate(skills) -> None:
    for _ in range(3):
        skills.record_attempt(GOAL, STEPS, success=False)
    assert _streak(skills) == 3


def test_a_success_clears_the_streak_but_not_the_lifetime_tally(skills) -> None:
    """Both numbers stay true: one is history, the other is current condition."""
    skills.record_attempt(GOAL, STEPS, success=False)
    skills.record_attempt(GOAL, STEPS, success=True)

    assert _streak(skills) == 0
    assert _lifetime_failures(skills) == 1, (
        "clearing the streak must not erase the failure from the record -- the "
        "lifetime tally is still what `verified` status is computed from"
    )


def test_a_weak_success_also_clears_the_streak(skills) -> None:
    """A below-floor green is not a failure.

    The promotion floor decides what counts as EVIDENCE; this counter only
    answers 'did the arc just break?'. Conflating the two would quietly make
    the floor stricter than it is written to be.
    """
    skills.record_attempt(GOAL, STEPS, success=False)
    skills.record_attempt(GOAL, STEPS, success=True, strength=VerificationStrength.WEAK)

    assert _streak(skills) == 0


def test_a_failure_after_successes_restarts_the_streak(skills) -> None:
    for _ in range(3):
        skills.record_attempt(GOAL, STEPS, success=True)
    skills.record_attempt(GOAL, STEPS, success=False)

    assert _streak(skills) == 1


def test_a_skill_that_only_ever_succeeded_has_no_streak(skills) -> None:
    skills.record_attempt(GOAL, STEPS, success=True)
    assert _streak(skills) == 0
    assert _lifetime_failures(skills) == 0


def test_merging_two_fragments_keeps_the_worst_recent_record(tmp_path) -> None:
    """Counts add across fragments; "failures since the last success" does not.

    Consolidation sums successes and failures, but the keeper's streak is not
    the arc's streak — a sibling fragment whose last runs failed is part of the
    same arc. Taking the keeper's 0 would let an arc that has not had a clean
    run compile a reflex immediately, on the strength of a row that merely
    happens to be the keeper.
    """
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    skills = SkillMemory(db_path=db)
    skills.record_attempt(GOAL, STEPS, success=True)

    with get_connection(db) as conn:
        row = conn.execute("SELECT signature_v2 FROM procedural_skills").fetchone()
        # The unique index exists to PREVENT two active fragments sharing an
        # arc; a database written before it was added can still hold them, and
        # that is exactly the case consolidation is for.
        conn.execute("DROP INDEX IF EXISTS idx_skills_active_sig_v2")
        conn.execute(
            "INSERT INTO procedural_skills "
            "(signature, signature_v2, goal_pattern, steps_json, status, "
            " success_count, failure_count, consecutive_failures) "
            "VALUES ('other', ?, ?, ?, 'candidate', 0, 2, 2)",
            (str(row["signature_v2"]), GOAL, json.dumps(STEPS)),
        )

    init_memory_db(db)  # runs consolidation

    with get_connection(db) as conn:
        keeper = conn.execute(
            "SELECT consecutive_failures FROM procedural_skills "
            "WHERE status != 'superseded'"
        ).fetchone()
    assert int(keeper["consecutive_failures"]) == 2
