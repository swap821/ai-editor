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
