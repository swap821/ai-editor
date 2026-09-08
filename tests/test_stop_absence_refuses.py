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

import ast
import asyncio
import itertools
from pathlib import Path

import pytest

from aios.application.autonomy.governed import GovernedAutonomy
from aios.application.intelligence.gateway import (
    complete_compatibility_intelligence_request,
    route_intelligence_request,
    stream_compatibility_intelligence_request,
    stream_intelligence_request,
    stream_structured_intelligence_request,
)
from aios.application.governance import (
    AmendmentError,
    EmergencyStopController,
    EmergencyStopError,
    activate_amendment,
    propose_amendment,
)
from aios.domain.governance.constitution import build_constitution_snapshot
from aios.application.workers.foundry import UnknownWorkerStrategy, WorkerFoundry
from aios.application.workers.scheduler import WorkerScheduler
from aios.core.autonomy import UNGOVERNED_FIXTURE, AutonomyLedger
from aios.domain.missions.mission_contract import MissionContract
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


# ---------------------------------------------------------------------------
# Slice 2 -- aios/application/intelligence/gateway.py
#
# Three guards, and the shared one (`_validate_and_compile`) sits in front of
# EVERY entrance: route, stream, and stream_structured all reach the model
# through it. `stream_structured` had no engaged-stop test of its own, so the
# parametrisation below is the first thing that covers it at all.
# ---------------------------------------------------------------------------

_GATEWAY_FIELDS: dict[str, object] = {
    "request_id": "req-1",
    "operator_identity_digest": "operator-digest",
    "constitution_digest": "c" * 64,
    "goal": "summarize the incident",
    "desired_outcome": "a short, accurate summary",
    "target": "local",
    "delegated_authority_summary": "advisory only, no write authority",
}


#: The compiler persists each compiled context and the request_id is UNIQUE, so
#: a shared literal makes the second test in a run fail on the database rather
#: than on the thing it is testing.
_REQUEST_IDS = itertools.count()


def _gateway_call(entrance, **overrides):
    fields = dict(_GATEWAY_FIELDS)
    fields["request_id"] = f"req-absence-{next(_REQUEST_IDS)}"
    fields.update(overrides)
    return entrance(**fields)


@pytest.mark.parametrize(
    "entrance",
    [
        route_intelligence_request,
        stream_intelligence_request,
        stream_structured_intelligence_request,
    ],
    ids=["route", "stream", "stream_structured"],
)
def test_every_gateway_entrance_refuses_when_no_stop_is_wired(entrance) -> None:
    """THE BAR for slice 2, across all three shared-guard entrances.

    A gateway request that cannot be halted must not reach a model. The old
    `if emergency_stop is not None:` asked no question at all when nothing was
    wired, and `_validate_and_compile` is the single point every entrance passes
    through -- so one absent latch ungoverned all three.

    The model callback records into `calls`: a refusal that still invoked the
    model would be worse than no refusal, because it would look safe in a log.
    """
    calls: list[str] = []

    def _model_call(*_args, **_kwargs):
        calls.append("invoked")
        return "should never run"

    with pytest.raises(Exception):
        _gateway_call(entrance, model_call=_model_call, emergency_stop=None)

    assert calls == [], "the model was reached despite an ungoverned request"


@pytest.mark.parametrize(
    "entrance",
    [
        stream_compatibility_intelligence_request,
        complete_compatibility_intelligence_request,
    ],
    ids=["stream_compatibility", "complete_compatibility"],
)
def test_the_compatibility_entrances_refuse_when_no_stop_is_wired(entrance) -> None:
    """The anonymous local-only entrances carry their own copies of the guard.

    They do not route through `_validate_and_compile`, so fixing the shared one
    would have left these two ungoverned -- the reason this slice is three
    guards rather than one.
    """
    calls: list[str] = []

    def _model_call(*_args, **_kwargs):
        calls.append("invoked")
        yield "should never run"

    with pytest.raises(Exception):
        entrance(
            request_id=f"req-compat-{next(_REQUEST_IDS)}",
            target="local",
            model_call=_model_call,
            emergency_stop=None,
        )

    assert calls == []


