"""Architecture conformance: every mutating API route must declare policy metadata."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

import pytest
from fastapi.routing import APIRoute

from aios.policy.kernel import PolicyKernel, _ROUTE_AUTHORITY, _route_match


_MUTATING_METHODS = {"post", "put", "delete", "patch"}


def _route_decorator_paths(source_path: Path) -> Iterable[tuple[str, str]]:
    """Yield (http_method, path) for every mutating route decorator in *source_path*."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        method = func.attr.lower()
        if method not in _MUTATING_METHODS:
            continue
        # Match @router.post("/path") or @app.post("/path").
        value = func.value
        if not (isinstance(value, ast.Name) and value.id in {"router", "app"}):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
            continue
        yield method.upper(), first.value


def _all_mutating_routes() -> set[str]:
    """Collect mutating route paths from the API surface."""
    api_dir = Path(__file__).parent.parent / "aios" / "api"
    routes_dir = api_dir / "routes"
    paths: set[str] = set()
    for source in list(routes_dir.glob("*.py")) + [api_dir / "main.py"]:
        if not source.is_file():
            continue
        for _method, path in _route_decorator_paths(source):
            paths.add(path)
    return paths


def _application_routes(routes) -> Iterable[APIRoute]:
    """Flatten FastAPI's lazy included-router wrappers for architecture scans."""
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _application_routes(original_router.routes)
        elif isinstance(route, APIRoute):
            yield route


def _application_route(path: str) -> APIRoute:
    from aios.api.main import app

    return next(route for route in _application_routes(app.routes) if route.path == path)


@pytest.fixture
def kernel():
    return PolicyKernel()


def test_every_mutating_route_has_registry_entry(kernel):
    missing: list[str] = []
    registered = set(_ROUTE_AUTHORITY.keys())
    for path in _all_mutating_routes():
        if path in registered:
            continue
        # Templated routes may match a templated registry key.
        if any(_route_match(route, path) for route in registered):
            continue
        missing.append(path)
    assert not missing, f"mutating routes missing policy registry metadata: {missing}"


def test_registered_routes_declare_action_type(kernel):
    empty_action_type: list[str] = []
    for route, authority in _ROUTE_AUTHORITY.items():
        if authority.action_type.value == "unknown":
            empty_action_type.append(route)
    assert not empty_action_type, f"routes missing action_type: {empty_action_type}"


def test_route_authority_returns_registered_metadata_for_mutations(kernel):
    for path in _all_mutating_routes():
        authority = kernel.route_authority(path)
        assert authority.audit_event, f"{path} has no audit event"
        assert authority.rate_limit_per_minute > 0, f"{path} has no rate limit"


def test_command_mutation_routes_depend_on_action_broker():
    """The two direct command surfaces must enter the R4 broker boundary."""
    for path in (
        "/api/v1/execute",
        "/api/terminal",
        "/api/v1/approval/req",
        "/api/v1/rollback",
        "/api/v1/self-analysis/proposals/{proposal_id}/apply",
        "/api/v1/council/missions/{mission_id}/rollback",
        "/api/generate",
    ):
        route = _application_route(path)
        dependency_names = {
            getattr(dependency.call, "__name__", "")
            for dependency in route.dependant.dependencies
        }
        assert "get_action_broker" in dependency_names, (
            f"{path} bypasses the ActionEnvelope -> PolicyKernel -> ActionBroker chain"
        )


def test_every_ordinary_mutation_route_has_universal_action_guard():
    """No ordinary mutating endpoint may omit the pre-dispatch broker gate."""
    from aios.api.main import app

    guarded = {
        route.path
        for route in _application_routes(app.routes)
        if any(method in {"POST", "PUT", "PATCH", "DELETE"} for method in route.methods)
        and any(
            getattr(dependency.call, "__name__", "") == "enforce_action_boundary"
            for dependency in route.dependant.dependencies
        )
    }
    missing = sorted(_all_mutating_routes() - guarded)
    # The bespoke flows own their own complete broker transaction; they are
    # tested separately above and are the only allowed dependency exceptions.
    exact = {
        "/api/v1/execute",
        "/api/terminal",
        "/api/v1/approval/req",
        "/api/v1/rollback",
        "/api/v1/self-analysis/proposals/{proposal_id}/apply",
        "/api/v1/council/missions/{mission_id}/rollback",
        "/api/generate",
    }
    assert set(missing) <= exact, f"ordinary mutating routes missing action guard: {missing}"
