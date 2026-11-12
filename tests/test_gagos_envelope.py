"""GAGOS's daily envelope (organ 9), signed by the operator (2026-11-12).

He chose "Envelope via organs 9+10": he approves GAGOS's work once a day as an
envelope -- folders, kinds of change, how many missions, PR only -- and each
GAGOS mission consumes one slot. Pinned here, with red-team cases: only a
privileged operator signs; GAGOS never originates as him; nothing is admitted
outside the folders, kinds, count or expiry; the forbidden paths stay
forbidden whatever the folders say; a stop ends the envelope even after it is
cleared; two missions never share the last slot.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import pytest

from aios.application.capabilities.authority import EmergencyStopHardWiringAuthority
from aios.application.capabilities.envelope import EnvelopeAuthority, EnvelopeRefused
from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopHooks,
)
from aios.domain.capabilities.envelope import EnvelopeError, EnvelopeTerms
from aios.domain.governance.contracts import EmergencyStopRequest

FOLDER = "frontend/src/superbrain/"
TEST = "frontend/src/superbrain/lib/tabStore.test.ts"
CODE = "frontend/src/superbrain/lib/tabStore.ts"


@dataclass
class Who:
    principal_id: str = "operator-1"
    principal_type: str = "operator"
    authentication_level: str = "privileged"
    authentication_event_id: str = "auth-1"
    session_id: str = "session-1"
    metadata: dict = field(default_factory=dict)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def _stop(tmp_path) -> EmergencyStopController:
    return EmergencyStopController(
        tmp_path / "stop.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda: None,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda reason: None,
        ),
    )


def _terms(**kw) -> EnvelopeTerms:
    base = {"folders": [FOLDER], "kinds": ["tests"], "max_missions": 2, "hours": 12}
    return EnvelopeTerms.build(**{**base, **kw})


def _authority(tmp_path, clock=None, stop=None) -> EnvelopeAuthority:
    return EnvelopeAuthority(
        db_path=tmp_path / "caps.db",
        emergency_stop=stop if stop is not None else _stop(tmp_path),
        clock=clock or Clock(),
    )


def _admit(authority, mission="goal-1", files=(TEST,), kind="tests", by="gagos"):
    return authority.admit(
        mission_id=mission, files=list(files), kind=kind, originator=by
    )


# -- the terms --------------------------------------------------------------


@pytest.mark.parametrize(
    "folders",
    [
        ["aios/security/"],
        [".git/"],
        [".github/workflows/"],
        ["data/"],
        ["/etc/"],
        ["C:/Windows/"],
        ["../outside/"],
        ["frontend/*"],
        [""],
        ["."],
        [],
    ],
)
def test_terms_refuse_folders_that_can_never_be_an_envelope(folders) -> None:
    with pytest.raises(EnvelopeError):
        _terms(folders=folders)


@pytest.mark.parametrize(
    "kw",
    [
        {"kinds": []},
        {"kinds": ["everything"]},
        {"max_missions": 0},
        {"max_missions": 21},
        {"max_missions": True},
        {"hours": 0},
        {"hours": 25},
        {"delivery": "push"},
    ],
)
def test_terms_refuse_out_of_range_values(kw) -> None:
    with pytest.raises(EnvelopeError):
        _terms(**kw)


def test_terms_are_normalised_and_digested_stably() -> None:
    a = _terms(folders=["frontend\\src\\superbrain", "./frontend/src/workbench/"])
    b = _terms(folders=["frontend/src/workbench", "frontend/src/superbrain/"])
    assert a.folders == ("frontend/src/superbrain/", "frontend/src/workbench/")
    assert a.digest() == b.digest()


# -- signing -----------------------------------------------------------------


@pytest.mark.parametrize(
    "who",
    [
        Who(principal_type="system"),
        Who(principal_type="worker"),
        Who(authentication_level="standard"),
        Who(authentication_event_id=""),
    ],
)
def test_only_a_freshly_authenticated_operator_signs(tmp_path, who) -> None:
    with pytest.raises(EnvelopeRefused):
        _authority(tmp_path).sign(_terms(), principal=who)


def test_a_signed_envelope_is_live_and_reports_itself(tmp_path) -> None:
    authority = _authority(tmp_path)
    envelope = authority.sign(_terms(), principal=Who())
    status = authority.status()
    assert status["live"] is True
    assert status["envelopeId"] == envelope.envelope_id
    assert status["missionsLeft"] == 2
    assert status["terms"]["folders"] == [FOLDER]


def test_no_envelope_says_so(tmp_path) -> None:
    authority = _authority(tmp_path)
    assert authority.status() == {
        "live": False,
        "reason": "the operator has not signed an envelope",
    }
    with pytest.raises(EnvelopeRefused, match="has not signed"):
        _admit(authority)


def test_a_newer_signature_ends_the_older_envelope(tmp_path) -> None:
    authority = _authority(tmp_path)
    first = authority.sign(_terms(), principal=Who())
    _admit(authority, "goal-1")
    second = authority.sign(_terms(max_missions=1), principal=Who())
    assert authority.live().envelope_id == second.envelope_id
    with pytest.raises(EnvelopeRefused, match="superseded"):
        authority.held_slot("goal-1")
    assert first.envelope_id != second.envelope_id


# -- admission -----------------------------------------------------------------


def test_a_mission_inside_takes_one_slot_and_records_it(tmp_path) -> None:
    authority = _authority(tmp_path)
    envelope = authority.sign(_terms(), principal=Who())
    slot = _admit(authority)
    assert (slot.slot, slot.of, slot.envelope_id) == (1, 2, envelope.envelope_id)
    assert "slot 1 of 2" in slot.approval_reason()
    assert authority.held_slot("goal-1") == slot
    assert authority.status()["missionsLeft"] == 1


@pytest.mark.parametrize(
    "files,kind,why",
    [
        ([CODE], "tests", "not a test file"),
        ([TEST], "code", "not 'code'"),
        (
            ["frontend/src/workbench/x.test.ts"],
            "tests",
            "outside the envelope's folders",
        ),
        (
            ["frontend/src/superbrain/../../../aios/security/a.test.ts"],
            "tests",
            "climb",
        ),
        (["/frontend/src/superbrain/a.test.ts"], "tests", "absolute"),
        (["frontend/src/superbrain/*.test.ts"], "tests", "plain"),
        ([], "tests", "at least one file"),
    ],
)
def test_nothing_outside_the_terms_is_admitted(tmp_path, files, kind, why) -> None:
    authority = _authority(tmp_path)
    authority.sign(_terms(), principal=Who())
    with pytest.raises(EnvelopeRefused, match=why):
        _admit(authority, files=files, kind=kind)
    assert authority.status()["missionsUsed"] == 0


def test_forbidden_paths_stay_forbidden_inside_a_wide_folder(tmp_path) -> None:
    authority = _authority(tmp_path)
    authority.sign(_terms(folders=["aios/"], kinds=["code"]), principal=Who())
    for path in ("aios/security/gateway.py", "aios/SECURITY/x.py", "aios/.env.local"):
        with pytest.raises(EnvelopeRefused, match="never inside"):
            _admit(authority, files=[path], kind="code")
    assert _admit(authority, files=["aios/core/x.py"], kind="code").slot == 1


def test_the_signer_never_originates_inside_his_own_envelope(tmp_path) -> None:
    authority = _authority(tmp_path)
    authority.sign(_terms(), principal=Who())
    with pytest.raises(EnvelopeRefused, match="cannot originate"):
        _admit(authority, by="operator-1")


def test_slots_run_out_and_a_mission_holds_one_slot_only(tmp_path) -> None:
    authority = _authority(tmp_path)
    authority.sign(_terms(), principal=Who())
    _admit(authority, "goal-1")
    with pytest.raises(EnvelopeRefused, match="already holds"):
        _admit(authority, "goal-1")
    _admit(authority, "goal-2")
    with pytest.raises(EnvelopeRefused, match="2 missions are used"):
        _admit(authority, "goal-3")


def test_two_missions_never_share_the_last_slot(tmp_path) -> None:
    authority = _authority(tmp_path)
    authority.sign(_terms(max_missions=1), principal=Who())
    won, lost = [], []

    def ask(mission: str) -> None:
        try:
            won.append(_admit(authority, mission))
        except EnvelopeRefused as exc:
            lost.append(str(exc))

    threads = [threading.Thread(target=ask, args=(f"goal-{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(won) == 1
    assert len(lost) == 7


def test_expiry_ends_the_envelope_and_its_slots(tmp_path) -> None:
    clock = Clock()
    authority = _authority(tmp_path, clock=clock)
    authority.sign(_terms(hours=1), principal=Who())
    _admit(authority, "goal-1")
    clock.now += 3600
    assert authority.live() is None
    with pytest.raises(EnvelopeRefused, match="expired"):
        _admit(authority, "goal-2")
    with pytest.raises(EnvelopeRefused, match="expired"):
        authority.held_slot("goal-1")


def test_revocation_ends_it_and_only_the_operator_revokes(tmp_path) -> None:
    authority = _authority(tmp_path)
    authority.sign(_terms(), principal=Who())
    with pytest.raises(EnvelopeRefused):
        authority.revoke(principal=Who(principal_type="system"))
    assert authority.revoke(principal=Who()) is True
    with pytest.raises(EnvelopeRefused, match="revoked by the operator"):
        _admit(authority)


# -- the emergency stop ----------------------------------------------------------


def test_a_stop_ends_the_envelope_even_after_it_is_cleared(tmp_path) -> None:
    stop = _stop(tmp_path)
    authority = _authority(tmp_path, stop=stop)
    authority.sign(_terms(), principal=Who())
    _admit(authority, "goal-1")
    stop.engage(
        EmergencyStopRequest(
            operator_id="operator-1", authentication_event_id="auth-2", reason="test"
        )
    )
    with pytest.raises(EnvelopeRefused, match="emergency stop"):
        _admit(authority, "goal-2")
    token = stop.issue_clear_capability(
        operator_id="operator-1",
        authentication_event_id="auth-3",
        session_id="session-1",
    )
    stop.clear(
        operator_id="operator-1",
        authentication_event_id="auth-3",
        session_id="session-1",
        clear_capability=token,
    )
    assert not stop.is_engaged()
    with pytest.raises(EnvelopeRefused, match="engaged after the envelope was signed"):
        _admit(authority, "goal-2")
    with pytest.raises(EnvelopeRefused, match="engaged after"):
        authority.held_slot("goal-1")
    # Only a new signature starts another.
    authority.sign(_terms(), principal=Who())
    assert _admit(authority, "goal-2").slot == 1


@pytest.mark.parametrize(
    "stop", [None, EmergencyStopHardWiringAuthority.UNGOVERNED_FIXTURE]
)
def test_an_envelope_is_never_ungoverned(tmp_path, stop) -> None:
    authority = EnvelopeAuthority(db_path=tmp_path / "caps.db", emergency_stop=stop)
    with pytest.raises(EnvelopeRefused, match="no emergency stop"):
        authority.sign(_terms(), principal=Who())


@pytest.mark.parametrize(
    "path",
    [
        "aios/security./gateway.py",
        "aios/security /gateway.py",
        "aios/SECURI~1/gateway.py",
        "aios/core/x.py:hidden",
        "aios/core/x.py::$DATA",
        "aios/core/x.py.",
        'aios/core/"x".py',
        "aios/core/x|y.py",
    ],
)
def test_windows_spellings_of_a_path_are_refused(tmp_path, path) -> None:
    """Windows reads these as other paths: trailing dots and spaces are
    dropped (so ``security.`` IS ``security``), ``~1`` names an 8.3 short
    name, ``:`` an alternate data stream."""
    authority = _authority(tmp_path)
    authority.sign(_terms(folders=["aios/"], kinds=["code"]), principal=Who())
    with pytest.raises(EnvelopeRefused):
        _admit(authority, files=[path], kind="code")
    assert authority.status()["missionsUsed"] == 0


# -- races (Codex's adversarial review of 58834665) -----------------------------


class EngagesBetween:
    """A stop whose check passes, then reads engaged: the stop engaging between
    the check and the generation read."""

    def __init__(self, real) -> None:
        self.real = real

    def assert_operational(self) -> None:
        self.real.assert_operational()

    def state(self):
        self.real.engage(
            EmergencyStopRequest(
                operator_id="operator-1",
                authentication_event_id="auth-9",
                reason="race",
            )
        )
        return self.real.state()


def _clear(stop) -> None:
    token = stop.issue_clear_capability(
        operator_id="operator-1",
        authentication_event_id="auth-10",
        session_id="session-1",
    )
    stop.clear(
        operator_id="operator-1",
        authentication_event_id="auth-10",
        session_id="session-1",
        clear_capability=token,
    )


def test_a_stop_engaging_while_signing_refuses_the_signature(tmp_path) -> None:
    real = _stop(tmp_path)
    racing = _authority(tmp_path, stop=EngagesBetween(real))
    with pytest.raises(EnvelopeRefused, match="engaged"):
        racing.sign(_terms(), principal=Who())
    _clear(real)
    # Nothing was signed that the clearing could revive.
    assert _authority(tmp_path, stop=real).live() is None


def test_a_stop_engaging_while_a_slot_is_taken_voids_the_slot(tmp_path) -> None:
    stop = _stop(tmp_path)
    authority = _authority(tmp_path, stop=stop)
    authority.sign(_terms(), principal=Who())
    reserve = authority.store.reserve

    def engage_then_reserve(**kw):
        stop.engage(
            EmergencyStopRequest(
                operator_id="operator-1",
                authentication_event_id="auth-9",
                reason="race",
            )
        )
        return reserve(**kw)

    authority.store.reserve = engage_then_reserve
    with pytest.raises(EnvelopeRefused, match="the slot just taken is void"):
        _admit(authority, "after-stop")
    _clear(stop)
    with pytest.raises(EnvelopeRefused, match="engaged after"):
        authority.held_slot("after-stop")


def test_expiry_is_read_once_the_lock_is_held(tmp_path) -> None:
    clock = Clock()
    authority = _authority(tmp_path, clock=clock)
    authority.sign(_terms(hours=1), principal=Who())
    clock.now += 3600 - 1
    reserve = authority.store.reserve

    def slow_lock(**kw):
        clock.now += 2  # the wait for the writer lock outlives the envelope
        return reserve(**kw)

    authority.store.reserve = slow_lock
    with pytest.raises(EnvelopeRefused, match="ended while the slot was being taken"):
        _admit(authority, "late")
    assert authority.store.slot("late") is None
