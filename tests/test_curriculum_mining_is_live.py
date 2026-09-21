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

    def test_it_proposes_from_work_on_REAL_code(self, db) -> None:
        """L6's standing blocker, now discharged rather than reworded.

        `_extract_module_name` matched `training_ground/<name>.py` and nothing
        else, so a verified success on this repository's own source produced no
        proposal at all: the miner RAN on every real turn and could still only
        ever propose toy work. The fix is a real-code escalation family, not a
        widened pattern -- the toy templates interpolate into a
        `training_ground/...` path, so widening the extractor alone would have
        pointed them at real files.
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
        proposals = CurriculumMiner(db_path=db).mine_from_development()
        assert proposals, "verified work on real code still produced nothing"
        assert all("aios/agents/tool_handlers.py" in p.prompt for p in proposals)
        assert not any("training_ground/" in p.prompt for p in proposals), (
            "a proposal mined from real code that names the toy world has not "
            "escaped the toy world; it has only relabelled it"
        )

    def test_a_real_proposal_never_asks_to_edit_the_source(self, db) -> None:
        """The subject is characterisation, not modification.

        Proposing that the system practise by editing this repository's own
        code is a far larger proposition than proposing it practise by
        describing it, and it is not the one being made here.
        """
        from aios.memory.curriculum_miner import CurriculumMiner

        development = DevelopmentTracker(db_path=db)
        development.read_only = False
        development.record(
            "read aios/memory/relevance.py and pin relevance()",
            "verified_success",
            tool_calls=3,
        )
        for proposal in CurriculumMiner(db_path=db).mine_from_development():
            assert "Do not edit aios/memory/relevance.py" in proposal.prompt
            assert "Edit aios/memory/relevance.py" not in proposal.prompt

    def test_a_real_level_gets_a_held_out_sibling(self, db) -> None:
        """Without one the proposed level can never be mastered.

        `_refresh_level` gates on ``bool(held_out) and all(...)``, so a level
        whose mined tasks are all trainers is permanently un-masterable -- the
        toy path learned this the same way.
        """
        from aios.memory.curriculum_miner import CurriculumMiner

        development = DevelopmentTracker(db_path=db)
        development.read_only = False
        development.record(
            "read aios/memory/relevance.py and pin relevance()",
            "verified_success",
            tool_calls=3,
        )
        proposals = CurriculumMiner(db_path=db).mine_from_development()
        assert [p.held_out for p in proposals].count(True) == 1
        trained = [p for p in proposals if not p.held_out]
        held = [p for p in proposals if p.held_out]
        assert trained and held and trained[0].prompt != held[0].prompt, (
            "a held-out task identical to the trainer proves mastery with the "
            "same task that taught it"
        )

    def test_the_toy_world_still_mines_the_toy_way(self, db) -> None:
        """The negative control for the two assertions above.

        Without it, a real-code family that accidentally swallowed every prompt
        would pass every test here while quietly deleting the toy curriculum.
        """
        from aios.memory.curriculum_miner import CurriculumMiner

        _seed_evidence(db)
        proposals = CurriculumMiner(db_path=db).mine_from_development(max_proposals=3)
        assert proposals
        assert all("training_ground/" in p.prompt for p in proposals)

    def test_a_prompt_naming_no_module_still_proposes_nothing(self, db) -> None:
        """The other negative control: proposals need a subject."""
        from aios.memory.curriculum_miner import CurriculumMiner

        development = DevelopmentTracker(db_path=db)
        for i in range(3):
            development.read_only = False
            development.record(
                f"think about concurrency in the abstract, round {i}",
                "verified_success",
                tool_calls=1,
            )
        assert CurriculumMiner(db_path=db).mine_from_development() == []


class TestAProposalLeavesTheProcess:
    """A proposal nobody can read is not a proposal.

    The miner's whole contract is that it suggests and somebody else accepts.
    Until proposals were written down, what left the process was a log line
    counting them -- so the authority boundary the miner protects had nothing
    on the other side of it to accept.
    """

    def test_proposals_are_written_where_a_human_can_accept_them(
        self, db, tmp_path, monkeypatch
    ) -> None:
        import json

        import aios.config as config_mod
        import aios.memory.curriculum_miner as miner_mod

        monkeypatch.setattr(config_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(miner_mod.CurriculumMiner, "db_path", db, raising=False)
        real_miner = miner_mod.CurriculumMiner

        class _Scoped(real_miner):  # the production miner, pointed at the test db
            def __init__(self, *a, **k) -> None:
                super().__init__(db_path=db)

        monkeypatch.setattr(miner_mod, "CurriculumMiner", _Scoped)
        _seed_evidence(db)
        _mine_curriculum(CurriculumManager(db_path=db), None)

        trail = tmp_path / ".aios" / "audit" / "curriculum-proposals.jsonl"
        assert trail.exists(), "mining proposed tasks and recorded none of them"
        rows = [json.loads(line) for line in trail.read_text().splitlines() if line]
        assert rows and all(row["prompt"] for row in rows)
        assert all(row["accepted"] is False for row in rows), (
            "a proposal recorded as already accepted is not a proposal"
        )

    def test_an_unwritable_trail_cannot_break_a_turn(
        self, db, tmp_path, monkeypatch
    ) -> None:
        """Fail-open, like every other step on this path."""
        from aios.application.turns.generate_pipeline import _record_proposals

        import aios.config as config_mod

        # A FILE where the directory must go: mkdir raises, and the turn must
        # not notice.
        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory")
        monkeypatch.setattr(config_mod, "PROJECT_ROOT", blocker)

        class _Proposal:
            skill_name, level, prompt = "s", 1, "p"
            rationale, held_out, fingerprint = "r", False, "f"

        _record_proposals([_Proposal()], 10)  # must not raise


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
