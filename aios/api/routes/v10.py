"""Backend-backed v10 truth surface routes.

The v10 scaffold is an architectural contract, not an authority path. These
routes expose the current local evidence surfaces for the frontend without
creating a new executor, scanner daemon, or approval bypass.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aios import config
from aios.learning.meta_loop import assess_meta_loop, collect_meta_loop_evidence
from aios.maintenance.ecosystem_scanner import EcosystemReport, scan_environment
from aios.maintenance.vulture_sanitation import VultureReport, scan_vulture_targets
from aios.policy.constitution import build_constitution
from aios.api.action_guard import enforce_action_boundary

router = APIRouter(dependencies=[Depends(enforce_action_boundary)])

_LAST_VULTURE_SCAN: dict[str, Any] | None = None
_LAST_ECOSYSTEM_SCAN: dict[str, Any] | None = None


class VultureScanRequest(BaseModel):
    targets: dict[str, str] | None = None


class EcosystemScanRequest(BaseModel):
    root: str | None = None
    include_git_history: bool = Field(False, alias="includeGitHistory")

    model_config = {"populate_by_name": True}


@router.get("/api/v1/v10/status")
def v10_status() -> dict[str, Any]:
    """Return a read-only aggregate of v10 organs already backed by code."""
    meta_loop = assess_meta_loop(collect_meta_loop_evidence()).as_dict()
    return {
        "activation": "proposal/evidence",
        "authority": "proposal/evidence",
        "localOnly": True,
        "cloudCalls": 0,
        "writesPerformed": False,
        "canAuthorize": False,
        "constitution": _constitution_status(),
        "vulture": _scanner_status(_LAST_VULTURE_SCAN),
        "ecosystem": _scanner_status(_LAST_ECOSYSTEM_SCAN, network_key=True),
        "councilMemory": _council_memory_status(),
        "symbolRepoMap": _symbol_repo_map_status(),
        "metaLoop": {
            "available": True,
            "activation": meta_loop["activation"],
            "authority": meta_loop["authority"],
            "localOnly": meta_loop["localOnly"],
            "cloudCalls": meta_loop["cloudCalls"],
            "writesPerformed": meta_loop["writesPerformed"],
            "policyMutations": meta_loop["policyMutations"],
            "selfApplyAttempted": meta_loop["selfApplyAttempted"],
            "canAuthorize": meta_loop["canAuthorize"],
            "safetyStatus": meta_loop["safetyStatus"],
            "proposalCount": len(meta_loop["proposals"]),
            "blockerCount": len(meta_loop["blockers"]),
        },
    }


@router.post("/api/v1/v10/vulture/scan")
def v10_vulture_scan(req: VultureScanRequest | None = None) -> dict[str, Any]:
    """Run the read-only vulture scanner over supplied or default text evidence."""
    global _LAST_VULTURE_SCAN
    request = req or VultureScanRequest()
    targets = request.targets or _default_vulture_targets()
    report = scan_vulture_targets(targets)
    _LAST_VULTURE_SCAN = _vulture_summary(report, target_count=len(targets))
    return {"lastScan": _LAST_VULTURE_SCAN}


@router.post("/api/v1/v10/ecosystem/scan")
def v10_ecosystem_scan(req: EcosystemScanRequest | None = None) -> dict[str, Any]:
    """Run the local-only ecosystem scanner over manifests under a safe root."""
    global _LAST_ECOSYSTEM_SCAN
    request = req or EcosystemScanRequest()
    root = _resolve_scan_root(request.root, Path.cwd().resolve())
    report = scan_environment(root)
    if request.include_git_history:
        from aios.maintenance.ecosystem_scanner import EcosystemScanner

        report = EcosystemReport(
            findings=tuple(report.findings)
            + tuple(EcosystemScanner().scan_git_history(root).findings)
        )
    _LAST_ECOSYSTEM_SCAN = _ecosystem_summary(report, root)
    return {"lastScan": _LAST_ECOSYSTEM_SCAN}


def _constitution_status() -> dict[str, Any]:
    constitution = build_constitution()
    return {
        "available": True,
        "activation": "executable/facade",
        "authority": "strengthen-only",
        "frozenCoreProtected": "aios/security/" in constitution.frozen_path_prefixes,
        "frozenPathPrefixes": list(constitution.frozen_path_prefixes),
        "scopeRootCount": len(constitution.scope_roots),
        "routerCloudTasks": list(constitution.router_cloud_tasks),
        "routerPreferLocal": constitution.router_prefer_local,
        "routerMaxCost": constitution.router_max_cost,
        "resourceMode": str(constitution.resource_mode),
        "earnedAutonomyEnabled": constitution.earned_autonomy_enabled,
        "earnedAutonomyMinSuccesses": constitution.earned_autonomy_min_successes,
        "policyEngineEnabled": constitution.policy_engine_enabled,
        "casteCount": len(constitution.castes),
        "canAuthorize": False,
    }


def _scanner_status(
    last_scan: dict[str, Any] | None,
    *,
    network_key: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "available": True,
        "activation": "proposal/evidence",
        "authority": "proposal/evidence",
        "localOnly": True,
        "writesPerformed": False,
        "cloudCalls": 0,
        "canAuthorize": False,
        "lastScan": last_scan,
        "findingCount": int(last_scan.get("findingCount", 0)) if last_scan else None,
    }
    if network_key:
        payload["networkCalls"] = 0
    return payload


def _council_memory_status() -> dict[str, Any]:
    db_path = Path(config.COUNCIL_STATE_DB)
    base = {
        "available": True,
        "activation": "proposal/evidence",
        "authority": "proposal/evidence",
        "canAuthorize": False,
        "eventType": "ganglia_synthesis",
        "deliberationCount": 0,
        "lastEvent": None,
    }
    if not db_path.exists():
        return base
    try:
        with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='council_events'"
            ).fetchone()
            if table is None:
                return base
            count = conn.execute(
                "SELECT COUNT(*) FROM council_events WHERE event_type = ?",
                ("ganglia_synthesis",),
            ).fetchone()[0]
            last = conn.execute(
                "SELECT mission_id, risk, created_at FROM council_events "
                "WHERE event_type = ? ORDER BY id DESC LIMIT 1",
                ("ganglia_synthesis",),
            ).fetchone()
    except sqlite3.Error:
        return base | {"status": "unreadable"}
    return base | {
        "deliberationCount": int(count),
        "lastEvent": dict(last) if last is not None else None,
    }


def _symbol_repo_map_status() -> dict[str, Any]:
    from aios.api.routes.projects import symbol_repo_map_status

    return symbol_repo_map_status()


def _default_vulture_targets() -> dict[str, str]:
    targets: dict[str, str] = {}
    for rel in (
        ".aios/memory/warnings.md",
        ".aios/state/RESUME.md",
        ".aios/state/V10_INTEGRATION_PLAN.md",
        ".aios/state/V10_INTEGRATION_AUDIT.md",
    ):
        path = Path(rel)
        if path.exists() and path.is_file():
            targets[rel] = path.read_text(encoding="utf-8", errors="replace")
    return targets


def _vulture_summary(report: VultureReport, *, target_count: int) -> dict[str, Any]:
    return _finding_summary(
        report.to_dict(),
        extra={"targetCount": target_count},
    )


def _ecosystem_summary(report: EcosystemReport, root: Path) -> dict[str, Any]:
    return _finding_summary(
        report.to_dict(),
        extra={"root": str(root), "networkCalls": report.network_calls},
    )


def _finding_summary(
    payload: dict[str, Any], *, extra: dict[str, Any]
) -> dict[str, Any]:
    findings = list(payload.get("findings") or [])
    severities = [
        str(item.get("severity", "")).lower()
        for item in findings
        if isinstance(item, dict)
    ]
    return {
        "ranAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "activation": payload.get("activation", "proposal/evidence"),
        "authority": "proposal/evidence",
        "localOnly": payload.get("local_only") is True,
        "writesPerformed": payload.get("writes_performed") is True,
        "cloudCalls": int(payload.get("cloud_calls") or 0),
        "findingCount": len(findings),
        "criticalCount": severities.count("critical"),
        "highCount": severities.count("high"),
        "topFindings": [
            {
                "kind": item.get("kind"),
                "severity": item.get("severity"),
                "targetId": item.get("target_id"),
                "recommendation": item.get("recommendation"),
            }
            for item in findings[:5]
            if isinstance(item, dict)
        ],
    } | extra


def _resolve_scan_root(raw: str | None, workspace: Path) -> Path:
    if raw is None or not raw.strip():
        return workspace
    requested = Path(raw)
    target = (
        requested.resolve()
        if requested.is_absolute()
        else (workspace / requested).resolve()
    )
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise HTTPException(
            status_code=403, detail="scan root must stay inside the current workspace"
        ) from exc
    if target == Path.home().resolve() or target.anchor == str(target):
        raise HTTPException(
            status_code=403, detail="refusing to scan broad home/root path"
        )
    return target
