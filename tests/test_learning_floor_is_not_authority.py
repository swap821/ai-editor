"""What may TEACH the system is not what may let it act unattended.

Those were one question with one answer, and the answer was STRONG. STRONG is
reachable only from a recognized test runner, so every skill whose evidence is
a type-check, a build, or a lint sat under a ceiling below the bar: it could
succeed forever and never promote, and nothing reported it — the counters just
never moved.

Splitting the floors is the fix, and it is also the single most gameable change
in this plan, because "make the number move" and "lower the bar" look identical
from the outside. So most of this file is the bar NOT moving:

* WEAK and NONE cannot promote under any configuration;
* a spoofed ``echo "5 passed"`` is still WEAK;
* a checker that inspected no code (``ruff --version``) is still WEAK;
* earned autonomy still demands STRONG, and a MEDIUM success does not extend
  its streak by one.

The one thing that DOES change is a passing checker promoting a skill. That is
Phase B, and it is one test.
"""

from __future__ import annotations

import pytest

from aios import config
from aios.core.autonomy import AutonomyLedger
from aios.core.verification_strength import (
    VerificationStrength,
    derive_strength,
    learning_floor,
    meets_learning_floor,
    meets_promotion_floor,
)
from aios.memory.db import get_connection, init_memory_db
from aios.memory.skills import SkillMemory

STEPS = ["read_file: src/foo.py", "verify: mypy aios/"]
GOAL = "type-check the package"


@pytest.fixture()
def skills(tmp_path) -> SkillMemory:
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    return SkillMemory(db_path=db)


def _counts(skills: SkillMemory) -> tuple[int, int]:
    with get_connection(skills.db_path) as conn:
        row = conn.execute(
            "SELECT success_count, weak_success_count FROM procedural_skills"
        ).fetchone()
    return int(row["success_count"]), int(row["weak_success_count"])


class TestWhatPhaseBChanges:
    def test_a_passing_checker_now_promotes_a_skill(self, skills) -> None:
        """The whole point: a type-check skill can finally be learned."""
        for _ in range(3):
            skills.record_attempt(
                GOAL, STEPS, success=True, strength=VerificationStrength.MEDIUM
            )

        promotable, weak = _counts(skills)
        assert promotable == 3
        assert weak == 0
        rows = skills.list(status="verified")
        assert rows, "three clean checker runs should verify the skill"

    def test_medium_evidence_is_reachable_only_from_a_real_checker(self) -> None:
        """MEDIUM is not a weaker claim about the same thing — it is a different kind."""
        assert (
            derive_strength(
                passed=True, passed_count=0, failed_count=0, command="mypy aios/"
            )
            is VerificationStrength.MEDIUM
        )


class TestWhatMustNotChange:
    def test_weak_still_cannot_promote(self, skills) -> None:
        skills.record_attempt(
            GOAL, STEPS, success=True, strength=VerificationStrength.WEAK
        )
        promotable, weak = _counts(skills)
        assert (promotable, weak) == (0, 1)

    def test_none_cannot_promote(self) -> None:
        assert not meets_learning_floor(VerificationStrength.NONE)

    def test_a_spoofed_test_summary_is_still_weak(self) -> None:
        """`echo "5 passed"` must not mint anything promotable."""
        strength = derive_strength(
            passed=True,
            passed_count=5,
            failed_count=0,
            command='echo "5 passed"',
        )
        assert strength is VerificationStrength.WEAK
        assert not meets_learning_floor(strength)

    def test_a_hollow_test_run_is_still_weak(self) -> None:
        """A real runner that asserted nothing stays below every floor."""
        strength = derive_strength(
            passed=True, passed_count=0, failed_count=0, command="pytest tests/"
        )
        assert strength is VerificationStrength.WEAK
        assert not meets_learning_floor(strength)

    @pytest.mark.parametrize(
        "command",
        [
            "ruff --version",
            "mypy --version",
            "eslint --help",
            "tsc --version",
            "ruff check --show-settings",
            "ruff -V",
        ],
    )
    def test_a_checker_that_inspected_no_code_is_not_medium(self, command) -> None:
        """The checker-side hollow-run defense.

        Before the floors split this did not matter, because MEDIUM could never
        promote anything. Making MEDIUM the learning floor ACTIVATES the hole —
        which is exactly the kind of latent gap a floor change turns live.
        """
        strength = derive_strength(
            passed=True, passed_count=0, failed_count=0, command=command
        )
        assert strength is VerificationStrength.WEAK, command
        assert not meets_learning_floor(strength)

    def test_a_real_checker_invocation_is_unaffected_by_that_defense(self) -> None:
        """The defense must be narrow enough to leave genuine checks alone."""
        for command in (
            "ruff check aios/",
            "mypy aios/core",
            "npm run lint",
            # `-v` is VERBOSE, not version. Lowercasing the tokens would have
            # collapsed it into `-V` and silently refused a real check.
            "ruff check -v aios/",
            "mypy -v aios/core",
        ):
            assert (
                derive_strength(
                    passed=True, passed_count=0, failed_count=0, command=command
                )
                is VerificationStrength.MEDIUM
            ), command


