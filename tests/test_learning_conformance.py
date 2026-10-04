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
        """Three WEAK successes must not make a skill review-ready -- so M2 must
        go red. Patched on the library adapter, the store M2 measures."""
        from aios.application.memory.institutional_skills import (
            InstitutionalSkillAdapter,
        )
        from aios.core.verification_strength import VerificationStrength

        real = InstitutionalSkillAdapter.record_attempt

        def weak(
            self,
            goal,
            steps,
            *,
            success,
            principal,
            strength=VerificationStrength.STRONG,
        ):
            return real(
                self,
                goal,
                steps,
                success=success,
                principal=principal,
                strength=VerificationStrength.WEAK,
            )

        monkeypatch.setattr(InstitutionalSkillAdapter, "record_attempt", weak)
        assert lcr.mission_2_skill_verifies(tmp).passed is False

    def test_m1_fails_when_promotion_does_nothing(self, tmp, monkeypatch) -> None:
        from aios.memory.mistake import MistakeMemory

        monkeypatch.setattr(MistakeMemory, "promote", lambda self, mid, **k: None)
        assert lcr.mission_1_lesson_transfers(tmp).passed is False


class TestTheRefusalReelIsAnInvariant:
    def test_every_reel_mission_is_flagged_as_a_refusal(self) -> None:
        report = lcr.run_all()
        reel_ids = {m.mission_id for m in report.reel}
        assert reel_ids == {"R6", "R7", "R8", "R9", "R10"}, reel_ids

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


