"""The miner must escalate along the source task's own axis, and seed a held-out.

Two defects, both of which made mined curriculum unable to grow the system:

* `_generate_variants` hardcoded ``_ESCALATION_TEMPLATES["create_and_test"]``,
  so `refactor_and_test` and `extend_and_test` were unreachable dead code. A
  refactor task escalated into a create task; the curriculum could only ever
  get harder along one axis.
* No mined proposal was ever held out. `_refresh_level` gates mastery on
  ``bool(held_out) and all(...)``, so a level with no held-out task is blocked
  forever -- the counters climb and the transition never fires. Nothing
  automatic created one, so mastery was inert out of the box.
"""

from __future__ import annotations

from aios.memory.curriculum_miner import (
    _ESCALATION_TEMPLATES,
    CurriculumMiner,
    _template_family,
)


class TestTemplateFamilyFollowsTheSourceTask:
    def test_a_refactor_source_escalates_as_a_refactor(self) -> None:
        assert (
            _template_family(
                "Edit training_ground/cache.py to refactor the eviction policy "
                "into smaller functions. Then verify that the tests pass."
            )
            == "refactor_and_test"
        )

    def test_an_edit_source_escalates_as_an_extension(self) -> None:
        assert (
            _template_family(
                "Edit training_ground/parser.py to add streaming support. "
                "Then verify that the tests pass."
            )
            == "extend_and_test"
        )

    def test_a_create_source_escalates_as_a_create(self) -> None:
        assert (
            _template_family(
                "Create training_ground/stack.py with a Stack class. "
                "Then verify that the tests pass."
            )
            == "create_and_test"
        )

    def test_refactor_wins_over_the_generic_edit_case(self) -> None:
        """A refactor prompt also contains 'Edit' -- ordering is load-bearing."""
        assert _template_family("Edit x.py to refactor y") == "refactor_and_test"

    def test_every_declared_family_is_reachable(self, tmp_path) -> None:
        """Guards the mapping, not today's strings.

        The original bug was a whole family of templates that no input could
        ever select. A template nobody can reach is not a feature.

        `pin_real_behaviour` is selected one level up -- by the target being
        real, not by the source prompt's verb -- so reaching it means actually
        generating from a real-code source rather than calling
        `_template_family`. Checking only the latter would have declared it
        unreachable while it worked, or reachable while it did not.
        """
        reachable = {
            _template_family("Create training_ground/a.py with a thing."),
            _template_family("Edit training_ground/a.py to refactor a thing."),
            _template_family("Edit training_ground/a.py to add a thing."),
        }
        miner = CurriculumMiner(db_path=tmp_path / "reachable.sqlite")
        real = miner._generate_variants(
            "read aios/memory/relevance.py and pin relevance()",
            "python-general",
            3,
            set(),
        )
        assert real, "the real-code family produced nothing and is unreachable"
        reachable.add("pin_real_behaviour")
        assert reachable == set(_ESCALATION_TEMPLATES), (
            f"unreachable template families: {set(_ESCALATION_TEMPLATES) - reachable}"
        )


class TestHeldOutSeeding:
    def test_variants_include_a_held_out_sibling(self, tmp_path) -> None:
        miner = CurriculumMiner(db_path=tmp_path / "m.sqlite")
        proposals = miner._generate_variants(
            "Create training_ground/stack.py with a Stack class supporting push "
            "and pop. Then create training_ground/test_stack.py with pytest "
            "tests. Then verify that the tests pass.",
            skill_name="python-data-structures",
            target_level=2,
            existing_prompts=set(),
        )
        assert proposals, "the miner should propose something for a create task"
        held = [p for p in proposals if p.held_out]
        assert held, (
            "a level with no held-out task can never be mastered, so mining "
            "only training variants can never grow the system"
        )

    def test_the_held_out_task_is_not_the_training_task(self, tmp_path) -> None:
        """Otherwise mastery is proven by the very task that trained it."""
        miner = CurriculumMiner(db_path=tmp_path / "m.sqlite")
        proposals = miner._generate_variants(
            "Create training_ground/queue.py with a Queue class supporting "
            "enqueue and dequeue. Then create training_ground/test_queue.py "
            "with pytest tests. Then verify that the tests pass.",
            skill_name="python-data-structures",
            target_level=2,
            existing_prompts=set(),
        )
        training = [p for p in proposals if not p.held_out]
        held = [p for p in proposals if p.held_out]
        if not (training and held):
            return
        assert training[0].prompt != held[0].prompt

    def test_held_out_defaults_false_so_existing_callers_are_unchanged(self) -> None:
        from aios.memory.curriculum_miner import CurriculumProposal

        p = CurriculumProposal(
            skill_name="s",
            level=1,
            prompt="p",
            rationale="r",
            source_pattern="sp",
            difficulty_delta="d",
        )
        assert p.held_out is False
