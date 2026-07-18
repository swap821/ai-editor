"""API routes for managing the Maintenance Center."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import (
    get_maintenance_finding_repository,
    get_maintenance_scan_repository,
)
from aios.domain.maintenance.repository import MaintenanceFindingRepository
from aios.domain.maintenance.scan_repository import MaintenanceScanRepository

router = APIRouter(
    tags=["maintenance-center"], dependencies=[Depends(enforce_action_boundary)]
)


@router.get("/api/v1/maintenance/findings")
def list_maintenance_findings(
    repository: MaintenanceFindingRepository = Depends(
        get_maintenance_finding_repository
    ),
) -> dict[str, Any]:
    """List durable scanner findings without inventing operational state."""
    items = [finding.model_dump(mode="json") for finding in repository.list_findings()]
    return {
        "items": items,
        "status": "available" if items else "empty",
        "source": "durable_repository",
    }


@router.get("/api/v1/maintenance/scans")
def list_maintenance_scans(
    repository: MaintenanceScanRepository = Depends(get_maintenance_scan_repository),
) -> dict[str, Any]:
    """List persisted bounded-scan metadata only."""
    items = [scan.model_dump(mode="json") for scan in repository.list_scans()]
    return {
        "items": items,
        "status": "available" if items else "empty",
        "source": "durable_repository",
    }
