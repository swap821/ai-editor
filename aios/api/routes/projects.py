"""Project Passport / RepoMap routes.

The endpoint is intentionally a read-only harvester. It returns proposal/evidence
and does not promote scanned data into trusted memory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import hashlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aios.api.deps import get_project_passport_store
from aios.application.governance.organ_ledger import current_commit_sha
from aios.application.memory.human_representation import build_project_passport_v1
from aios.cognition.repo_map import (
    SymbolRepoMapLimits,
    scan_symbol_repo_map,
    scope_hints_for_contract,
)
from aios.infrastructure.memory.human_representation_store import ProjectPassportStore
from aios.memory.project_passport import ProjectPassport
from aios.memory.project_passport import RepoScanLimits, harvest_project_passport
from aios.runtime.contracts import MissionContract
from aios.api.action_guard import enforce_action_boundary


router = APIRouter(dependencies=[Depends(enforce_action_boundary)])
_LAST_PROJECT_PASSPORT_SCAN: dict[str, object] | None = None
_LAST_PROJECT_PASSPORT_ID: str | None = None
_LAST_SYMBOL_REPO_MAP_SCAN: dict[str, object] | None = None


class ProjectPassportScanRequest(BaseModel):
    root: Optional[str] = Field(
        None,
        description="Repo path to scan. Relative paths resolve under the current workspace.",
    )
    max_files: int = Field(500, ge=1, le=2000, alias="maxFiles")

    model_config = {"populate_by_name": True}


@router.post("/api/v1/projects/passport/scan")
def scan_project_passport(
    req: ProjectPassportScanRequest,
    store: ProjectPassportStore = Depends(get_project_passport_store),
) -> dict:
    """Return a local-only Project Passport as proposal/evidence.

    Organ 28: also builds the typed ProjectPassportV1 (Slice 28) from this
    same real scan and records it durably (append-only, digest-verified,
    ProjectPassportStore) -- previously build_project_passport_v1() had zero
    production callers anywhere; every real scan silently discarded the
    typed representation this organ exists to provide. The route's own
    response shape is unchanged (existing frontend callers are unaffected);
    the durable record is additive.
    """
    global _LAST_PROJECT_PASSPORT_SCAN, _LAST_PROJECT_PASSPORT_ID
    workspace = Path.cwd().resolve()
    root = _resolve_scan_root(req.root, workspace)
    try:
        passport = harvest_project_passport(
            root, limits=RepoScanLimits(max_files=req.max_files)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _LAST_PROJECT_PASSPORT_SCAN = _project_passport_summary(passport)

    project_id = _project_id_for_root(root)
    typed_passport = build_project_passport_v1(
        root,
        project_id=project_id,
        verified_at_commit=current_commit_sha(root),
        passport=passport,
    )
    store.save(typed_passport)
    _LAST_PROJECT_PASSPORT_ID = project_id

    return passport.as_dict()


def _project_id_for_root(root: Path) -> str:
    """A stable, per-root identifier so unrelated projects never share one
    passport history. Deterministic (not random) so re-scanning the same
    project always resolves to the same durable history."""
    return hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:32]


@router.get("/api/v1/projects/passport/status")
def project_passport_status(
    store: ProjectPassportStore = Depends(get_project_passport_store),
) -> dict:
    """Return status for the local-only RepoMap harvester without scanning."""
    durable: dict[str, object] | None = None
    if _LAST_PROJECT_PASSPORT_ID is not None:
        current = store.get_current(_LAST_PROJECT_PASSPORT_ID)
        if current is not None:
            history = store.get_history(_LAST_PROJECT_PASSPORT_ID)
            durable = {
                "revisionCount": len(history),
                "passportDigest": current.passport_digest,
                "verifiedAtCommit": current.verified_at_commit,
            }
    return {
        "available": True,
        "localOnly": True,
        "activation": "proposal/evidence",
        "trustedMemoryActivated": False,
        "lastScan": _LAST_PROJECT_PASSPORT_SCAN,
        "durable": durable,
    }


@router.get("/api/v1/projects/symbol-repomap/status")
def symbol_repo_map_status() -> dict[str, Any]:
    """Return status for the symbol-level RepoMap without scanning."""
    return {
        "available": True,
        "localOnly": True,
        "activation": "proposal/evidence",
        "trustedMemoryActivated": False,
        "canWidenScope": False,
        "cloudCalls": 0,
        "lastScan": _LAST_SYMBOL_REPO_MAP_SCAN,
    }


class ScopeHintsRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=4000)
    allowed_files: list[str] = Field(default_factory=list, alias="allowedFiles")
    root: Optional[str] = Field(
        None, description="Repo path to scan. Defaults to the current workspace."
    )
    max_files: int = Field(300, ge=1, le=2000, alias="maxFiles")

    model_config = {"populate_by_name": True}


@router.post("/api/v1/projects/scope-hints")
def scope_hints(req: ScopeHintsRequest) -> dict[str, Any]:
    """Advisory, evidence-only file-scope suggestions for a not-yet-submitted
    mission goal — symbol matches restricted to the goal's own allowed_files,
    never expanding scope. Real repo scan (aios/cognition/repo_map.py), not
    fabricated data; this module previously had zero callers outside its own
    tests anywhere in the codebase."""
    global _LAST_SYMBOL_REPO_MAP_SCAN
    workspace = Path.cwd().resolve()
    root = _resolve_scan_root(req.root, workspace)
    try:
        repo_map = scan_symbol_repo_map(
            root, limits=SymbolRepoMapLimits(max_files=req.max_files)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _LAST_SYMBOL_REPO_MAP_SCAN = _symbol_repo_map_summary(repo_map)
    contract = MissionContract(
        mission_id="scope-hints-preview",
        goal=req.goal,
        worker_type="advisory_preview",
        created_by="operator",
        workspace_root=str(root),
        allowed_files=req.allowed_files,
    )
    hints = scope_hints_for_contract(repo_map, contract)
    return hints.as_dict()


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


def _symbol_repo_map_summary(repo_map: Any) -> dict[str, object]:
    return {
        "root": repo_map.root,
        "generatedAt": repo_map.generated_at,
        "symbolCount": len(repo_map.symbols),
        "edgeCount": len(repo_map.edges),
        "evidenceFileCount": len(repo_map.evidence_files),
        "skippedFileCount": len(repo_map.skipped_files),
        "activation": repo_map.activation,
        "trustedMemoryActivated": repo_map.trusted_memory_activated,
        "localOnly": repo_map.local_only,
        "cloudCalls": repo_map.cloud_calls,
    }


def _resolve_scan_root(raw: Optional[str], workspace: Path) -> Path:
    if raw is None or not raw.strip():
        return workspace
    requested = Path(raw)

    # Use CodeQL-recognized path sanitization pattern
    import os

    workspace_real = os.path.realpath(str(workspace))
    target_real = os.path.realpath(
        os.path.join(workspace_real, str(requested))
        if not requested.is_absolute()
        else str(requested)
    )

    if target_real != workspace_real and not target_real.startswith(
        workspace_real + os.sep
    ):
        raise HTTPException(
            status_code=403, detail="scan root must stay inside the current workspace"
        )

    target = Path(target_real)
    if target == Path.home().resolve() or target.anchor == str(target):
        raise HTTPException(
            status_code=403, detail="refusing to scan broad home/root path"
        )

    return target
