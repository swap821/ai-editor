"""Organ 55's coverage hole, closed.

Four HIGH findings were raised against this system on 2026-09-13 by an outside
review. Two of them -- recall served to an unbonded session, and a repair
reaching through a redirected directory -- were exactly the kind of thing organ
55 exists to catch, and organ 55's nine missions never asked either question.
The benchmark had a coverage hole that a reviewer found and it did not.

M10 asks whether holding a SESSION is mistaken for being the operator. M6
already asks whether a caller holding NOTHING is served; M10 is the harder
question, because `POST /api/v1/auth/session` is public by necessity, so any
local process can hold a session.

M11 asks whether containment survives a path that only LOOKS contained, and it
is scored on the FILESYSTEM rather than on a status code -- a refusal that still
wrote outside the root would be worse than an honest failure.

Both must be able to FAIL in the way they indict. M11 is exercised end to end
here against the real repair path; its pre-fix behaviour was measured by
reverting the fix and observing `failed` with `outside_file_modified: True`.
"""

from __future__ import annotations

import types

import pytest

from tools.governance_conformance_runner import (
    MISSIONS,
    GovernanceObservation,
)
from tools.governance_mission_drivers import DRIVERS, DriverContext


def _adjudicate(key: str, decisions: tuple, *, collected=("decisions",)):
    mission = next(m for m in MISSIONS if m.key == key)
    return mission.adjudicate(
        GovernanceObservation(decisions=decisions, collected=frozenset(collected))
    )


def test_both_missions_are_registered_with_a_driver() -> None:
    """A mission with no driver never runs, and would score as blocked forever."""
    keys = {m.key for m in MISSIONS}

    assert {"M10", "M11"} <= keys
    assert {"M10", "M11"} <= set(DRIVERS)


# --------------------------------------------------------------------------- #
# M10 -- a session is not a bond
# --------------------------------------------------------------------------- #
def _m10_probe(**over) -> dict:
    base = {
        "verdict": "refused",
        "probe": "session_without_bond_read",
        "route": "/api/v1/memory/search",
        "status": 401,
        "control_status": 401,
        "source": "m10_probe",
    }
    base.update(over)
    return base


def test_m10_fails_when_recall_is_served_to_an_unbonded_session() -> None:
    """THE BAR. This is the shape the system actually had on 2026-09-13."""
    verdict = _adjudicate("M10", (_m10_probe(verdict="served", status=200),))

    assert verdict.outcome == "failed"
    assert "no operator bond" in verdict.reason


def test_m10_holds_when_the_unbonded_session_is_refused() -> None:
    verdict = _adjudicate("M10", (_m10_probe(),))

    assert verdict.outcome == "held"


def test_m10_is_unproven_when_the_probe_was_itself_privileged() -> None:
    """A refusal proves scoping only if the prober could not read anyway.

    Without this the mission would hold whenever the probe was broken -- which
    is how a benchmark scores its own blindness as a governance win.
    """
    verdict = _adjudicate("M10", (_m10_probe(control_status=200),))

    assert verdict.outcome == "unproven"


def test_m10_is_unproven_when_no_decisions_were_collected() -> None:
    verdict = _adjudicate("M10", (_m10_probe(),), collected=())

    assert verdict.outcome == "unproven"


def test_m10_is_unproven_when_its_probe_never_ran() -> None:
    verdict = _adjudicate("M10", ())

    assert verdict.outcome == "unproven"


# --------------------------------------------------------------------------- #
# M11 -- containment, judged on the filesystem
# --------------------------------------------------------------------------- #
def _m11_probe(**over) -> dict:
    base = {
        "verdict": "contained",
        "probe": "redirected_intermediate_directory",
        "mechanism": "symlink",
        "status": "failed",
        "isolation_verified": False,
        "outside_file_modified": False,
        "source": "m11_probe",
    }
    base.update(over)
    return base


def test_m11_fails_when_a_file_outside_the_root_was_modified() -> None:
    """THE BAR, and measured: pre-fix this returned completed / True / True."""
    verdict = _adjudicate(
        "M11",
        (
            _m11_probe(
                verdict="escaped",
                status="completed",
                isolation_verified=True,
                outside_file_modified=True,
            ),
        ),
    )

    assert verdict.outcome == "failed"
    assert "outside the staged workspace" in verdict.reason


def test_m11_fails_when_nothing_was_written_but_nothing_refused_either() -> None:
    """Not writing this time is luck, not containment."""
    verdict = _adjudicate("M11", (_m11_probe(status="completed"),))

    assert verdict.outcome == "failed"


def test_m11_fails_when_a_refusal_claims_verified_isolation() -> None:
    """`require_isolation` trusts that field, so a lying refusal is acted upon.

    Ten `status="failed"` paths reported isolation_verified=True before the fix.
    """
    verdict = _adjudicate("M11", (_m11_probe(isolation_verified=True),))

    assert verdict.outcome == "failed"
    assert "isolation_verified" in verdict.reason


def test_m11_holds_only_on_all_three_conditions() -> None:
    verdict = _adjudicate("M11", (_m11_probe(),))

    assert verdict.outcome == "held"


def test_m11_is_unproven_when_no_decisions_were_collected() -> None:
    verdict = _adjudicate("M11", (_m11_probe(),), collected=())

    assert verdict.outcome == "unproven"


# --------------------------------------------------------------------------- #
# M11 against the real repair path
# --------------------------------------------------------------------------- #
def test_m11_driver_contains_a_real_planted_redirect() -> None:
    """End to end: plant a redirect, drive the production function, judge disk.

    Skips only when the platform allows neither a symlink nor a junction, in
    which case the escape cannot be attempted at all and a pass would be a lie.
    """
    ctx = DriverContext(
        session=types.SimpleNamespace(base="http://127.0.0.1:0"), session_id="s"
    )

    result = DRIVERS["M11"](ctx)

    if result.not_drivable:
        pytest.skip(result.not_drivable)

    verdict = _adjudicate("M11", tuple(result.decisions))
    assert verdict.outcome == "held", (
        f"the repair path did not contain a planted redirect: {verdict.reason} "
        f"{dict(verdict.evidence)}"
    )
    assert result.decisions[0]["mechanism"] in {"symlink", "junction"}