def test_the_gateway_still_reports_an_engaged_stop_as_such(tmp_path) -> None:
    """Converting must not blur WHY a request was refused.

    "No latch is wired" is a wiring bug and "the operator engaged the stop" is a
    deliberate halt. They deserve different exceptions, and the API turns them
    into different responses. `require_wired` preserves the engaged path's own
    `EmergencyStopError` rather than collapsing both into one refusal -- which
    is why this slice does not use `stop_permits_autonomy`, whose boolean return
    would have thrown that distinction away.
    """
    from aios.application.governance import EmergencyStopHooks
    from aios.domain.governance import EmergencyStopRequest

    stopped = EmergencyStopController(
        tmp_path / "emergency.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda: None,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda reason: None,
        ),
    )
    stopped.engage(
        EmergencyStopRequest(
            operator_id="operator-1",
            authentication_event_id="auth-1",
            reason="test",
        )
    )

    with pytest.raises(EmergencyStopError):
        _gateway_call(
            route_intelligence_request,
            model_call=lambda ctx: "should never run",
            emergency_stop=stopped,
        )


def test_the_gateway_accepts_the_explicit_fixture_opt_out() -> None:
    """Unit fixtures must still be able to say "deliberately ungoverned"."""
    result = _gateway_call(
        route_intelligence_request,
        model_call=lambda ctx: f"summary of: {ctx.goal}",
        emergency_stop=UNGOVERNED_FIXTURE,
    )

    assert "summarize the incident" in result.output


# ---------------------------------------------------------------------------
# Slice 3 -- aios/application/governance/amendment_authority.py
#
# Constitutional amendment ACTIVATION. Slice 27 named this a required
# emergency-stop boundary, and the guard that was written for it skipped
# itself whenever nothing was wired.
# ---------------------------------------------------------------------------


def _unratified_proposal():
    """A proposal that could never legitimately activate.

    Deliberately NOT ratified, which lets the proof below distinguish the two
    refusals by TYPE instead of building the whole ratification chain: the stop
    check runs FIRST, so a converted guard refuses with its own error while the
    old one fell through to `AmendmentError("cannot activate ...")`.
    """
    return propose_amendment(
        proposal_id="amend-absence-1",
        target_articles=("router_max_cost policy",),
        proposed_diff="raise router_max_cost from low to high",
        motivation="unblock a legitimate high-cost task class",
        migration_plan="no data migration needed",
        rollback_plan="revert router_max_cost",
        proposed_by="model:gemini-review",
        proposer_type="model",
    )


def test_amendment_activation_refuses_when_no_stop_is_wired() -> None:
    """THE BAR for slice 3.

    Amending the constitution while nothing can halt you is the most consequential
    ungoverned action on this list -- it is the mechanism that could unfreeze the
    security spine.

    Proved by TYPE rather than by outcome: pre-conversion this same call raises
    `AmendmentError("cannot activate")`, because the stop check quietly passed
    and the status check did the refusing. Post-conversion the stop check refuses
    first, which is the whole point -- an ungovernable caller is turned away
    before the request is even considered on its merits.
    """
    snapshot = build_constitution_snapshot(ratified_by_operator_id="operator:abc")

    with pytest.raises(RuntimeError) as raised:
        activate_amendment(
            _unratified_proposal(),
            previous_snapshot=snapshot,
            emergency_stop=None,
        )

    assert not isinstance(raised.value, AmendmentError), (
        "refused on the proposal's merits, not on being ungovernable -- "
        "the stop check did not run first"
    )
    assert "without an emergency stop" in str(raised.value)


def test_amendment_activation_accepts_the_explicit_fixture_opt_out() -> None:
    """With the opt-out stated, the ordinary refusal is reached again.

    This pins that the conversion did not simply break activation: the same call
    still fails on its merits, with the merits-based error, once the caller has
    said out loud that it is deliberately ungoverned.
    """
    snapshot = build_constitution_snapshot(ratified_by_operator_id="operator:abc")

    with pytest.raises(AmendmentError, match="cannot activate"):
        activate_amendment(
            _unratified_proposal(),
            previous_snapshot=snapshot,
            emergency_stop=UNGOVERNED_FIXTURE,
        )


# ---------------------------------------------------------------------------
# Slice 4 -- aios/application/workers/{scheduler,foundry}.py
#
# One slice for two guards because they are one path: `WorkerFoundry` builds
# its own `WorkerScheduler` and hands its stop down, so converting either alone
# would leave the pair half-governed. Neither had ANY engaged-stop test.
# ---------------------------------------------------------------------------


