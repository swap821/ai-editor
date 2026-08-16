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


class _Resp:
    """Minimal stand-in for a streamed requests.Response."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def json(self) -> dict:
        return {}


def _session_with(
    statuses: list[int],
    reauth_status: int = 200,
    login_status: int = 200,
):
    """A ProbeSession whose POSTs return `statuses` in order.

    `login_status` and `reauth_status` are separate on purpose. The first
    version of these tests returned one status for every auth call, so it could
    not tell login from reauth -- and passed against a refresh that called only
    reauth, which the live run then proved insufficient. A mock that cannot
    distinguish the two steps cannot guard their ordering.
    """
    from aios.probe_session import ProbeSession

    session = ProbeSession()
    session._credential = "credential-from-enrollment"
    sent: list[str] = []

    def _post_stream(url, **kwargs):
        sent.append(url)
        return _Resp(statuses.pop(0))

    def _post_auth(path, payload, timeout=30):
        sent.append(path)
        if "login" in path:
            return _Resp(login_status)
        return _Resp(reauth_status)

    session.http.post = _post_stream  # type: ignore[method-assign]
    session._post = _post_auth  # type: ignore[method-assign]
    return session, sent


def test_the_refresh_logs_in_before_reauthenticating() -> None:
    """The ordering that the first fix got wrong.

    Calling only `/api/v1/auth/reauth` looks sufficient and is not: once the
    privileged window has lapsed the session has usually lapsed with it, so
    reauth is itself refused. The endurance harness died at turn 6 twice, and
    the backend log showed the refusal directly:

        POST /api/generate        401 Unauthorized
        POST /api/v1/auth/reauth  401 Unauthorized

    Login mints a fresh session; only then can reauth grant the window on it.
    """
    session, sent = _session_with([401, 200])
    session.post_stream("/api/generate", {}, 10)

    auth = [s for s in sent if "/auth/" in s]
    assert auth, "no authentication was attempted on a 401"
    assert "login" in auth[0], f"expected login first, got {auth}"
    assert any("reauth" in s for s in auth), (
        "login alone leaves the privileged window unopened -- reauth must follow"
    )
    assert auth.index([s for s in auth if "login" in s][0]) < auth.index(
        [s for s in auth if "reauth" in s][0]
    ), "reauth ran before login; that is the exact ordering bug this pins"


def test_a_refused_login_stops_the_refresh() -> None:
    """If the credential itself is rejected, do not go on to reauth."""
    session, sent = _session_with([401, 200], login_status=401)
    assert session.post_stream("/api/generate", {}, 10).status_code == 401
    assert not any("reauth" in s for s in sent), (
        "reauth was attempted after login failed -- it cannot succeed and the "
        "extra call only obscures the real error"
    )


def test_an_expired_privileged_window_is_refreshed_and_the_call_retried() -> None:
    """The defect that killed the first 30-minute endurance run.

    `aios/application/identity/service.py` records the reauthentication event
    with `expires_at = now + 900`, so privileged access lapses after 15
    minutes. The endurance harness defaults to a 30-MINUTE run and died at
    turn 6 with `401 Unauthorized for url: /api/generate` -- it could never
    once have completed its own default duration.
    """
    session, sent = _session_with([401, 200])

    response = session.post_stream("/api/generate", {}, 10)

    assert response.status_code == 200
    assert any("/api/v1/auth/reauth" in s for s in sent), (
        "a 401 must trigger a re-authentication, not just a blind retry"
    )


def test_a_real_401_still_surfaces() -> None:
    """The refresh is not a way to make 401s disappear.

    If re-authentication does not restore access the failure is genuine and
    must reach the caller. Swallowing it would turn a broken credential into
    an infinite retry, or into a silent run of failed turns -- the same class
    of dishonesty as an unauthenticated driver scoring zero.
    """
    session, _ = _session_with([401, 401], reauth_status=200)
    assert session.post_stream("/api/generate", {}, 10).status_code == 401


def test_only_one_retry_is_attempted() -> None:
    """Exactly one, so a persistent 401 cannot spin."""
    session, sent = _session_with([401, 401], reauth_status=200)
    session.post_stream("/api/generate", {}, 10)
    assert sum(1 for s in sent if "/api/generate" in s) == 2


def test_a_failed_reauthentication_does_not_retry() -> None:
    """No credential, or a refused refresh, means the 401 stands as-is."""
    session, sent = _session_with([401, 200], reauth_status=403)
    assert session.post_stream("/api/generate", {}, 10).status_code == 401
    assert sum(1 for s in sent if "/api/generate" in s) == 1


def test_a_healthy_call_never_reauthenticates() -> None:
    """The refresh is exceptional. A 200 must cost exactly one request."""
    session, sent = _session_with([200])
    assert session.post_stream("/api/generate", {}, 10).status_code == 200
    assert not any("reauth" in s for s in sent)


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
