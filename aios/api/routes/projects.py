"""Project Passport / RepoMap routes.

The endpoint is intentionally a read-only harvester. It returns proposal/evidence
and does not promote scanned data into trusted memory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aios.memory.project_passport import ProjectPassport
from aios.memory.project_passport import RepoScanLimits, harvest_project_passport


router = APIRouter()
_LAST_PROJECT_PASSPORT_SCAN: dict[str, object] | None = None


class ProjectPassportScanRequest(BaseModel):
    root: Optional[str] = Field(
        None,
        description="Repo path to scan. Relative paths resolve under the current workspace.",
    )
    max_files: int = Field(500, ge=1, le=2000, alias="maxFiles")

    model_config = {"populate_by_name": True}


@router.post("/api/v1/projects/passport/scan")
def scan_project_passport(req: ProjectPassportScanRequest) -> dict:
    """Return a local-only Project Passport as proposal/evidence."""
    global _LAST_PROJECT_PASSPORT_SCAN
    workspace = Path.cwd().resolve()
    root = _resolve_scan_root(req.root, workspace)
    try:
        passport = harvest_project_passport(root, limits=RepoScanLimits(max_files=req.max_files))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _LAST_PROJECT_PASSPORT_SCAN = _project_passport_summary(passport)
    return passport.as_dict()


@router.get("/api/v1/projects/passport/status")
def project_passport_status() -> dict:
    """Return status for the local-only RepoMap harvester without scanning."""
    return {
        "available": True,
        "localOnly": True,
        "activation": "proposal/evidence",
        "trustedMemoryActivated": False,
        "lastScan": _LAST_PROJECT_PASSPORT_SCAN,
    }


def _project_passport_summary(passport: ProjectPassport) -> dict[str, object]:
    return {
        "root": passport.root,
        "generatedAt": passport.generated_at,
        "purpose": passport.purpose,
        "stack": list(passport.stack),
        "keyFileCount": len(passport.key_files),
        "evidenceFileCount": len(passport.evidence_files),
        "suggestedImprovementCount": len(passport.suggested_improvements),
    }


def _resolve_scan_root(raw: Optional[str], workspace: Path) -> Path:
    if raw is None or not raw.strip():
        return workspace
    requested = Path(raw)
    
    # Use CodeQL-recognized path sanitization pattern
    import os
    workspace_real = os.path.realpath(str(workspace))
    target_real = os.path.realpath(os.path.join(workspace_real, str(requested)) if not requested.is_absolute() else str(requested))
    
    if target_real != workspace_real and not target_real.startswith(workspace_real + os.sep):
        raise HTTPException(status_code=403, detail="scan root must stay inside the current workspace")
        
    target = Path(target_real)
    if target == Path.home().resolve() or target.anchor == str(target):
        raise HTTPException(status_code=403, detail="refusing to scan broad home/root path")
        
    return target
