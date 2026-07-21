"""Red-first tests exposing the verified starting defects in GAGOS R15 production composition."""

from __future__ import annotations

import inspect
import pytest

from aios.api.deps import get_maintenance_convergence_service
from aios.application.executor.service import IsolationUnavailable
from aios.application.workers.foundry import WorkerFoundry
from aios.api.routes import maintenance as maintenance_routes


def test_defect1_canonical_maintenance_has_admitted_scanner() -> None:
    """Defect 1: Canonical maintenance dependency constructs VerifierRegistry(scanner_adapters={})."""
    service = get_maintenance_convergence_service()
    assert (
        len(service.verifier_registry.scanner_adapters) > 0
    ), "Production VerifierRegistry has no admitted scanner adapters registered"


def test_defect2_canonical_worker_foundry_can_execute_code_work() -> None:
    """Defect 2: Canonical WorkerFoundry cannot execute repair code work."""
    service = get_maintenance_convergence_service()
    foundry = service.worker_foundry
    assert getattr(foundry, "runtime_root", None) is not None, "WorkerFoundry has no runtime_root configured"
    assert getattr(foundry, "spawner", None) is not None, "WorkerFoundry has no spawner configured"


def test_defect3_maintenance_invokes_executor_service() -> None:
    """Defect 3: MaintenanceConvergenceService.run_approved_repair must invoke executor_service."""
    service = get_maintenance_convergence_service()
    # Inspect run_approved_repair implementation to ensure executor_service is invoked
    source = inspect.getsource(service.run_approved_repair)
    assert "executor_service" in source or "self.executor_service.execute" in source, (
        "run_approved_repair does not submit a job to executor_service"
    )


def test_defect4_production_executor_composition_is_valid() -> None:
    """Defect 4: Production ExecutorService requires a configured StructuredExecutorClient."""
    service = get_maintenance_convergence_service()
    executor_service = service.executor_service
    assert executor_service.profile == "production"
    assert executor_service.client is not None, (
        "Production ExecutorService has client=None, which raises IsolationUnavailable on execute()"
    )


def test_defect5_mounted_repair_route_uses_canonical_callbacks() -> None:
    """Defect 5: Mounted repair route must not supply dummy lambda callbacks to run_approved_repair."""
    source = inspect.getsource(maintenance_routes.run_approved_repair)
    assert "capability_consumer=lambda" not in source, "Route supplies dummy capability_consumer lambda"
    assert "create_checkpoint=lambda" not in source, "Route supplies dummy create_checkpoint lambda"
    assert "restore_checkpoint=lambda" not in source, "Route supplies dummy restore_checkpoint lambda"
    assert "smoke_test=lambda" not in source, "Route supplies dummy smoke_test lambda"
