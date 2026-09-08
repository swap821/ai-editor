"""An absent emergency stop is a refusal, not a passed check.

WHY THIS FILE EXISTS. Thirteen guards across ten subsystems were written as:

    if self.emergency_stop is not None:
        self.emergency_stop.assert_operational()

which skips the check entirely when the latch is absent, and lets the
privileged action proceed ungoverned. That shape has already produced four real
defects -- `executor.py`, `deps.py:1079`, `replay_writes.py`,
`policy/kernel.py` -- every one found by a reviewer rather than by a test.

The ratchet in `test_governed_wiring.py` pinned the count so it could not grow.
It never converted them. This file is where each conversion proves itself.

HOW TO READ A TEST HERE. Every test asserts that a subsystem built WITHOUT a
stop refuses to act. Each one therefore FAILS against the pre-conversion code
by construction -- that is the point, and it is how each conversion is shown to
be real rather than merely typed. A conversion whose test passes before the
flip has proven nothing.

The counterpart -- that an ENGAGED stop blocks -- lives with each subsystem's
own suite. Eight of the thirteen had no such test at their own layer, and where
one appeared to exist it was shadowed by an outer service check that blocked
first. Those are added alongside their conversions.
"""

from __future__ import annotations

import pytest

from aios.application.autonomy.governed import GovernedAutonomy
from aios.core.autonomy import UNGOVERNED_FIXTURE, AutonomyLedger
from aios.domain.autonomy import ActionClassKey, AutonomyDecisionStatus


def _key() -> ActionClassKey:
    """A narrow action class in the sandbox -- the kind autonomy may be earned for.

    Mirrors the shape `tests/test_governed_autonomy.py` already uses, so a
    refusal here cannot be blamed on an unusual key.
    """
    return ActionClassKey(
        project_id="proj-1",
        action_type="edit_file",
        tool="edit_file",
        target="training_ground/example.py",
        path_class="training_ground/*.py",
        verification_plan_digest="verify-plan-1",
        policy_version="policy-1",
        model_id="local:model-1",
        data_classification="PROJECT_INTERNAL",
    )


def _ledger(tmp_path) -> AutonomyLedger:
    return AutonomyLedger(
        db_path=tmp_path / "autonomy.db", emergency_stop=UNGOVERNED_FIXTURE
    )


def test_governed_autonomy_refuses_when_no_stop_is_wired(tmp_path) -> None:
    """THE BAR for this slice.

    A `GovernedAutonomy` built with no latch cannot be halted by anyone. It must
    therefore never return ALLOW -- not because the action is wrong, but because
    nothing could stop it if it were.

    Against the old `if self.emergency_stop is not None:` guard this test fails:
    the check is skipped and evaluation proceeds to its normal verdict.
    """
    autonomy = GovernedAutonomy(
        ledger=_ledger(tmp_path),
        enabled=True,
        production_gate_open=True,
        emergency_stop=None,
    )

    decision = autonomy.evaluate(_key(), enabled=True)

    assert decision.status is AutonomyDecisionStatus.DENY
    assert "EMERGENCY_STOP_ENGAGED" in decision.reason_codes


def test_the_explicit_fixture_opt_out_still_evaluates(tmp_path) -> None:
    """The opt-out has to keep working, or every caller is forced to lie.

    `UNGOVERNED_FIXTURE` is the one way to say "this caller deliberately has no
    stop". If it were refused too, the only way to test anything would be to
    build a fake latch, and the sentinel would be decoration.
    """
    autonomy = GovernedAutonomy(
        ledger=_ledger(tmp_path),
        enabled=True,
        production_gate_open=True,
        emergency_stop=UNGOVERNED_FIXTURE,
    )

    decision = autonomy.evaluate(_key(), enabled=True)

    assert "EMERGENCY_STOP_ENGAGED" not in decision.reason_codes


def test_an_engaged_stop_still_denies(tmp_path) -> None:
    """The behaviour that already worked must survive the conversion.

    Converting a guard is only safe if the case it already handled keeps
    working; otherwise a fail-closed default could mask a broken engaged path.
    """

    class _Engaged:
        def assert_operational(self) -> None:
            raise RuntimeError("emergency stop engaged")

    autonomy = GovernedAutonomy(
        ledger=_ledger(tmp_path),
        enabled=True,
        production_gate_open=True,
        emergency_stop=_Engaged(),
    )

    decision = autonomy.evaluate(_key(), enabled=True)

    assert decision.status is AutonomyDecisionStatus.DENY
    assert "EMERGENCY_STOP_ENGAGED" in decision.reason_codes


def test_a_latch_that_is_not_a_latch_is_refused(tmp_path) -> None:
    """An object that cannot be asked is not evidence that nothing is wrong.

    `stop_permits_autonomy` denies on ANY exception, including AttributeError
    from something that is simply not a stop. Wiring the wrong object is a
    wiring bug, and a wiring bug must not read as permission.
    """
    autonomy = GovernedAutonomy(
        ledger=_ledger(tmp_path),
        enabled=True,
        production_gate_open=True,
        emergency_stop=object(),
    )

    decision = autonomy.evaluate(_key(), enabled=True)

    assert decision.status is AutonomyDecisionStatus.DENY


@pytest.mark.parametrize("absent", [None, object()])
def test_refusal_does_not_depend_on_the_feature_flag(tmp_path, absent) -> None:
    """An ungoverned caller is refused even with autonomy switched off.

    Belt and braces: the refusal must come from the stop check, not fall out of
    some later flag that happens to be false in this fixture. If the flag were
    doing the work, the test would pass for the wrong reason.
    """
    autonomy = GovernedAutonomy(
        ledger=_ledger(tmp_path),
        enabled=False,
        production_gate_open=False,
        emergency_stop=absent,
    )

    decision = autonomy.evaluate(_key(), enabled=False)

    assert decision.status is AutonomyDecisionStatus.DENY
    assert "EMERGENCY_STOP_ENGAGED" in decision.reason_codes
