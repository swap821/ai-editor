"""The nightly prover must gate on harness integrity, never on model score.

nightly.yml states that contract in its own header -- "WHAT IT GATES ON:
harness integrity, never model score ... broken, not that a 0.5b model was
disobedient" -- and already passes ``--lenient``, the prover's supported way to
say it. But every model-obedience check was registered ``hard``, which
``--lenient`` cannot downgrade, so the job failed on a 0.5b model's obedience
and the Nightly was red on **all of its last 60 runs**.

The subtle one was the cerebellum pair. Those assert real machinery, but their
precondition is a promoted skill, which needs the model to have produced
verified successes. Weak model -> no verified success -> no promotion -> no
compiled playbook -> hard failure for a reason that is not the harness's.

These tests pin both directions: what may be downgraded, and what may never be.
"""

from __future__ import annotations

import re

import pytest

from tests.source_rules import executable_source
from tools import learning_loop_prover as prover


def _registrations(kind: str) -> list[str]:
    """Check names registered via ``check.<kind>(`` in the prover source."""
    src = executable_source(prover)
    return re.findall(rf"check\.{kind}\(\s*\n\s*(f?\"[^\"]+\")", src)


def test_model_obedience_checks_are_soft() -> None:
    """A check that asserts the MODEL succeeded must be downgradable.

    Each of these reads the model's own outcome or a promotion that depends on
    it. On a CI-sized model they fail, and failing the job for that is exactly
    what the workflow forbids.
    """
    soft = " ".join(_registrations("soft"))
    for name in (
        "lesson.turn1-verified-success",
        "lesson.fail-then-pass",
        "lesson.reflect-step",
        "lesson.turn2-verified-success",
        "reflex.rep{rep}-verified-success",
        "reflex.rep{rep}-strong",
        "reflex.skill-verified",
    ):
        assert name in soft, f"{name} must be soft so --lenient can downgrade it"


def test_the_mutation_probe_is_never_downgradable() -> None:
    """The negative control is the one check that must always gate.

    `probe.broken-code-fails` asserts that deliberately broken code FAILS
    verification. It holds regardless of model quality -- a weak model cannot
    make broken code pass -- so softening it would remove the only assertion
    standing between this prover and a verifier that rubber-stamps anything.
    """
    assert "probe.broken-code-fails" in " ".join(_registrations("hard"))


def test_hard_checks_are_only_structural() -> None:
    """Nothing model-dependent may sit in the hard set.

    Guards the SET, not today's members: anything added later has to justify
    itself against the same rule.
    """
    hard = _registrations("hard")
    assert hard, (
        "the prover must still have hard checks; a gate that cannot fail is not a gate"
    )
    for name in hard:
        assert "verified-success" not in name, (
            f"{name} asserts a model outcome and must not be hard"
        )
        assert "-strong" not in name, (
            f"{name} asserts model evidence strength and must not be hard"
        )


def test_cerebellum_checks_are_gated_on_promotion() -> None:
    """Hard only when a playbook exists; soft when nothing was promoted.

    Ungated, these failed whenever the model was too weak to promote a skill --
    asserting the replay of a playbook that was never compiled. Gated, the
    guarantee survives exactly where it means something: a playbook that WAS
    compiled and then fails to match or complete still fails the run.
    """
    src = executable_source(prover)
    assert "if promoted:" in src, "the cerebellum assertions must be gated on promotion"
    gated = src.split("if promoted:", 1)[1]
    hard_block = gated.split("else:", 1)[0]
    assert "reflex.cerebellum-match" in hard_block
    # Was `reflex.cerebellum-done` until the Phase 0b containment (2026-09-25):
    # the prover's reflex step is YELLOW, so a correct replay is now withheld.
    assert "reflex.withheld-without-human-approval" in hard_block
    assert "check.hard(" in hard_block, "when a playbook exists the check must be hard"


def test_lenient_downgrades_soft_and_never_hard() -> None:
    """The mechanism itself, independent of which checks use it."""
    lenient = prover.Check(lenient=True)
    lenient.soft("s", False, "model was disobedient")
    assert lenient.passed, "a soft failure must not fail a lenient run"

    lenient_hard = prover.Check(lenient=True)
    lenient_hard.hard("h", False, "harness is broken")
    assert not lenient_hard.passed, "--lenient must never downgrade a hard check"

    strict = prover.Check(lenient=False)
    strict.soft("s", False, "model was disobedient")
    assert not strict.passed, "without --lenient a soft failure still fails"


