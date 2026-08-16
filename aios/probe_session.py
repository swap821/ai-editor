"""Operator-session bootstrap for the evidence drivers (organ 44).

Why this exists
---------------
`tools/golden_mission_runner.py` and `tools/endurance_tester.py` are organ 44's
production entrypoints. Neither could execute against the API at all: they sent
no authentication, and every turn died on

    403  Mutation requires a bearer token or a valid session, exact Origin,
         and session-bound CSRF proof

They were written when `/api/generate` was open. The API was secured
afterwards, and nothing re-ran them, so organ 44's "Outside-machine — cloud
credentials barred" residual was only half the story: even with credentials the
runner could not have produced a single turn.

What the API actually requires, established by driving the real middleware
in-process rather than by reading the code:

    bearer only              -> 400  Host header is not configured for this API
    bearer + origin + host   -> 401  authenticated operator session required

So a bearer token was never sufficient. `/api/generate` wants a real operator
session, which is exactly what the test harness bootstraps in-process and what
this module now does over HTTP:

  enroll (first run only) -> login -> reauthenticate -> session + CSRF cookies

Re-authentication is not optional ceremony. The privileged control plane
requires a *fresh* reauth event on a rotated session before any control-plane
mutation, which is the same flow the real UI performs.

The enrollment credential is one-time material returned by the server. It is
held in memory for the life of the driver and written nowhere -- not to the
repo, not to `.aios/`, not to a log. A driver that persisted it would be
manufacturing a permanent operator credential on disk, which is precisely what
AGENTS.md §VII forbids.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from aios.probe_common import BASE, probe_headers

#: The API rejects any Host it was not configured for, so drivers must present
#: the configured one rather than whatever they happened to dial.
API_HOST_HEADER = os.environ.get("AIOS_PROBE_HOST", "localhost:8000")

#: Returned by a YELLOW route instead of running the handler. The driver must
#: replay the identical request carrying the server-issued token.
CAPABILITY_CHALLENGE = 428


class ProbeAuthError(RuntimeError):
    """Raised when a driver cannot establish an operator session."""


class ProbeSession:
    """A `requests.Session` that can actually reach the privileged API.

    Handles the two things every driver got wrong: establishing a real operator
    session, and replaying a 428 capability challenge with the issued token.
    """

    def __init__(self, base: str = BASE) -> None:
        self.base = base.rstrip("/")
        self.http = requests.Session()
        self._credential: str | None = None
        self.operator_id: str | None = None

    # -- bootstrap ---------------------------------------------------------
    def _post(self, path: str, payload: dict[str, Any], timeout: int = 30):
        headers = {**probe_headers(), "Host": API_HOST_HEADER}
        return self.http.post(
            f"{self.base}{path}", json=payload, headers=headers, timeout=timeout
        )

    def bootstrap(self, display_name: str = "Golden Mission Driver") -> "ProbeSession":
        """Enroll if needed, log in, then re-authenticate.

        Enrollment is attempted first and a 409 is expected on every run after
        the first -- the system permits exactly one Human Sovereign. When the
        operator already exists the driver cannot invent a credential, so the
        caller must supply one via ``AIOS_OPERATOR_CREDENTIAL``. Failing loudly
        here is deliberate: silently continuing would produce a driver that
        reports "0 missions passed" for an auth reason and look like a model
        failure.
        """
        credential = os.environ.get("AIOS_OPERATOR_CREDENTIAL") or None

        if credential is None:
            enrolled = self._post("/api/v1/auth/enroll", {"display_name": display_name})
            if enrolled.status_code == 201:
                body = enrolled.json()
                credential = body["enrollmentCredential"]
                self.operator_id = body.get("operatorId")
            elif enrolled.status_code == 409:
                raise ProbeAuthError(
                    "an operator is already enrolled and no credential was "
                    "supplied. Set AIOS_OPERATOR_CREDENTIAL to the enrollment "
                    "credential for this instance; this driver will not and "
                    "cannot invent one."
                )
            else:
                raise ProbeAuthError(
                    f"enrollment failed: HTTP {enrolled.status_code} "
                    f"{enrolled.text[:200]}"
                )

        login = self._post("/api/v1/auth/login", {"credential": credential})
        if login.status_code != 200:
            raise ProbeAuthError(
                f"login failed: HTTP {login.status_code} {login.text[:200]}"
            )

        # The control plane requires a FRESH reauthentication event on a
        # rotated session before any privileged mutation -- the same step the
        # real UI performs. Skipping it yields "authenticated operator session
        # required" on the first real turn.
        reauth = self._post("/api/v1/auth/reauth", {"credential": credential})
        if reauth.status_code != 200:
            raise ProbeAuthError(
                f"reauthentication failed: HTTP {reauth.status_code} "
                f"{reauth.text[:200]}"
            )

        self._credential = credential
        if not self.http.cookies.get("session_id"):
            raise ProbeAuthError("no session cookie was set by the server")
        return self

    def _reauthenticate(self) -> bool:
        """Re-establish the session AND the privileged window. True if it took.

        A ``reauthentication`` event is recorded with ``expires_at = now + 900``
        (``aios/application/identity/service.py``), so privileged access lapses
        15 minutes after bootstrap. That is a real control and is NOT to be
        widened; the correct client behaviour when it lapses is to authenticate
        again, which is what the real UI does.

        LOGIN FIRST, and that ordering is the whole fix. Calling only
        ``/api/v1/auth/reauth`` looks sufficient and is not: by the time the
        privileged window has lapsed the SESSION has usually lapsed with it, so
        reauth is itself rejected. The first version of this method did exactly
        that and the endurance harness still died at turn 6; the backend log
        showed the attempt and its refusal on consecutive lines::

            POST /api/generate        401 Unauthorized
            POST /api/v1/auth/reauth  401 Unauthorized

        ``login`` mints a fresh session cookie, and only then can ``reauth``
        grant the privileged window on it -- the same two steps, in the same
        order, that :meth:`bootstrap` performs.
        """
        if not self._credential:
            return False
        login = self._post("/api/v1/auth/login", {"credential": self._credential})
        if login.status_code != 200:
            return False
        reauth = self._post("/api/v1/auth/reauth", {"credential": self._credential})
        return reauth.status_code == 200

    # -- requests ----------------------------------------------------------
    def post_stream(self, path: str, payload: dict[str, Any], timeout: int):
        """POST with the session, refreshing auth and replaying a challenge.

        A YELLOW route answers 428 with an opaque token instead of running the
        handler. Replaying the identical request with that token is the real
        two-request protocol, not a workaround -- the token is server-issued
        and bound to this session.

        A 401 is handled separately and for a different reason. The privileged
        reauthentication window is 900 seconds, so ANY driver running longer
        than 15 minutes loses access mid-run. The endurance harness defaults to
        a 30-minute run and died at turn 6 with
        ``401 Unauthorized for url: /api/generate`` -- it could never once have
        completed its own default duration. Re-authenticating with the
        credential this session already holds is the documented flow, not a
        bypass: the window still expires on schedule and is still enforced by
        the server on every request.
        """

        def _send(
            extra: dict[str, str] | None = None, body: dict[str, Any] | None = None
        ):
            headers = {**probe_headers(), "Host": API_HOST_HEADER}
            csrf = self.http.cookies.get("csrf_token")
            if csrf:
                headers["X-CSRF-Token"] = csrf
            if extra:
                headers.update(extra)
            return self.http.post(
                f"{self.base}{path}",
                json=payload if body is None else body,
                headers=headers,
                stream=True,
                timeout=timeout,
            )

        def _without_stale_capabilities(body: dict[str, Any]) -> dict[str, Any]:
            """Drop approvalTokens minted for the session we just replaced.

            A capability is bound to the PRINCIPAL that requested it
            (``_generate_capability_binding`` in the turn pipeline). Logging in
            again mints a NEW session, so a token issued to the old one fails
            its binding and the server answers::

                400 {"detail":"invalid approval token: capability binding mismatch"}

            Replaying the identical body after a refresh is therefore guaranteed
            to fail whenever an approval was in flight -- which is exactly what
            truncated three long organ-44 runs, and why every simpler
            reproduction recovered cleanly: they all carried no tokens.

            Dropping them is FAIL-SAFE and self-healing. It cannot grant
            anything: without a token the route re-issues its 428 challenge, and
            the caller's normal approval loop obtains a fresh capability bound to
            the new session. Carrying the dead token forward is the only option
            that cannot work.
            """
            if not body.get("approvalTokens"):
                return body
            return {**body, "approvalTokens": []}

        response = _send()
        if response.status_code == 401 and self._reauthenticate():
            # Exactly one retry. If the refresh did not restore access the 401
            # is real and must surface, not be retried into a hang.
            #
            # The retry drops any approvalTokens: they were bound to the session
            # the refresh just replaced, and replaying them yields a guaranteed
            # 400 rather than the recovery this path exists to provide.
            response.close()
            response = _send(body=_without_stale_capabilities(payload))
        if response.status_code != CAPABILITY_CHALLENGE:
            return response

        headers = {**probe_headers(), "Host": API_HOST_HEADER}
        csrf = self.http.cookies.get("csrf_token")
        if csrf:
            headers["X-CSRF-Token"] = csrf

        try:
            token = (response.json().get("detail") or {}).get("approvalToken")
        except (AttributeError, ValueError):
            token = None
        if not token:
            return response
        headers["X-AIOS-Capability"] = token
        return self.http.post(
            f"{self.base}{path}",
            json=payload,
            headers=headers,
            stream=True,
            timeout=timeout,
        )


__all__ = ["API_HOST_HEADER", "ProbeAuthError", "ProbeSession"]
