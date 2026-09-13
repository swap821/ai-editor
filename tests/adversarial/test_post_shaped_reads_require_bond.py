"""A read shaped as a POST walked past the bond gate.

`edge_security._require_bonded_operator` refuses unbonded callers on
`_READ_METHODS = {"GET", "HEAD"}`. That keys the decision on the HTTP *verb*,
while confidentiality depends on what the route *serves*. `POST
/api/v1/memory/search` is semantic recall over the operator's memory -- a read
by every meaning except the verb -- so the gate never inspected it.

Reproduced 2026-09-13, same client, three calls:

    POST /api/v1/auth/session    -> 200  anonymous session + CSRF, no bond
    GET  /api/v1/security/audit  -> 401  proves this client is NOT bonded
    POST /api/v1/memory/search   -> 200  memory recall SERVED

Nothing else stopped it either: the route is `RouteAuthority("GREEN", 120,
"session")`, so `action_guard`'s privileged check (YELLOW-only) does not apply
and any session satisfies `"session"`; `check_mutation_origin_or_token` wants a
session and CSRF proof, and an anonymous session has both.

The threat is not a stranger at the keyboard. It is other local software on the
operator's machine -- a browser extension, an npm postinstall, another app --
which is precisely the adversary the bonded-read gate was built for.

These tests are the behavioural bar. The structural fix (RouteAuthority
declaring what a route serves, instead of the gate guessing from the verb) is
pinned separately in test_route_authority_declares_what_it_serves.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def isolated_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A client against a fresh data dir, holding an ANONYMOUS session.

    The session is real -- minted by the public session-create route the way any
    local process could mint one -- and carries no operator bond.
    """
    data_dir = tempfile.mkdtemp(prefix="aios-bondgate-")
    monkeypatch.setenv("AIOS_DATA_DIR", data_dir)

    from aios.api.main import app

    client = TestClient(app, client=("127.0.0.1", 12345))
    client.headers["Origin"] = "http://localhost:5173"
    client.headers["Host"] = "localhost:8000"

    # conftest bootstraps a loopback session at TestClient init. Drop it and
    # mint our own, so the session under test is unambiguously the anonymous
    # one this test is about -- and so two `csrf_token` cookies do not collide.
    client.cookies.clear()
    created = client.post("/api/v1/auth/session")
    assert created.status_code == 200, "public session-create route changed shape"
    csrf = client.cookies.get("csrf_token")
    if csrf:
        client.headers["X-CSRF-Token"] = csrf

    try:
        yield client
    finally:
        client.close()
        shutil.rmtree(data_dir, ignore_errors=True)


def _is_unbonded(client: TestClient) -> bool:
    """The control. A bonded client would be served this; this one must not be."""
    return client.get("/api/v1/security/audit").status_code in {401, 403}


def test_the_client_under_test_really_is_unbonded(isolated_app: TestClient) -> None:
    """Without this, the test below could pass by refusing a bonded caller.

    A confidentiality test whose subject turns out to be privileged proves the
    opposite of what it claims, so the premise is asserted rather than assumed.
    """
    assert _is_unbonded(isolated_app), (
        "the fixture client is bonded; the refusal tests below would be vacuous"
    )


def test_an_unbonded_session_is_refused_memory_recall(isolated_app: TestClient) -> None:
    """THE BAR. Holding a session is not being the operator."""
    response = isolated_app.post(
        "/api/v1/memory/search", json={"query": "ssh key", "top_k": 3}
    )

    assert response.status_code in {401, 403}, (
        "an unbonded caller was served semantic recall over operator memory "
        f"(got {response.status_code}: {response.text[:200]})"
    )


def test_recall_does_not_silently_widen_to_unverified(
    isolated_app: TestClient,
) -> None:
    """`include_unverified=True` was hardcoded at the route.

    `MemoryRecallContext.include_unverified` defaults to False, and the
    authority uses it to drop everything that is not VERIFIED-or-advisory
    (aios/application/memory/authority.py). The route overrode that default, so
    the one caller that reached the widest surface was also the least
    authenticated one. This pins the contract's own default as the route's
    behaviour.
    """
    from aios.domain.memory.contracts import MemoryRecallContext

    assert MemoryRecallContext().include_unverified is False, (
        "the safe default moved; the route fix below is anchored to it"
    )

    # Parsed, not string-matched. A substring search also hits the docstring
    # that EXPLAINS the old behaviour, so it would fail on a correct fix and
    # pass on a route that merely renamed the argument.
    import ast
    import textwrap

    from aios.api.routes import memory as memory_routes
    from tests.source_rules import executable_source

    # `executable_source`, not `inspect.getsource`: the repo pins raw-source use
    # in tests at budget ZERO (tests/test_source_rules.py). The AST walk below
    # would not be fooled by prose anyway, but there is no honest reason to add
    # a raw one back when the stripped version is a drop-in.
    tree = ast.parse(textwrap.dedent(executable_source(memory_routes.memory_search)))
    widened = [
        kw
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "MemoryRecallContext"
        for kw in node.keywords
        if kw.arg == "include_unverified"
        and not (isinstance(kw.value, ast.Constant) and kw.value.value is False)
    ]
    assert not widened, (
        "the recall route still widens include_unverified, disabling the trust "
        "filter for the least authenticated caller on the surface"
    )

    scoped = [
        kw.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "MemoryRecallContext"
        for kw in node.keywords
    ]
    assert "session_id" in scoped or "project_id" in scoped, (
        "recall is unscoped: MemoryRecallContext carries session_id/project_id "
        "and the adapters honour them, so passing neither recalls across scopes"
    )