def _probe(monkeypatch, evidence: list[str], *, lenient: bool) -> "prover.Check":
    monkeypatch.setattr(prover, "run_prompt", lambda *a, **k: {"evidence": evidence})
    monkeypatch.setattr(prover, "log_event", lambda *a, **k: None)
    check = prover.Check(lenient=lenient)
    prover.phase_probe({"probe_test": "lab/test_llp_probe_x.py"}, "run", "model", check)
    return check


def _result(check, name):
    return next((r for r in check.results if r["check"] == name), None)


class TestTheProbeSeparatesNotReachedFromViolated:
    """The nightly failed on "broken code did not fail verification" with a
    0.5b model whose other turns never reached verification. "The model never
    ran verify" and "verify PASSED broken code" are different findings."""

    def test_verification_failing_broken_code_passes(self, monkeypatch) -> None:
        check = _probe(monkeypatch, ["[VERIFY FAIL] 1 failed"], lenient=True)
        assert _result(check, "probe.reached")["ok"]
        assert _result(check, "probe.broken-code-fails")["ok"]

    @pytest.mark.parametrize("lenient", [True, False])
    def test_verification_passing_broken_code_fails_in_every_mode(
        self, monkeypatch, lenient
    ) -> None:
        check = _probe(monkeypatch, ["[VERIFY PASS] 1 passed"], lenient=lenient)
        verdict = _result(check, "probe.broken-code-fails")
        assert verdict["ok"] is False and verdict["soft"] is False
        assert "PASSED broken code" in verdict["detail"]
        assert check.passed is False

    def test_not_reached_is_never_a_pass_of_the_negative_control(
        self, monkeypatch
    ) -> None:
        check = _probe(monkeypatch, [], lenient=True)
        reached = _result(check, "probe.reached")
        assert reached["ok"] is False and reached["downgraded"] is True
        assert "NOT EXERCISED" in reached["detail"]
        assert _result(check, "probe.broken-code-fails") is None, (
            "a probe that never ran must not record a verdict at all"
        )

    def test_a_strict_run_still_fails_when_the_probe_is_not_reached(
        self, monkeypatch
    ) -> None:
        check = _probe(monkeypatch, [], lenient=False)
        assert check.passed is False

    def test_reaching_the_probe_is_soft(self) -> None:
        assert "probe.reached" in " ".join(_registrations("soft"))


def _turn(*, replayed: bool = False, done: bool = False, withheld: bool = True) -> dict:
    events = (["cerebellum_match"] if replayed else []) + (
        ["cerebellum_done"] if done else []
    )
    return {
        "outcome": "verified_success",
        "evidence": ["[VERIFY PASS] 1 passed strength=STRONG"],
        "step_tools": ["verify"],
        "cerebellum_events": events,
        "cerebellum_controls": ["reflex_authority"] if (replayed and withheld) else [],
    }