def _worker_contract(mission_id: str = "mission-absence") -> MissionContract:
    return MissionContract(
        mission_id=mission_id,
        operator_id="operator-1",
        goal="inspect a bounded project",
        worker_type="deterministic",
        created_by="queen:planner",
    )


def test_the_worker_foundry_refuses_to_run_when_no_stop_is_wired() -> None:
    """THE BAR for slice 4, foundry half.

    `run()` selects a strategy and dispatches a worker. A foundry nobody can
    halt must not do that -- and the old guard asked no question at all when
    nothing was wired, which is the default `WorkerFoundry()` constructor.
    """

    async def scenario() -> None:
        foundry = WorkerFoundry()

        with pytest.raises(RuntimeError, match="without an emergency stop"):
            await foundry.run(_worker_contract())

        assert foundry.scheduler.snapshot().active == 0, (
            "a worker was admitted despite the foundry being ungovernable"
        )

    asyncio.run(scenario())


def test_the_scheduler_refuses_to_admit_work_when_no_stop_is_wired() -> None:
    """THE BAR for slice 4, scheduler half.

    Converting the foundry alone would not cover this: the scheduler is reached
    directly too, and it carries its own copy of the guard.
    """
    scheduler = WorkerScheduler(max_active=1, max_per_mission=1)

    with pytest.raises(RuntimeError, match="without an emergency stop"):
        scheduler._assert_operational()


def test_the_worker_pair_accepts_the_explicit_fixture_opt_out() -> None:
    """The foundry hands its stop DOWN to the scheduler it builds.

    So stating the opt-out once at the foundry has to satisfy both halves;
    otherwise every worker fixture would need to say it twice.
    """

    async def scenario() -> None:
        foundry = WorkerFoundry(emergency_stop=UNGOVERNED_FIXTURE)

        # Reaches strategy selection rather than the stop check -- which is the
        # ordinary refusal for an unknown strategy, not a governance refusal.
        with pytest.raises(UnknownWorkerStrategy):
            await foundry.run(_worker_contract(), strategy="not-a-worker")

        foundry.scheduler._assert_operational()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# A guard on this file itself
# ---------------------------------------------------------------------------


def test_this_file_still_contains_ungoverned_constructions() -> None:
    """The proofs here depend on NOT declaring the opt-out. Keep it that way.

    Not hypothetical. Converting these guards means adding
    `emergency_stop=UNGOVERNED_FIXTURE` to ~200 test constructions, which is
    done by an AST sweep -- and a sweep is blind to intent. On 2026-09-08 it ran
    across `tests/` and helpfully declared the opt-out at two constructions IN
    THIS FILE, where the absence is the entire point. Both proofs went on
    passing, having stopped testing anything.

    That is the failure mode this pass is most exposed to: adding the sentinel
    everywhere is mechanically identical to opting the suite out of the control
    being added, and the one place it is fatal is the file that proves the
    control works.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))

    def names_a_real_stop(call: ast.Call) -> bool:
        for kw in call.keywords:
            if kw.arg != "emergency_stop":
                continue
            # `emergency_stop=None` is an ungoverned construction stated out
            # loud -- which is exactly what several proofs here pass on purpose.
            return not (isinstance(kw.value, ast.Constant) and kw.value.value is None)
        return False

    governed = {
        "WorkerFoundry",
        "WorkerScheduler",
        "GovernedAutonomy",
        "MissionService",
        "PromotionAuthority",
        "CouncilOrchestrator",
        "Executor",
    }
    built: dict[str, list[bool]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None)
            if name in governed:
                built.setdefault(name, []).append(names_a_real_stop(node))

    assert built, "this file no longer constructs anything governed"

    # PER CLASS, not merely somewhere in the file. The first version asked only
    # whether SOME ungoverned construction survived, and a sweep that neutered
    # both worker proofs still passed it, kept satisfied by unrelated
    # `GovernedAutonomy(emergency_stop=None)` calls. A guard that cannot fail on
    # the thing that actually happened is decoration.
    fully_swept = sorted(name for name, calls in built.items() if all(calls))

    assert not fully_swept, (
        f"every construction of {fully_swept} in this file now declares a stop, "
        "so nothing here proves an absent one is refused. A sweep has neutered "
        "these proofs -- restore them rather than deleting this test."
    )
