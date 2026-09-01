"""Every route handler's type annotations must actually resolve.

Found by the first run of the mypy gate (Ultra-plan Phase 8 / item 86):

    aios/api/main.py:1159: error: Name "DevelopmentTracker" is not defined

`generate` -- the handler behind `/api/generate`, the single busiest route in
the product -- annotated a FastAPI dependency with a name that was never
imported. Confirmed live, not theoretical::

    typing.get_type_hints(aios.api.main.generate)
    -> NameError: name 'DevelopmentTracker' is not defined

It survived because `from __future__ import annotations` makes annotations lazy
strings and FastAPI's current dependency path never forced them. Anything that
DOES force them -- OpenAPI schema generation, a typing-based validator, a future
FastAPI release that resolves hints eagerly -- would have raised at import or
first request.

This is exactly the class the inventory predicted mypy would catch: "type errors
in the security spine are caught only by whatever a test happens to exercise".
No test exercised this, because no test called `get_type_hints`.

The rule is asserted for EVERY route on the app rather than for the one handler
that was broken, so the next unimported annotation fails here instead of in
production.
"""

from __future__ import annotations

import typing

import pytest
from fastapi.routing import APIRoute

from aios.api.main import app


def _all_api_routes(routes: object) -> list[APIRoute]:
    """Every APIRoute, including those behind lazy `_IncludedRouter` wrappers.

    `app.routes` reports 31 entries of which only SIX are APIRoute; the other 21
    are lazy included-router wrappers holding their own route tables. A naive
    `isinstance` filter therefore sweeps a fifth of the app while looking
    exhaustive -- which the count guard below caught on the first run.

    Mirrors `_router_contains_path` in tests/conftest.py, which walks
    `original_router` for the same reason.
    """
    found: list[APIRoute] = []
    for route in routes or []:  # type: ignore[union-attr]
        if isinstance(route, APIRoute):
            found.append(route)
        inner = getattr(route, "original_router", None)
        if inner is not None:
            found.extend(_all_api_routes(getattr(inner, "routes", [])))
    return found


_ROUTES = _all_api_routes(app.routes)


def test_the_route_sweep_actually_covers_the_app() -> None:
    """Guard against the parametrised test passing on a near-empty list.

    Written because it fired: the first version collected 6 routes and reported
    success, while 21 included routers went unchecked.
    """
    assert len(_ROUTES) > 40, (
        f"only {len(_ROUTES)} APIRoute(s) collected. If the app still registers "
        "its routers, the collector has stopped walking them and the annotation "
        "check below is close to vacuous."
    )


@pytest.mark.parametrize(
    "route", _ROUTES, ids=lambda r: f"{sorted(r.methods)[0]} {r.path}"
)
def test_route_annotations_resolve(route: APIRoute) -> None:
    """`get_type_hints` must succeed for every handler.

    A NameError here means a handler is annotated with something that is not
    importable at runtime -- which FastAPI may tolerate today and will not
    necessarily tolerate tomorrow.
    """
    try:
        typing.get_type_hints(route.endpoint)
    except NameError as exc:
        pytest.fail(
            f"{route.path} handler {route.endpoint.__name__!r} has an "
            f"unresolvable annotation: {exc}. The name is used in a signature "
            "but never imported; `from __future__ import annotations` hides it "
            "until something resolves the hints."
        )
    except Exception as exc:  # noqa: BLE001 - report, do not mask
        pytest.fail(
            f"{route.path} handler {route.endpoint.__name__!r} annotations "
            f"could not be resolved: {type(exc).__name__}: {exc}"
        )


def test_the_generate_handler_specifically_resolves() -> None:
    """The one that was broken, pinned by name.

    Kept separate from the parametrised sweep so a refactor that drops
    `/api/generate` from the route table cannot silently retire this check.
    """
    from aios.api.main import generate

    hints = typing.get_type_hints(generate)
    assert "development" in hints, (
        "the `development` dependency disappeared from generate(); if that is "
        "deliberate, delete this test rather than weakening it"
    )
