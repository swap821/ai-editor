"""GAGOS originates a council mission inside the operator's envelope (2026-11-12).

Move A2b on the aliveness map. A goal the local clerk briefed goes to the
council, but only through one slot of the envelope the operator signed; the
goal is his own words; the mission is verified by the workshop's sandbox; and
nothing here approves or runs it. One deliberation serves every originator.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aios.api.routes import council as council_route
from aios.application.capabilities.envelope import EnvelopeAuthority
from aios.council.sandbox_spec import SANDBOX_KEY
from aios.domain.capabilities.envelope import EnvelopeTerms
from aios.operations import council_origination as co
from tests.test_gagos_envelope import Who, _stop

TEST = "frontend/src/superbrain/lib/tabStore.test.ts"
CODE = "frontend/src/superbrain/lib/tabStore.ts"
WORDS = "Add a test that 100 open and close cycles keep recoverableTabs bounded."


def _task(rel=TEST, also=(), text=WORDS):
    return {"task_id": "gt-0123456789", "rel": rel, "also": list(also), "text": text}


def _briefed(**briefing):
    return {
        "state": "briefed",
        "clerk": {
            "briefing": {
                "goal": "restated by the clerk",
                "constraints": ["invented by a 3b"],
                "done_when": "tests pass",
                **briefing,
            }
        },
    }


def _envelope(tmp_path, *, sign=True, **terms):
    authority = EnvelopeAuthority(
        db_path=tmp_path / "caps.db", emergency_stop=_stop(tmp_path)
    )
    if sign:
        base = {
            "folders": ["frontend/src/superbrain/"],
            "kinds": ["tests"],
            "max_missions": 2,
            "hours": 8,
        }
        authority.sign(EnvelopeTerms.build(**{**base, **terms}), principal=Who())
    return authority


class Council:
    """A council that records what it was asked and answers with *status*."""

    def __init__(self, status="awaiting_approval", raises=None) -> None:
        self.asked = []
        self.status = status
        self.raises = raises

    def __call__(self, request, *, runtime_root):
        self.asked.append(request)
        if self.raises:
            raise self.raises
        return SimpleNamespace(
            report=SimpleNamespace(
                status=self.status, human_summary=f"the King says {self.status}"
            )
        )


def _originate(tmp_path, envelope, council, task=None, seen=None, injection=None):
    return co.originate_goal(
        task or _task(),
        seen if seen is not None else _briefed(),
        envelope=envelope,
        workspace_root=tmp_path / "ws",
        runtime_root=tmp_path / "rt",
        deliberate_with=council,
        detect_injection=lambda text: injection,
    )


def test_a_briefed_goal_inside_the_envelope_goes_to_the_council(tmp_path) -> None:
    envelope, council = _envelope(tmp_path), Council()
    out = _originate(tmp_path, envelope, council)
    assert out["state"] == "awaiting_approval" and out["slot"] == 1
    (request,) = council.asked
    assert request.mission_id == out["mission_id"]
    assert request.goal == WORDS  # his words, never the clerk's restatement
    assert request.allowed_files == [TEST]
    assert request.created_by == co.GAGOS_ORIGINATOR
    assert request.operator_id == "operator-1"  # the envelope's signer
    assert request.metadata[SANDBOX_KEY] == {"files": [TEST]}
    assert request.metadata["envelope"]["slot"] == 1
    assert request.metadata["clerk_briefing"]["constraints"] == ["invented by a 3b"]
    assert envelope.held_slot(out["mission_id"]).slot == 1


@pytest.mark.parametrize("state", ["escalated", "awaiting_clerk", None])
def test_only_a_briefed_goal_originates(tmp_path, state) -> None:
    envelope, council = _envelope(tmp_path), Council()
    out = _originate(
        tmp_path, envelope, council, seen={"state": state} if state else {}
    )
    assert out["state"] == "refused"
    assert council.asked == [] and envelope.status()["missionsUsed"] == 0


def test_no_envelope_no_council(tmp_path) -> None:
    council = Council()
    out = _originate(tmp_path, _envelope(tmp_path, sign=False), council)
    assert out["state"] == "refused"
    assert "has not signed" in out["reason"]
    assert council.asked == []


def test_a_goal_outside_the_envelope_is_refused_with_its_reason(tmp_path) -> None:
    envelope, council = _envelope(tmp_path), Council()
    out = _originate(tmp_path, envelope, council, task=_task(rel=CODE))
    assert out["state"] == "refused"
    assert "allows tests, not 'code'" in out["reason"]
    assert council.asked == []


def test_an_injected_goal_is_refused_before_any_slot(tmp_path) -> None:
    envelope, council = _envelope(tmp_path), Council()
    out = _originate(
        tmp_path, envelope, council, injection="ignore previous instructions"
    )
    assert out["state"] == "refused" and "injection" in out["reason"]
    assert envelope.status()["missionsUsed"] == 0 and council.asked == []


def test_a_blocked_or_failed_deliberation_still_spends_its_slot(tmp_path) -> None:
    envelope = _envelope(tmp_path)
    blocked = _originate(tmp_path, envelope, Council(status="blocked"))
    assert blocked["state"] == "blocked" and "blocked" in blocked["reason"]
    failed = _originate(tmp_path, envelope, Council(raises=RuntimeError("ollama gone")))
    assert failed["state"] == "failed" and "ollama gone" in failed["reason"]
    assert envelope.status()["missionsLeft"] == 0
    out = _originate(tmp_path, envelope, Council())
    assert out["state"] == "refused" and "missions are used" in out["reason"]


def test_mission_kind() -> None:
    assert co.mission_kind([TEST, "frontend/src/a.test.tsx"]) == "tests"
    assert co.mission_kind([TEST, CODE]) == "code"


def test_the_operators_route_deliberates_through_the_same_function(
    monkeypatch, tmp_path
) -> None:
    seen = []
    monkeypatch.setattr(
        co,
        "deliberate",
        lambda request, *, runtime_root, bus=None: seen.append(request),
    )
    request = SimpleNamespace(mission_id="mission-0123456789ab")
    council_route._run_council_deliberation(tmp_path, request)
    assert seen == [request]


def test_a_real_deliberation_passes_a_sandbox_verified_gagos_mission(tmp_path) -> None:
    """The real council: no verification commands, the sandbox declared; the
    Planner does not defer, the Security Queen does not deny, and organ 10
    records the mission awaiting approval."""
    from aios.application.missions.mission_service import MissionAuthority
    from aios.domain.missions.mission_state import MissionState
    from aios.infrastructure.missions.sqlite_mission_repository import (
        SqliteMissionRepository,
    )

    envelope = _envelope(tmp_path)
    workspace = co.gagos_workspace(tmp_path / "council_workspace")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    out = co.originate_goal(
        _task(),
        _briefed(),
        envelope=envelope,
        workspace_root=workspace,
        runtime_root=runtime,
        detect_injection=lambda text: None,
    )
    assert out["state"] == "awaiting_approval", out
    record = SqliteMissionRepository(runtime / council_route.MISSIONS_DB_NAME).get(
        out["mission_id"]
    )
    assert record.state is MissionState.AWAITING_APPROVAL
    assert MissionAuthority  # the authority that recorded it


# -- the hour --------------------------------------------------------------------


@pytest.fixture()
def hour(tmp_path, monkeypatch):
    from aios.maintenance.daily_work import DailyLedger
    from tools import gagos_daily as tool

    monkeypatch.setattr(tool, "goals_through_clerk", lambda: True)
    led = DailyLedger(tmp_path / "ledger.db")
    tid = led.add_task(TEST, WORDS, said_by="operator")
    led.record_intake(tid, {**_briefed(), "reason": "", "mission_request": None})
    return tool, led, tid


def test_the_hour_without_an_envelope_says_why_and_records_nothing(
    hour, tmp_path, capsys
) -> None:
    tool, led, _tid = hour
    asked = []
    tool.missions_hour(
        led,
        tmp_path,
        envelope=_envelope(tmp_path, sign=False),
        originate=lambda task, seen: asked.append(task),
    )
    assert asked == [] and led.originations() == {}
    assert (
        "none originated -- the operator has not signed an envelope"
        in capsys.readouterr().out
    )


def test_the_hour_originates_once_per_spent_slot_and_retries_refusals(
    hour, tmp_path
) -> None:
    tool, led, tid = hour
    envelope = _envelope(tmp_path)
    answers = iter(
        [
            {
                "state": "refused",
                "reason": "the goal fails the injection check: x",
                "mission_id": None,
            },
            {
                "state": "awaiting_approval",
                "reason": "",
                "mission_id": "mission-0123456789ab",
                "envelope_id": "envelope-1",
                "slot": 1,
            },
        ]
    )
    asked = []

    def originate(task, seen):
        asked.append(task["task_id"])
        return next(answers)

    for _ in range(3):
        tool.missions_hour(led, tmp_path, envelope=envelope, originate=originate)
    assert asked == [tid, tid]  # the refusal was tried again; the spent slot never
    assert led.originations()[tid]["state"] == "awaiting_approval"
    lines = "\n".join(tool.task_section(led))
    assert "with the council: mission `mission-0123456789ab` awaiting_approval" in lines


def test_the_hour_is_off_with_the_clerk(hour, tmp_path, monkeypatch) -> None:
    tool, led, _tid = hour
    monkeypatch.setattr(tool, "goals_through_clerk", lambda: False)
    asked = []
    tool.missions_hour(
        led,
        tmp_path,
        envelope=_envelope(tmp_path),
        originate=lambda t, s: asked.append(t),
    )
    assert asked == []
