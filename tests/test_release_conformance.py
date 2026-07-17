"""Release-time architecture and deployment invariants."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aios.domain.workers.worker_contract import WorkerPrincipal
from aios.runtime.cortex_bus import CortexBus
from scripts.security_scan import scan
from tests.cortex_event_helpers import append_event


REPO_ROOT = Path(__file__).resolve().parents[1]
_AUTHORITY_IMPORTS = frozenset(
    {
        "aios.application.capabilities.authority",
        "aios.infrastructure.capabilities.sqlite_store",
        "aios.core.approvals",
    }
)


def _import_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py")) if root.exists() else []


def test_model_and_worker_layers_do_not_import_capability_write_authority() -> None:
    paths = _python_files(REPO_ROOT / "aios" / "agents")
    paths += _python_files(REPO_ROOT / "aios" / "application" / "models")
    offenders = {
        str(path.relative_to(REPO_ROOT)): sorted(
            _import_names(path) & _AUTHORITY_IMPORTS
        )
        for path in paths
        if _import_names(path) & _AUTHORITY_IMPORTS
    }
    assert not offenders, offenders


def test_queen_layer_does_not_import_executor_implementation() -> None:
    forbidden_fragments = (
        "aios.core.executor",
        "aios.executor_service",
        "aios.infrastructure.executor",
    )
    offenders: list[str] = []
    for path in _python_files(REPO_ROOT / "aios" / "council"):
        imports = _import_names(path)
        if any(
            any(fragment in name for fragment in forbidden_fragments)
            for name in imports
        ):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, offenders


def test_worker_principal_cannot_carry_operator_or_credential_fields() -> None:
    forbidden = {
        "operator_id",
        "password",
        "secret",
        "token",
        "credential",
        "session_cookie",
    }
    assert not forbidden.intersection(WorkerPrincipal.model_fields)


@pytest.mark.parametrize(
    "event_type",
    (
        "approval.decided",
        "grant.issued",
        "skill.promoted",
        "autonomy.granted",
        "verdict.accepted",
        "zone.changed",
    ),
)
def test_authority_event_families_are_blocked_from_cortex(
    tmp_path: Path, event_type: str
) -> None:
    bus = CortexBus(tmp_path / "cortex.db")
    with pytest.raises(ValueError, match="may never ride"):
        append_event(bus, event_type, "entity-1", {})


def test_control_plane_image_has_non_root_default_and_executor_owns_socket() -> None:
    control_dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    executor_dockerfile = (REPO_ROOT / "Dockerfile.executor").read_text(
        encoding="utf-8"
    )
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "USER 65534:65534" in control_dockerfile
    assert "USER 65534:65534" in executor_dockerfile
    control_service = compose.split("\n  executor:", maxsplit=1)[0]
    executor_service = compose.split("\n  executor:", maxsplit=1)[1].split(
        "\n  prometheus:", maxsplit=1
    )[0]
    assert "docker.sock" not in control_service
    assert "docker.sock" in executor_service
    assert "group_add:" in executor_service
    assert "${AIOS_DOCKER_SOCKET_GID:-999}" in executor_service


def test_release_source_scan_is_clean() -> None:
    assert scan() == ()


def test_emergency_governance_routes_are_registered_and_separate_from_council() -> None:
    from aios.api.main import app

    def application_paths(routes) -> set[str]:
        paths: set[str] = set()
        for route in routes:
            original_router = getattr(route, "original_router", None)
            if original_router is not None:
                paths.update(application_paths(original_router.routes))
            elif hasattr(route, "path"):
                paths.add(route.path)
        return paths

    paths = application_paths(app.routes)
    assert "/api/v1/governance/emergency-stop" in paths
    assert "/api/v1/governance/emergency-stop/engage" in paths
    assert "/api/v1/governance/emergency-stop/clear" in paths


def test_r3_migrated_routes_do_not_issue_legacy_approval_tokens() -> None:
    for relative in (
        "aios/api/main.py",
        "aios/api/routes/actions.py",
        "aios/api/routes/council.py",
    ):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "approvals.issue(" not in source, relative
        assert "approval_store.issue(" not in source, relative
        assert "LegacyApprovalAdapter" not in source, relative
        assert "approvals.redeem(" not in source, relative
        assert "approvals.consume(" not in source, relative


def test_action_broker_uses_exact_capability_authority_in_production() -> None:
    source = (REPO_ROOT / "aios" / "application" / "action_broker.py").read_text(
        encoding="utf-8"
    )
    assert "CapabilityAuthority" in source
    assert "capabilities.issue" in source
    assert "capabilities.consume" in source
    assert "legacy test adapter" in source
    assert "from aios.core.approvals" not in source


def test_convergence_ledger_uses_truthful_status_taxonomy() -> None:
    ledger = (
        REPO_ROOT / ".aios" / "state" / "PRODUCTION_CONVERGENCE_LEDGER.md"
    ).read_text(encoding="utf-8")

    assert "**DONE**" not in ledger
    for status in ("VERIFIED", "PARTIAL", "DORMANT", "BLOCKED"):
        assert status in ledger
    assert "Real Human Sovereign principal | **PARTIAL**" in ledger
    assert "Exact capabilities | **PARTIAL**" in ledger
    assert "TurnCoordinator | **VERIFIED**" in ledger
    assert "PromotionAuthority | **PARTIAL**" in ledger
    assert "EmergencyStopController | **PARTIAL**" in ledger
    assert "Isolated Executor Service | **PARTIAL**" in ledger
