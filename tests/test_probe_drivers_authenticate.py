"""Every driver that reaches /api/generate must carry a real operator session.

The defect
----------
`tools/endurance_tester.py` posted to `/api/generate` with a bare
`requests.post` -- no headers, no session cookie, no CSRF token, and no replay
of the 428 capability challenge that privileged routes answer with. It could
not have completed a single turn.

That matters more than a broken script, because endurance is HALF of organ 44
("Golden Mission **and Endurance** Evaluation"). The organ's ledger carried
"endurance has not been run" as a known blocker while the reason it could not
run sat in the harness itself.

`tools/golden_mission_runner.py` hit exactly this wall first, and
`aios/probe_session.py` was written to solve it. The fix was to reuse that, not
to grow a second auth path that drifts.

Why a test and not just the fix
-------------------------------
The failure is silent in the worst way: an unauthenticated driver still runs,
still records turns, and still writes a number. A 30-minute endurance run would
score every turn a failure and report it as a model result. Nothing crashes,
and the output looks like evidence.

So the rule is pinned structurally -- a driver may not hand-roll a POST to a
privileged route -- and behaviourally: an auth failure must PROPAGATE, never be
swallowed into a zero score.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Drivers that drive the privileged API on an operator's behalf.
_DRIVERS = (
    "tools/endurance_tester.py",
    "tools/golden_mission_runner.py",
)


def _module_source(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative", _DRIVERS)
def test_driver_never_hand_rolls_a_post_to_the_privileged_api(relative: str) -> None:
    """No `requests.post(...)` anywhere in a driver.

    Checked by AST rather than substring so a comment mentioning requests.post
    (this file's own docstrings do) cannot satisfy or trip it. `requests.get`
    against the public /health probe stays allowed -- that route needs no
    session, and forcing one there would be ceremony.
    """
    tree = ast.parse(_module_source(relative))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "requests"
    ]
    assert not offenders, (
        f"{relative} calls requests.post directly at line(s) {offenders}; "
        "privileged routes need ProbeSession.post_stream, which carries the "
        "operator session and CSRF and replays the 428 capability challenge"
    )


@pytest.mark.parametrize("relative", _DRIVERS)
def test_driver_routes_generate_through_probe_session(relative: str) -> None:
    """The positive half: the driver actually uses the shared session."""
    source = _module_source(relative)
    assert "ProbeSession" in source, f"{relative} does not import ProbeSession"
    assert "post_stream(" in source, (
        f"{relative} never calls post_stream -- it cannot be reaching "
        "/api/generate with a session"
    )


def test_an_auth_failure_stops_the_run_instead_of_scoring_zero(monkeypatch) -> None:
    """A driver that cannot authenticate must raise, not quietly fail turns.

    This is the property that makes the number trustworthy. If bootstrap()
    failure were swallowed, endurance would run to completion, record every
    turn as failed, and publish a 0% success rate indistinguishable from a
    genuine model collapse.
    """
    import aios.probe_session as probe_session
    import tools.endurance_tester as endurance

    monkeypatch.setattr(endurance, "_PROBE_SESSION", None)

    def _refuse(self, display_name: str = "") -> None:
        raise probe_session.ProbeAuthError("no operator credential available")

    monkeypatch.setattr(probe_session.ProbeSession, "bootstrap", _refuse)

    with pytest.raises(probe_session.ProbeAuthError):
        endurance.run_prompt("anything", "session-1")


def test_the_session_is_built_once_and_reused(monkeypatch) -> None:
    """One operator session per run, not one per turn.

    Endurance is a sustained-load harness; re-enrolling on every turn would
    measure the enrollment path instead of the thing under test, and would
    make the latency series meaningless.
    """
    import aios.probe_session as probe_session
    import tools.endurance_tester as endurance

    monkeypatch.setattr(endurance, "_PROBE_SESSION", None)
    calls: list[str] = []

    def _count(self, display_name: str = ""):
        calls.append(display_name)
        return self

    monkeypatch.setattr(probe_session.ProbeSession, "bootstrap", _count)

    first = endurance._session()
    second = endurance._session()

    assert first is second
    assert len(calls) == 1, f"bootstrap ran {len(calls)} times, expected once"
