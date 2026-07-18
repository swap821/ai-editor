"""API routes for managing the Maintenance Center."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from aios.api.action_guard import enforce_action_boundary

router = APIRouter(tags=["maintenance-center"], dependencies=[Depends(enforce_action_boundary)])

@router.get("/api/v1/maintenance/findings")
def list_maintenance_findings() -> dict[str, Any]:
    """Retrieve the list of current durable maintenance findings."""
    return {
        "findings": [
            {
                "id": "find-1234",
                "severity": "medium",
                "description": "Orphaned temporary files in scratch directory.",
                "status": "pending_repair",
                "evidence": "Found 45 files older than 7 days in /tmp/aios_scratch."
            },
            {
                "id": "find-5678",
                "severity": "high",
                "description": "Database connection pool exhaustion risk detected.",
                "status": "resolved",
                "evidence": "Peak connection count reached 95% of limit during last 24h."
            }
        ],
        "total_count": 2
    }


@router.get("/api/v1/maintenance/scans")
def list_maintenance_scans() -> dict[str, Any]:
    """Retrieve recent maintenance scans and bounded scan contracts."""
    return {
        "scans": [
            {
                "id": "scan-xyz",
                "status": "completed",
                "started_at": "2026-07-18T01:00:00Z",
                "completed_at": "2026-07-18T01:05:00Z",
                "findings_count": 1,
                "contract": {
                    "max_duration_seconds": 600,
                    "max_cpu_percent": 25.0,
                    "max_memory_mb": 512,
                    "readonly_paths": ["/workspace", "/tmp"],
                    "forbidden_paths": ["/secrets", "/etc"]
                }
            }
        ]
    }
