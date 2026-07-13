"""Architecture conformance: every mutating API route must declare policy metadata."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

import pytest

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
