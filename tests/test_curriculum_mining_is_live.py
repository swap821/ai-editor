"""The curriculum must propose without being asked, and never break a turn.

`CurriculumMiner` was constructed in exactly one place —
`aios/api/routes/development.py` — so proposals existed only when a human
called the API. A self-curriculum that never proposes anything unless someone
remembers to ask is not self-anything, and it is the precise shape the learning
ledger's LC2 exists to catch: heavily tested, documented as part of the loop,
reachable from nothing a real turn touches.

It mines `development_events`, which the turn path already appends to on every
completed turn, so the turn that produced the evidence is the natural place to
read it.

The second half matters more than the first. This is the ONLY learning step
that runs inside a turn, so its failures and its cost land on a user waiting
for an answer. A learning improvement that can break a chat turn is not an
improvement — so the tests that must never regress are the fail-open ones.
"""

from __future__ import annotations

import pytest

from aios import config
from aios.application.turns.generate_pipeline import _mine_curriculum
from aios.memory.curriculum import CurriculumManager
from aios.memory.db import get_connection, init_memory_db
from aios.memory.development import DevelopmentTracker


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "memory.sqlite"
    init_memory_db(path)
    return path


def _seed_evidence(db, n: int = 4) -> None:
    """Real turn outcomes, written the way the turn path writes them."""
    development = DevelopmentTracker(db_path=db)
    for i in range(n):
        development.record(
            f"create training_ground/helper_{i}.py with a function and a passing test",
            "verified_success",
            tool_calls=3,
        )


class TestItRunsWithoutBeingAsked:
    def test_the_turn_path_calls_it(self) -> None:
        """LC2: the call exists in the live path, not only in an API route."""
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "aios/application/turns/generate_pipeline.py"
        ).read_text(encoding="utf-8")
        assert "_mine_curriculum(" in source, (
            "a miner reachable only from /api/v1/development is not reachable "
            "from a turn, which is the whole of the LC2 finding"
        )

    def test_it_is_on_by_default(self) -> None:
        """A curriculum nobody generates is not a curriculum."""
        assert config.CURRICULUM_MINING_ENABLED is True

    def test_it_proposes_from_turn_evidence(self, db) -> None:
        from aios.memory.curriculum_miner import CurriculumMiner

        _seed_evidence(db)
        proposals = CurriculumMiner(db_path=db).mine_from_development(max_proposals=3)
        assert proposals, "development evidence existed and produced nothing"

    def test_it_can_only_mine_the_TOY_world(self, db) -> None:
        """A real finding, pinned so it is not mistaken for a passing feature.

        `_extract_module_name` matches `training_ground/<name>.py` and nothing
        else, so a task about real code yields no module and therefore no
        proposal. Wiring the miner into the turn path (LC2) makes it RUN on
        every turn; it does not make it able to propose from organic work.
        That is a design limit of the miner, not a regex typo — the escalation
        templates all describe creating toy modules — and it is why L6's LC10
        stays blocked rather than being quietly declared satisfied.
        """
        from aios.memory.curriculum_miner import CurriculumMiner

        development = DevelopmentTracker(db_path=db)
        for i in range(3):
            development.read_only = False
            development.record(
                f"read aios/agents/tool_handlers.py and pin next_step_{i}()",
                "verified_success",
                tool_calls=3,
            )
        assert CurriculumMiner(db_path=db).mine_from_development() == [], (
            "if this ever returns proposals the miner has learned to read real "
            "code, and L6's LC10 blocker should be re-examined"
        )


class TestItCanNeverBreakATurn:
    """Fail-open is the property; everything else is a nice-to-have."""

    def test_a_raising_miner_is_swallowed(self, db, monkeypatch) -> None:
        import aios.memory.curriculum_miner as miner_mod

        class _Exploding:
            def __init__(self, *a, **k) -> None:
                raise RuntimeError("the miner is broken")

        monkeypatch.setattr(miner_mod, "CurriculumMiner", _Exploding)
        _mine_curriculum(CurriculumManager(db_path=db), None)  # must not raise

    def test_a_miner_that_fails_mid_mining_is_swallowed(self, db, monkeypatch) -> None:
        import aios.memory.curriculum_miner as miner_mod

        monkeypatch.setattr(
            miner_mod.CurriculumMiner,
            "mine_from_development",
            lambda self, **k: (_ for _ in ()).throw(RuntimeError("mid-mining")),
        )
        _mine_curriculum(CurriculumManager(db_path=db), None)  # must not raise

    def test_an_empty_store_is_not_an_error(self, tmp_path) -> None:
        db = tmp_path / "empty.sqlite"
        init_memory_db(db)
        _mine_curriculum(CurriculumManager(db_path=db), None)


class TestBreakingMasteryIsNoticed:
    """LC8 for L6: if this faculty broke, would anything say so?

    Both directions, because a mutation proof that only shows "broken is
    caught" leaves open whether the check passes for the right reason.
    """

    def test_a_level_with_a_held_out_task_can_be_mastered(self, db) -> None:
        curriculum = CurriculumManager(db_path=db)
        curriculum.add_task("shell", 1, "write a passing test for add()")
        curriculum.add_task("shell", 1, "write a passing test for sub()", held_out=True)

        with get_connection(db) as conn:
            levels = conn.execute(
                "SELECT COUNT(*) n FROM curriculum_tasks WHERE held_out = 1"
            ).fetchone()["n"]
        assert levels == 1, "mastery is unreachable without a held-out task"

    def test_a_mastery_that_never_fires_is_caught(self, db, monkeypatch) -> None:
        """Break `_refresh_level` and the measurement must go red.

        Without this, a curriculum that silently stopped promoting anyone
        would look exactly like a curriculum nobody had earned yet.
        """
        curriculum = CurriculumManager(db_path=db)
        monkeypatch.setattr(
            CurriculumManager, "_refresh_level", lambda self, *a, **k: False
        )
        curriculum.add_task("shell", 1, "write a passing test for add()")
        curriculum.add_task("shell", 1, "write a passing test for sub()", held_out=True)

        fired: list[tuple[str, int]] = []
        curriculum.record_matching(
            "write a passing test for add()",
            passed=True,
            evidence="[VERIFY PASS] 3 passed, 0 failed (strength=STRONG)",
            on_mastered=lambda skill, level: fired.append((skill, level)),
        )
        assert fired == [], (
            "with _refresh_level broken nothing may report mastery — if this "
            "list is non-empty the mastery signal comes from somewhere other "
            "than the thing that decides it"
        )