class TestTheSkillMissionsMeasureTheLibrary:
    """Operator decisions 2026-09-27/28: the ledger's skill missions measure
    the institutional library -- since slice 2.4c-B the only skill store --
    where evidence makes a skill review-ready and only the operator activates
    it."""

    def test_m2_passes_on_review_readiness_not_activation(self, tmp) -> None:
        result = lcr.mission_2_skill_verifies(tmp)
        assert result.passed, result.detail
        assert "review-ready" in result.name and "review_ready=True" in result.detail

    @staticmethod
    def _misreport(monkeypatch, **update) -> None:
        """Make the runner's OWN read of the library report ``update``, while
        the adapter's review-readiness stays real, so each condition of the
        verdict is tested on its own."""
        real = lcr._library

        class Lying:
            def __init__(self, repository) -> None:
                self._repository = repository

            def list_skills(self):
                return tuple(
                    r.model_copy(update=update) for r in self._repository.list_skills()
                )

        def library(tmp):
            adapter, repository = real(tmp)
            return adapter, Lying(repository)

        monkeypatch.setattr(lcr, "_library", library)

    def test_m2_fails_if_evidence_ever_activated_a_skill(
        self, tmp, monkeypatch
    ) -> None:
        self._misreport(monkeypatch, state="active")
        result = lcr.mission_2_skill_verifies(tmp)
        assert result.passed is False
        assert "review_ready=True" in result.detail, "readiness alone must not pass"

    def test_r9_weak_successes_never_count_in_the_library(self, tmp) -> None:
        result = lcr.refusal_9_below_floor_cannot_promote(tmp)
        assert result.passed, result.detail
        assert "success_count=0" in result.detail

    def test_r9_fails_if_a_weak_success_was_counted(self, tmp, monkeypatch) -> None:
        self._misreport(monkeypatch, success_count=2)
        result = lcr.refusal_9_below_floor_cannot_promote(tmp)
        assert result.passed is False
        assert "review_ready=False" in result.detail, "not-ready alone must not pass"

    def test_the_report_names_the_store_measured(self) -> None:
        text = lcr.render(lcr.run_all())
        assert "skill store: library" in text
        assert "operator-activated" in text

    def test_the_reflex_missions_start_from_an_activation(self, tmp) -> None:
        """M3-M5 measure the only reflex that can exist since 2.4c-B."""
        result = lcr.mission_3_skill_compiles(tmp)
        assert result.passed, result.detail
        assert "operator-activated" in result.name

    def test_m3_fails_without_the_activation(self, tmp, monkeypatch) -> None:
        """Positive control: evidence alone must not be able to pass M3."""
        monkeypatch.setattr(lcr, "_operator_activates", lambda repository: None)
        result = lcr.mission_3_skill_compiles(tmp)
        assert result.passed is False
        assert "compiled=0" in result.detail

    def test_m5_fails_if_earning_brings_it_back(self, tmp, monkeypatch) -> None:
        """Positive control: a retirement that does not really suspend the
        skill lets the reflex straight back, and M5 must say so."""
        from aios.application.memory.institutional_skills import (
            InstitutionalSkillAdapter,
        )

        monkeypatch.setattr(
            InstitutionalSkillAdapter,
            "withdraw_reflex_source",
            lambda self, trail_id: True,  # claims the withdrawal, does nothing
        )
        result = lcr.mission_5_decompiled_reflex_recovers(tmp)
        assert result.passed is False
        assert "before re-activation=1" in result.detail

    def test_m5_fails_if_earning_reactivates_the_skill(self, tmp, monkeypatch) -> None:
        """Positive control for the EARNING clause alone: the retirement really
        suspends the skill, but a recorded success puts it back to active --
        the rule this decision replaced, moved into the library."""
        from aios.application.memory.institutional_skills import (
            InstitutionalSkillAdapter,
        )

        real = InstitutionalSkillAdapter.record_attempt

        def earning_restores(self, *args, **kwargs):
            trail = real(self, *args, **kwargs)
            for record in self.repository.list_skills():
                if record.state == "suspended":
                    self.repository.transition_state(
                        record.skill_id, record.version, "human_reviewed"
                    )
                    self.repository.transition_state(
                        record.skill_id, record.version, "active"
                    )
            return trail

        monkeypatch.setattr(
            InstitutionalSkillAdapter, "record_attempt", earning_restores
        )
        result = lcr.mission_5_decompiled_reflex_recovers(tmp)
        assert result.passed is False
        assert "before re-activation=0" in result.detail
        assert "after re-earning=1" in result.detail

    def test_m5_fails_without_the_reactivation(self, tmp, monkeypatch) -> None:
        """Positive control: with no re-activation it must not come back."""
        monkeypatch.setattr(lcr, "_operator_reactivates", lambda repository: None)
        result = lcr.mission_5_decompiled_reflex_recovers(tmp)
        assert result.passed is False
        assert "after re-activation=0" in result.detail

    def test_m5_passes_on_this_tree(self, tmp) -> None:
        result = lcr.mission_5_decompiled_reflex_recovers(tmp)
        assert result.passed, result.detail


def test_the_trail_records_which_store_was_measured(tmp_path, monkeypatch) -> None:
    import json

    trail = tmp_path / "trail.jsonl"
    monkeypatch.setattr(lcr, "TRAIL", trail)
    monkeypatch.setattr(lcr, "MISSIONS", [lcr.refusal_10_evidence_cannot_activate])
    assert lcr.main(["--json"]) == 0
    (row,) = [json.loads(line) for line in trail.read_text().splitlines()]
    assert row["skill_store_mode"] == lcr.SKILL_STORE == "library"
    assert row["reel"] == "1/1"


def test_r10_holds(tmp) -> None:
    result = lcr.refusal_10_evidence_cannot_activate(tmp)
    assert result.passed, result.detail
    assert "refused" in result.detail


def test_r10_fails_if_a_save_could_activate(tmp, monkeypatch) -> None:
    """Positive control: the refusal instrument must be able to see a breach,
    or a green R10 would mean nothing."""
    from aios.domain.learning.repository import SkillRepository

    real_save = SkillRepository.save

    def permissive(self, record):
        if record.state == "active":
            return None  # accepted without complaint
        return real_save(self, record)

    monkeypatch.setattr(SkillRepository, "save", permissive)
    result = lcr.refusal_10_evidence_cannot_activate(tmp)
    assert result.passed is False
    assert "ACCEPTED" in result.detail