def _reflex(
    monkeypatch, *, mode: str, replay: dict, ready: bool = True, active=0
) -> "prover.Check":
    turns = iter([_turn(), _turn(), _turn(), replay])
    monkeypatch.setattr(prover, "run_prompt", lambda *a, **k: next(turns))
    monkeypatch.setattr(prover, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(prover, "skill_store_mode", lambda: mode)
    monkeypatch.setattr(prover, "skill_review_ready", lambda marker: ready)
    monkeypatch.setattr(prover, "library_active_count", lambda: active)

    def no_legacy_poll(marker):
        raise AssertionError("a library backend is never asked the legacy question")

    monkeypatch.setattr(
        prover,
        "skill_promoted",
        no_legacy_poll if mode == "library" else (lambda m: False),
    )
    check = prover.Check(lenient=True)
    prover.phase_reflex(
        {"reflex_test": "lab/test_llp_reflex_x.py"}, "20260927T000000", "model", check
    )
    return check


class TestTheProverReadsTheLiveSlotInPilotMode:
    """Operator decision 2026-09-27: redefine the prover against the live slot.
    In pilot mode promotion is review-readiness (activation is the operator's),
    and since #395 a reflex replays there only if the operator activated it."""

    def test_legacy_mode_keeps_the_legacy_question(self, monkeypatch) -> None:
        check = _reflex(monkeypatch, mode="legacy", replay=_turn())
        assert _result(check, "reflex.skill-verified") is not None
        assert _result(check, "reflex.skill-review-ready") is None

    def test_a_library_backend_is_asked_for_review_readiness(self, monkeypatch) -> None:
        check = _reflex(monkeypatch, mode="library", replay=_turn())
        ready = _result(check, "reflex.skill-review-ready")
        assert ready["ok"] and ready["soft"]
        assert _result(check, "reflex.skill-verified") is None
        assert _result(check, "reflex.pilot-no-legacy-reflex")["ok"]
        assert _result(check, "reflex.withheld-without-human-approval") is None

    def test_with_nothing_activated_a_replay_is_a_gate_failure(
        self, monkeypatch
    ) -> None:
        check = _reflex(
            monkeypatch, mode="library", replay=_turn(replayed=True), active=0
        )
        gate = _result(check, "reflex.pilot-no-legacy-reflex")
        assert gate["ok"] is False and gate["soft"] is False
        assert "GATE FAILURE" in gate["detail"]
        assert check.passed is False

    def test_with_nothing_activated_no_replay_passes_hard(self, monkeypatch) -> None:
        check = _reflex(monkeypatch, mode="library", replay=_turn(), active=0)
        gate = _result(check, "reflex.pilot-no-legacy-reflex")
        assert gate["ok"] is True and gate["soft"] is False

    @pytest.mark.parametrize("active", [2, None])
    def test_with_activated_skills_or_an_unknown_count_a_replay_is_reported(
        self, monkeypatch, active
    ) -> None:
        """An activated skill may legitimately match; an unreadable count is
        never taken as zero."""
        check = _reflex(
            monkeypatch, mode="library", replay=_turn(replayed=True), active=active
        )
        gate = _result(check, "reflex.pilot-no-legacy-reflex")
        assert gate["ok"] is False and gate["soft"] is True
        assert "activated skill(s) exist" in gate["detail"]
        withheld = _result(check, "reflex.withheld-without-human-approval")
        assert withheld["ok"] and withheld["soft"] is False

    def test_a_reflex_that_auto_ran_fails_hard(self, monkeypatch) -> None:
        check = _reflex(
            monkeypatch,
            mode="library",
            replay=_turn(replayed=True, done=True, withheld=False),
        )
        withheld = _result(check, "reflex.withheld-without-human-approval")
        assert withheld["ok"] is False and withheld["soft"] is False
        assert check.passed is False

    def test_the_active_count_is_read_from_the_trail_summary(self, monkeypatch) -> None:
        class Resp:
            def __init__(self, body):
                self._body = body

            def raise_for_status(self):
                return None

            def json(self):
                return self._body

        class Session:
            def __init__(self, body):
                self.body = body

            def get(self, path, **kwargs):
                assert path == "/api/v1/development/trails"
                return Resp(self.body)

        monkeypatch.setattr(
            prover, "_session", lambda: Session({"summary": {"verified": 3}})
        )
        assert prover.library_active_count() == 3
        monkeypatch.setattr(prover, "_session", lambda: Session({"trails": []}))
        assert prover.library_active_count() is None, "unknown is not zero"

    def test_the_mode_is_asked_of_the_running_backend(self, monkeypatch) -> None:
        class Resp:
            def __init__(self, body):
                self._body = body

            def raise_for_status(self):
                return None

            def json(self):
                return self._body

        class Session:
            def __init__(self, body):
                self.body = body

            def get(self, path, **kwargs):
                assert path == "/api/v1/development/trails"
                return Resp(self.body)

        monkeypatch.setattr(prover, "_session", lambda: Session({"trails": []}))
        assert prover.skill_store_mode() == "legacy", "a pre-2.4c legacy backend"
        monkeypatch.setattr(
            prover,
            "_session",
            lambda: Session({"trails": [], "pilot": {"mode": "shadow"}}),
        )
        assert prover.skill_store_mode() == "legacy", "shadow read the legacy store"
        monkeypatch.setattr(
            prover,
            "_session",
            lambda: Session({"trails": [], "pilot": {"mode": "pilot"}}),
        )
        assert prover.skill_store_mode() == "library", "a pre-2.4c-B pilot backend"
        monkeypatch.setattr(
            prover,
            "_session",
            lambda: Session({"trails": [], "store": "institutional_skills"}),
        )
        assert prover.skill_store_mode() == "library", "every 2.4c-B backend"
