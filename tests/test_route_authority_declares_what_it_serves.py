"""Every GREEN route reachable by a non-GET method must answer the question.

The bonded-read gate used to infer confidentiality from the HTTP verb, so a read
shaped as a POST walked past it (`POST /api/v1/memory/search`, measured
2026-09-13: served to an anonymous session while `GET /api/v1/security/audit`
refused the same client). The fix was to stop inferring: a route now DECLARES
`serves_operator_data` and the gate enforces the declaration.

A declaration only helps if it cannot be forgotten. This file is what makes the
next POST-shaped read impossible to add silently -- it fails on any GREEN
non-GET route that leaves the field `None`.

Scoped to GREEN on purpose: YELLOW and RED already require
`authentication_level == "privileged"` through `action_guard`, and the
unknown-route fallback is RED.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from aios.policy.kernel import _ROUTE_AUTHORITY, _route_match

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _routes_by_method() -> dict[str, set[str]]:
    """Map path -> HTTP methods, by scanning decorators across the package.

    Deliberately static rather than reading `app.routes`: this project's `app`
    object reports only the handlers defined directly in `main.py` (31 of them)
    even after startup, so a runtime scan would MISS every router-mounted route
    -- including the one this whole change is about. Scanning the source finds
    both `@router.<verb>` and `@app.<verb>`; an earlier version of this sweep
    looked only for `@router.` and missed `/api/v1/chat` and `/api/generate`.
    """
    found: dict[str, set[str]] = {}
    pattern = re.compile(r'@(?:router|app)\.(get|post|put|patch|delete)\(\s*"([^"]+)"')
    for path in (REPO_ROOT / "aios").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for verb, route in pattern.findall(text):
            found.setdefault(route, set()).add(verb.upper())
    return found


def _green_non_get_routes() -> list[str]:
    by_method = _routes_by_method()
    out = []
    for route, authority in _ROUTE_AUTHORITY.items():
        if authority.authority_class != "GREEN":
            continue
        methods = by_method.get(route)
        if methods is None:
            for candidate, verbs in by_method.items():
                if _route_match(route, candidate):
                    methods = verbs
                    break
        if methods and (methods - {"GET", "HEAD"}):
            out.append(route)
    return sorted(out)


def test_the_sweep_finds_the_route_this_change_was_about() -> None:
    """Guards the guard. A sweep that finds nothing would pass vacuously."""
    routes = _green_non_get_routes()

    assert "/api/v1/memory/search" in routes, "the sweep no longer sees the hole"
    assert len(routes) >= 15, f"sweep collapsed to {len(routes)} routes; it found 20"


@pytest.mark.parametrize("route", _green_non_get_routes())
def test_a_green_non_get_route_declares_what_it_serves(route: str) -> None:
    """THE BAR. Undeclared is not allowed to be the answer.

    The gate treats `None` as "serves the operator" so a forgotten declaration
    fails closed rather than open -- but a fail-closed default is a backstop,
    not a design. This makes the question mandatory at the point it is cheapest
    to answer: when the route is written.
    """
    authority = _ROUTE_AUTHORITY[route]

    assert authority.serves_operator_data is not None, (
        f"{route} is GREEN and reachable by a non-GET method, so the bonded-read "
        "gate's verb test does not cover it. Set serves_operator_data=True if an "
        "unbonded caller must not reach it, or =False with a comment saying why "
        "it is safe to serve one."
    )


def test_the_three_measured_leaks_require_a_bond() -> None:
    """Pins the verdicts that were established by probing the live surface.

    Each of these answered an unbonded caller on 2026-09-13 and disclosed or
    spent something belonging to the operator. Flipping any back to False is a
    decision that should have to argue with this list.
    """
    for route in (
        "/api/v1/memory/search",  # served: recall over operator memory
        "/api/v1/projects/scope-hints",  # served: real host filesystem paths
        "/api/v1/plan",  # served: spends the operator's planner/LLM
    ):
        assert _ROUTE_AUTHORITY[route].serves_operator_data is True, (
            f"{route} was measured serving an unbonded caller; it must require a bond"
        )
