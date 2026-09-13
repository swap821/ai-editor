"""Re-authenticating to approve a high-risk action was impossible.

INVARIANT III says the principal that REQUESTS an action must not be the one
that authorises it, so for actions that fetch and execute remote code
(`pip install`, `npm install`, `git clone`) `consume` demands an authentication
event strictly NEWER than the one that made the request.

The only way to obtain a newer event is `IdentityService.reauthenticate`. That
method ALWAYS rotates the session -- it calls `SessionManager.upgrade_session`,
which mints `secrets.token_urlsafe(32)` and deletes the old record, deliberately,
to prevent session fixation. And `Principal.session_id` IS the session hash
(`_principal_from_session`).

So the binding presented after a reauth necessarily differs in `session_id`, and
the comparison in `consume` excluded only `authentication_event_id`:

    _ignored = {"constitution_digest": None}
    if fresh_required:
        _ignored["authentication_event_id"] = "*"

The two requirements contradicted each other. Measured 2026-09-13:

    approve after reauth (session-B / newer event E2) -> REFUSED: binding mismatch
    control, session NOT rotated (session-A / event E2) -> APPROVED

The second line isolates the cause: the freshness rule was satisfied, and
`session_id` alone refused it. The class was unapprovable by anyone -- a
deadlock, not a leak. It failed closed, which is why nothing caught it: every
test that asked "is this refused?" got the right answer for the wrong reason.

The fix excludes `session_id` for exactly the actions that require fresh
authentication, for the same reason `authentication_event_id` is already
excluded there. Everything else in the binding still pins: operator, device,
action type, route, method, payload and resource digests, scope. And
`reauthenticate` independently verifies the credential and refuses when the
device does not match the current principal's, so session continuity is not the
control being relied upon.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest

HIGH_RISK = {"command": "pip install requests"}
ORDINARY = {"command": "mkdir training_ground/x"}

EVENTS = {
    "E1": {"created_at": 1000.0},  # the request
    "E2": {"created_at": 2000.0},  # a genuine reauthentication: strictly newer
    "E0": {"created_at": 10.0},  # an older event
}


@pytest.fixture()
def authority(tmp_path: Path) -> CapabilityAuthority:
    return CapabilityAuthority(
        db_path=tmp_path / "caps.db",
        emergency_stop=UNGOVERNED_FIXTURE,
        authentication_event_lookup=EVENTS.get,
    )


def _binding(
    *,
    session: str = "session-A",
    event: str = "E1",
    operator: str = "op-1",
    device: str = "device:local",
    payload: dict = HIGH_RISK,
) -> CapabilityBinding:
    return CapabilityBinding(
        operator_id=operator,
        device_id=device,
        authentication_event_id=event,
        session_id=session,
        action_type="COMMAND",
        route="/api/v1/execute",
        http_method="POST",
        payload_digest=payload_digest(payload),
        resource_digest="r" * 64,
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope="route:/api/v1/execute",
        verification_requirement="route_policy_v1",
        constitution_digest=None,
    )


def test_the_action_under_test_really_requires_fresh_authentication(
    authority: CapabilityAuthority,
) -> None:
    """The premise. On an ordinary action none of this applies."""
    token = authority.issue(_binding(), action_payload=HIGH_RISK)
    assert authority._requires_fresh_authentication(authority.inspect(token)) is True

    ordinary = authority.issue(_binding(payload=ORDINARY), action_payload=ORDINARY)
    assert (
        authority._requires_fresh_authentication(authority.inspect(ordinary)) is False
    )


def test_a_genuine_reauthentication_can_approve(
    authority: CapabilityAuthority,
) -> None:
    """THE BAR. A control nobody can satisfy is not a control."""
    token = authority.issue(_binding(), action_payload=HIGH_RISK)

    # Exactly what reauthenticate() produces: a newer event AND a rotated session.
    proof = authority.consume(token, _binding(session="session-B", event="E2"))

    assert proof.capability_id


def test_self_approval_is_still_refused(authority: CapabilityAuthority) -> None:
    """The invariant this whole mechanism exists for, unchanged.

    Holding the requesting session is not authorisation. Without this, relaxing
    `session_id` would have quietly restored the behaviour INVARIANT III forbids.
    """
    token = authority.issue(_binding(), action_payload=HIGH_RISK)

    with pytest.raises(CapabilityError, match="cannot also authorise"):
        authority.consume(token, _binding())


def test_an_older_authentication_cannot_approve(
    authority: CapabilityAuthority,
) -> None:
    """ "Newer", not merely "different" -- including from a different session."""
    token = authority.issue(_binding(), action_payload=HIGH_RISK)

    with pytest.raises(CapabilityError, match="not newer"):
        authority.consume(token, _binding(session="session-B", event="E0"))


@pytest.mark.parametrize(
    ("kwargs", "what"),
    [
        ({"operator": "op-2"}, "a different operator"),
        ({"device": "device:other"}, "a different device"),
        ({"payload": ORDINARY}, "a different action"),
    ],
)
def test_relaxing_the_session_did_not_relax_anything_else(
    authority: CapabilityAuthority, kwargs: dict, what: str
) -> None:
    """Everything the binding pinned before, it still pins."""
    token = authority.issue(_binding(), action_payload=HIGH_RISK)

    with pytest.raises(CapabilityError, match="binding mismatch"):
        authority.consume(token, _binding(session="session-B", event="E2", **kwargs))


def test_an_ordinary_action_still_pins_its_session(
    authority: CapabilityAuthority,
) -> None:
    """The relaxation is scoped to the fresh-auth class and nothing wider.

    Ordinary YELLOW work is one click and never reauthenticates, so its session
    cannot legitimately rotate mid-approval -- the pin stays.
    """
    token = authority.issue(_binding(payload=ORDINARY), action_payload=ORDINARY)

    with pytest.raises(CapabilityError, match="binding mismatch"):
        authority.consume(
            token, _binding(session="session-B", event="E1", payload=ORDINARY)
        )