class TestAuthorityIsUntouched:
    def test_medium_does_not_satisfy_the_authority_floor(self) -> None:
        assert meets_learning_floor(VerificationStrength.MEDIUM)
        assert not meets_promotion_floor(VerificationStrength.MEDIUM), (
            "a passing type-check is a reason to remember a skill, not a reason "
            "to let a write run unattended"
        )

    def test_earned_autonomy_still_requires_strong(self, tmp_path) -> None:
        """The call site that decides whether a YELLOW action stops asking."""
        ledger = AutonomyLedger(db_path=tmp_path / "autonomy.sqlite")
        for _ in range(10):
            ledger.record_outcome(
                "edit_file",
                "training_ground/x.py",
                success=True,
                strength=VerificationStrength.MEDIUM,
            )
        record = ledger.record_outcome(
            "edit_file",
            "training_ground/x.py",
            success=True,
            strength=VerificationStrength.MEDIUM,
        )
        assert record["status"] != "earned", (
            "MEDIUM evidence must never graduate an action class to unattended "
            "execution, however many times it repeats"
        )

    def test_the_autonomy_module_does_not_reach_for_the_learning_floor(self) -> None:
        """An architecture pin, because the next edit is the dangerous one.

        Nothing stops a future change from importing the looser helper here; a
        grep-level assertion is crude, but it fails loudly at exactly the moment
        somebody blurs the authority/learning line again.
        """
        from pathlib import Path

        source = Path(config.PROJECT_ROOT, "aios", "core", "autonomy.py").read_text(
            encoding="utf-8"
        )
        assert "meets_learning_floor" not in source
        assert "meets_promotion_floor" in source


class TestTheFloorItselfCannotBeMisconfiguredDownward:
    def test_a_weak_floor_is_clamped_to_medium(self, monkeypatch) -> None:
        monkeypatch.setattr(config, "LEARNING_PROMOTION_FLOOR", "WEAK")
        assert learning_floor() is VerificationStrength.MEDIUM
        assert not meets_learning_floor(VerificationStrength.WEAK)

    def test_a_none_floor_is_clamped_to_medium(self, monkeypatch) -> None:
        monkeypatch.setattr(config, "LEARNING_PROMOTION_FLOOR", "NONE")
        assert learning_floor() is VerificationStrength.MEDIUM

    def test_garbage_falls_back_to_medium_not_open(self, monkeypatch) -> None:
        monkeypatch.setattr(config, "LEARNING_PROMOTION_FLOOR", "banana")
        assert learning_floor() is VerificationStrength.MEDIUM

    def test_an_operator_may_still_tighten_it(self, monkeypatch) -> None:
        """Configuration can add caution; it can never remove it."""
        monkeypatch.setattr(config, "LEARNING_PROMOTION_FLOOR", "STRONG")
        assert learning_floor() is VerificationStrength.STRONG
        assert not meets_learning_floor(VerificationStrength.MEDIUM)

    def test_tightening_it_really_stops_a_checker_skill_promoting(
        self, skills, monkeypatch
    ) -> None:
        monkeypatch.setattr(config, "LEARNING_PROMOTION_FLOOR", "STRONG")
        skills.record_attempt(
            GOAL, STEPS, success=True, strength=VerificationStrength.MEDIUM
        )
        assert _counts(skills) == (0, 1)


