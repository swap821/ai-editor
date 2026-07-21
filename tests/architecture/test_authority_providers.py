"""Architecture tests proving there is one canonical provider path for core authorities."""

import pytest

from aios.api import deps
from aios.application.evidence.verification import VerificationAuthority
from aios.application.promotion.authority import PromotionAuthority
from aios.application.evidence.verifier_registry import VerifierRegistry
from aios.application.executor.service import ExecutorService
from aios.application.workers.foundry import WorkerFoundry


@pytest.mark.architecture
def test_canonical_authority_provider_functions_exist() -> None:
    """Verify that canonical authority provider functions exist in aios.api.deps."""
    assert hasattr(deps, "get_verification_authority")
    assert hasattr(deps, "get_promotion_authority")
    assert hasattr(deps, "get_maintenance_scanner_registry")
    assert hasattr(deps, "get_private_executor_service")
    assert hasattr(deps, "get_worker_foundry")


@pytest.mark.architecture
def test_shared_authority_singleton_instances() -> None:
    """Verify that calling providers returns identical singleton instances."""
    v1 = deps.get_verification_authority()
    v2 = deps.get_verification_authority()
    assert v1 is v2
    assert isinstance(v1, VerificationAuthority)

    p1 = deps.get_promotion_authority()
    p2 = deps.get_promotion_authority()
    assert p1 is p2
    assert isinstance(p1, PromotionAuthority)

    # VerificationAuthority used by promotion_authority must be the same singleton
    assert p1.verification is v1

    r1 = deps.get_maintenance_scanner_registry()
    r2 = deps.get_maintenance_scanner_registry()
    assert r1 is r2
    assert isinstance(r1, VerifierRegistry)
    assert len(r1.scanner_adapters) > 0

    e1 = deps.get_private_executor_service()
    e2 = deps.get_private_executor_service()
    assert e1 is e2
    assert isinstance(e1, ExecutorService)

    w1 = deps.get_worker_foundry()
    w2 = deps.get_worker_foundry()
    assert w1 is w2
    assert isinstance(w1, WorkerFoundry)


@pytest.mark.architecture
def test_learning_and_maintenance_services_share_authorities() -> None:
    """Verify that LearningService and MaintenanceConvergenceService receive identical authorities."""
    learning = deps.get_learning_service()
    maintenance = deps.get_maintenance_convergence_service()

    canonical_verification = deps.get_verification_authority()
    canonical_promotion = deps.get_promotion_authority()

    assert learning.verification_authority is canonical_verification
    assert learning.promotion_authority is canonical_promotion

    assert maintenance.verification_authority is canonical_verification
    assert maintenance.promotion_authority is canonical_promotion
    assert maintenance.verifier_registry is deps.get_maintenance_scanner_registry()
    assert maintenance.executor_service is deps.get_private_executor_service()
    assert maintenance.worker_foundry is deps.get_worker_foundry()
