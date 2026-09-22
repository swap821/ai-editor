"""The benchmark must be able to fail, or it is decoration.

Organ 55's third rule is "a lucky pass is a fail", and it applies to the
scoreboard as hard as to the system. A mission that passes because of
something other than the thing it names is a classification accident, and a
suite of those reads exactly like a working loop.

So each test here BREAKS the thing a mission measures and asserts the mission
notices. The M4 case is the one that matters most: it must fail when no reflex
exists, because a mission that passes with and without a compiled playbook is
measuring nothing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tools import learning_conformance_runner as lcr


@pytest.fixture()
def tmp(tmp_path) -> Path:
    return tmp_path


class TestTheMissionsMeasureWhatTheyName:
    def test_m4_fails_when_there_is_no_reflex_to_serve_the_turn(self, tmp) -> None:
        """Without a compiled playbook the LLM must be reached — and raise.

        If this still "passed" with no cerebellum, M4 would be measuring the
        absence of a crash rather than the presence of a reflex.
        """
        from aios.agents.tool_agent import ToolAgent
        from aios.core.autonomy import UNGOVERNED_FIXTURE
        from aios.core.executor import Executor
        from aios.security.gateway import RateLimiter

        llm = lcr.RefusingLLM()
        agent = ToolAgent(
            llm,
            Executor(
                runner=lcr._SilentRunner(),
                rate_limiter=RateLimiter(),
                audit_log=lambda *a, **k: None,
                emergency_stop=UNGOVERNED_FIXTURE,
            ),
            max_iters=2,
            cerebellum=None,  # the thing under test, removed
        )
        with pytest.raises(AssertionError, match="the LLM was called"):
            list(agent.run([{"role": "user", "content": "read README.md"}]))
        assert llm.calls >= 1

    def test_m4_passes_only_with_a_real_compiled_playbook(self, tmp) -> None:
        result = lcr.mission_4_replay_serves_a_turn_with_no_llm(tmp)
        assert result.passed, result.detail
        assert "llm_calls=0" in result.detail

    def test_m2_fails_when_the_successes_are_below_floor(
        self, tmp, monkeypatch
    ) -> None:
        """Three WEAK successes must not verify a skill — so M2 must go red."""
        from aios.core.verification_strength import VerificationStrength
        from aios.memory.skills import SkillMemory

        real = SkillMemory.record_attempt

        def weak(self, goal, steps, *, success, strength=VerificationStrength.STRONG):
            return real(
                self, goal, steps, success=success, strength=VerificationStrength.WEAK
            )

        monkeypatch.setattr(SkillMemory, "record_attempt", weak)
        assert lcr.mission_2_skill_verifies(tmp).passed is False

    def test_m1_fails_when_promotion_does_nothing(self, tmp, monkeypatch) -> None:
        from aios.memory.mistake import MistakeMemory

        monkeypatch.setattr(MistakeMemory, "promote", lambda self, mid, **k: None)
        assert lcr.mission_1_lesson_transfers(tmp).passed is False


class TestTheRefusalReelIsAnInvariant:
    def test_every_reel_mission_is_flagged_as_a_refusal(self) -> None:
        report = lcr.run_all()
        reel_ids = {m.mission_id for m in report.reel}
        assert reel_ids == {"R6", "R7", "R8", "R9"}, reel_ids

    def test_the_reel_passes_on_the_current_tree(self) -> None:
        """These are invariants: a red here means the loop accepted something
        that only looked like evidence, which is worse than a missing feature."""
        report = lcr.run_all()
        failed = [(m.mission_id, m.detail) for m in report.reel if not m.passed]
        assert not failed, failed

    def test_a_failing_reel_mission_makes_the_runner_exit_nonzero(
        self, monkeypatch
    ) -> None:
        """The score may be below full; an accepted falsehood may not."""

        def broken(_tmp):
            return lcr.MissionResult("R6", "broken", False, "forced", refusal=True)

        monkeypatch.setattr(lcr, "MISSIONS", [broken])
        assert lcr.main(["--no-record"]) == 1

    def test_a_failing_product_mission_alone_does_not(self, monkeypatch) -> None:
        def unmet(_tmp):
            return lcr.MissionResult("M9", "not built yet", False, "forced")

        monkeypatch.setattr(lcr, "MISSIONS", [unmet])
        assert lcr.main(["--no-record"]) == 0


class TestTheRunnerReportsHonestly:
    def test_a_crashing_mission_is_a_failure_not_an_omission(self, monkeypatch) -> None:
        """A mission that raises must not silently vanish from the score."""

        def explodes(_tmp):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(lcr, "MISSIONS", [explodes])
        report = lcr.run_all()
        assert len(report.missions) == 1
        assert report.missions[0].passed is False
        assert "kaboom" in report.missions[0].detail

    def test_every_mission_returns_a_reason(self) -> None:
        for m in lcr.run_all().missions:
            assert m.detail.strip(), f"{m.mission_id} reported no reason"

    def test_missions_run_against_a_fresh_store_each_time(self) -> None:
        """Shared state between missions would let one mission's writes
        satisfy another's assertion — the benchmark equivalent of a lucky pass."""
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = lcr.mission_2_skill_verifies(Path(a))
            second = lcr.mission_2_skill_verifies(Path(b))
        assert first.passed and second.passed
        assert "3 STRONG successes" in second.detail, (
            "a second run seeing 6 successes would mean the store leaked "
            "between missions"
        )