class TestTheMonitorAgreesWithTheWriter:
    """A control whose alarms are false is worse than no control.

    `GovernanceObservation` audits `procedural_skills` for rows that were
    promoted without earning it, by re-deriving the verdict from the stored
    `verification_strength`. If that reader asks a DIFFERENT floor than the
    writer promoted with, every legitimate checker-backed skill is reported as
    a governance violation — the classic "do these two layers agree?" defect,
    which in this repo has twice been the thing that mattered.
    """

    def test_a_medium_skill_row_is_reported_as_earned(self) -> None:
        from aios.application.governance.governance_observation import (
            VerifiedMemoryReader,
        )

        assert VerifiedMemoryReader._earned("MEDIUM") is True

    def test_a_weak_skill_row_is_still_reported_as_unearned(self) -> None:
        from aios.application.governance.governance_observation import (
            VerifiedMemoryReader,
        )

        assert VerifiedMemoryReader._earned("WEAK") is False
        assert VerifiedMemoryReader._earned("NONE") is False
        assert VerifiedMemoryReader._earned(None) is False
        assert VerifiedMemoryReader._earned("banana") is False


class TestTheNoopDefenseCoversTheFlagFamily:
    @pytest.mark.parametrize(
        "command",
        ["ruff --version=1", "mypy --help=all", "eslint --version=2.0"],
    )
    def test_a_valued_meta_flag_is_still_a_noop(self, command) -> None:
        """Checking the flag NAME, not the token.

        A set membership test on the whole token turns the defense into a list
        of the spellings someone happened to think of.
        """
        assert (
            derive_strength(
                passed=True, passed_count=0, failed_count=0, command=command
            )
            is VerificationStrength.WEAK
        ), command


class TestLessonsUseTheSameLearningFloor:
    """Two gates guard one decision; they must not disagree.

    `tool_loop_helpers.confirm` decides whether to CALL the promotion hook, and
    `MistakeMemory.promote` decides whether to honour it. If one asked the
    authority floor and the other the learning floor, the hook would fire and
    the store would silently refuse — a lesson reported as verified in the
    event stream and still pending in the database.
    """

    def test_a_checker_confirmed_lesson_promotes(self, tmp_path) -> None:
        from aios.memory.mistake import MistakeMemory

        db = tmp_path / "m.sqlite"
        init_memory_db(db)
        mistakes = MistakeMemory(db_path=db)
        lesson_id = mistakes.record("t", "TypeError", "c", "f", "l", -0.2)
        mistakes.promote(lesson_id, strength=VerificationStrength.MEDIUM)

        assert mistakes.get(lesson_id)["verification_status"] == "verified", (
            "a lesson recorded when `mypy` failed and confirmed when it passes "
            "has transferred; MEDIUM is the ceiling for checker evidence, so "
            "the authority floor would have made it unconfirmable forever"
        )

    def test_a_weak_confirmation_still_leaves_it_pending(self, tmp_path) -> None:
        from aios.memory.mistake import MistakeMemory

        db = tmp_path / "m.sqlite"
        init_memory_db(db)
        mistakes = MistakeMemory(db_path=db)
        lesson_id = mistakes.record("t", "TypeError", "c", "f", "l", -0.2)
        mistakes.promote(lesson_id, strength=VerificationStrength.WEAK)

        assert mistakes.get(lesson_id)["verification_status"] == "pending"

    def test_the_stream_hook_and_the_store_agree(self) -> None:
        """Both sides of the same decision, checked against each other."""
        from aios.agents import tool_loop_helpers

        promoted: list[int] = []
        pending = [(1, "mypy aios/")]
        list(
            tool_loop_helpers.confirm(
                pending,
                "mypy aios/",
                0,
                promoted.append,
                strength=VerificationStrength.MEDIUM,
            )
        )
        assert promoted == [1]

        promoted.clear()
        pending = [(2, "mypy aios/")]
        list(
            tool_loop_helpers.confirm(
                pending,
                "mypy aios/",
                0,
                promoted.append,
                strength=VerificationStrength.WEAK,
            )
        )
        assert promoted == []
