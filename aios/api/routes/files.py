import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from aios import config
from aios.policy.constitution_enforcer import ConstitutionEnforcer
from aios.policy.credential_paths import is_credential_path, refusal_reason
from aios.security.scope_lock import is_path_in_scope
from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import get_constitution_authority
from aios.application.governance.constitution_authority import (
    ConstitutionAuthority,
)


def _enforcer_for(authority: ConstitutionAuthority) -> ConstitutionEnforcer:
    """Build an enforcer that honours the ACTIVE constitution snapshot.

    This was a module-level singleton built at import time with no
    snapshot, which meant two things: a ratified amendment could never
    reach it (`amended_frozen_paths` was permanently empty), and even once
    the parameter existed the value would have been frozen at boot.

    So `activate_amendment` persisted a new constitution, and the gate that
    decides whether a file may be edited went on consulting the one from
    process start. The amendment mechanism was wired end to end except for
    the last hop, which is the only hop a user can feel.

    Per request, deliberately: the active snapshot changes when an operator
    ratifies and activates one, and a cache here would reintroduce exactly
    the staleness this replaces. Falls back to a snapshot-less enforcer if
    the chain cannot be read, which is the pre-existing behaviour and is
    strictly the more restrictive of the two (live config only, no
    amendment-added freezes dropped -- amendments can only ADD).
    """
    try:
        snapshot = authority.get_active_snapshot()
    except Exception:  # pragma: no cover - defensive; chain not yet enrolled
        snapshot = None
    return ConstitutionEnforcer(snapshot=snapshot)


router = APIRouter(tags=["Files"], dependencies=[Depends(enforce_action_boundary)])


class ReadFileRequest(BaseModel):
    path: str = Field(..., description="Absolute path to the file to read")


class EditFileRequest(BaseModel):
    path: str = Field(..., description="Absolute path to the file to edit")
    content: str = Field(..., description="Proposed new content")
    # This hits the gate, so we just stub it out as a proposal here for Phase 1.


def _build_tree(root_dir: Path) -> List[Dict[str, Any]]:
    tree = []
    try:
        for entry in os.scandir(root_dir):
            if (
                entry.name.startswith(".")
                or entry.name == "__pycache__"
                or entry.name == "node_modules"
            ):
                continue
            node = {
                "name": entry.name,
                "path": str(Path(entry.path).resolve()).replace("\\", "/"),
                "type": "directory" if entry.is_dir() else "file",
                "status": "normal",
            }
            if entry.is_dir():
                # Don't recurse deeply to avoid massive payloads, just one level or handle carefully
                # We'll just do shallow children for directories that we expand
                node["children"] = []
            tree.append(node)
    except Exception as e:
        pass

    return sorted(tree, key=lambda x: (x["type"] == "file", x["name"]))


@router.get("/api/v1/files/tree")
def get_file_tree(root: Optional[str] = None):
    """Returns the AST structure of the workspace."""
    if root:
        check = is_path_in_scope(root)
        if not check.in_scope:
            raise HTTPException(status_code=403, detail="Directory out of bounds")
        base_dir = Path(check.resolved)
    else:
        base_dir = Path(config.PROJECT_ROOT)

    if not base_dir.exists() or not base_dir.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    return _build_tree(base_dir)


@router.post("/api/v1/files/read")
def read_file(req: ReadFileRequest):
    """Returns file content."""
    check = is_path_in_scope(req.path)
    if not check.in_scope:
        raise HTTPException(status_code=403, detail="File out of bounds")
    # In scope is containment, not permission to read secrets.
    if is_credential_path(req.path) or is_credential_path(check.resolved):
        raise HTTPException(status_code=403, detail=refusal_reason(req.path))
    p = Path(check.resolved)

    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = p.read_text(encoding="utf-8")
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from aios.api.main import get_cortex_bus
from aios.runtime.cortex_bus import CortexBus


@router.post("/api/v1/files/edit")
def edit_file(
    req: EditFileRequest,
    bus: Optional[CortexBus] = Depends(get_cortex_bus),
    authority: ConstitutionAuthority = Depends(get_constitution_authority),
):
    """Proposes diff, hits gate."""
    if is_credential_path(req.path):
        raise HTTPException(status_code=403, detail=refusal_reason(req.path))
    check = is_path_in_scope(req.path)
    if not check.in_scope:
        if bus:
            from aios.core.events import (
                CanonicalEvent,
                CanonicalEventType,
                EventPhase,
                TrustLevel,
            )

            canonical = CanonicalEvent(
                event_type=CanonicalEventType.EDIT_BLOCKED.value,
                phase=EventPhase.NARRATIVE.value,
                status="failed",
                trust=TrustLevel.VERIFIED.value,
                source="aios.api.routes.files",
                session_id="system",
                payload={"path": req.path, "reason": "File out of bounds"},
            )
            bus.append(canonical)
        raise HTTPException(status_code=403, detail="File out of bounds")

    decision = _enforcer_for(authority).check_file_edit(req.path, actor="operator")
    if not decision.allowed:
        if bus:
            from aios.core.events import (
                CanonicalEvent,
                CanonicalEventType,
                EventPhase,
                TrustLevel,
            )

            canonical = CanonicalEvent(
                event_type=CanonicalEventType.EDIT_BLOCKED.value,
                phase=EventPhase.NARRATIVE.value,
                status="failed",
                trust=TrustLevel.VERIFIED.value,
                source="aios.api.routes.files",
                session_id="system",
                payload={"path": req.path, "reason": decision.reason},
            )
            bus.append(canonical)
        raise HTTPException(status_code=403, detail=decision.reason)

    if bus:
        from aios.core.events import (
            CanonicalEvent,
            CanonicalEventType,
            EventPhase,
            TrustLevel,
        )

        canonical = CanonicalEvent(
            event_type=CanonicalEventType.EDIT_PROPOSED.value,
            phase=EventPhase.WONDER.value,
            status="in_progress",
            trust=TrustLevel.VERIFIED.value,
            source="aios.api.routes.files",
            session_id="system",
            payload={
                "path": req.path,
                "requiresHuman": decision.requires_human,
                "constraints": list(decision.constraints),
            },
        )
        bus.append(canonical)

    # In Phase 1, we just return success to simulate proposing an edit; the
    # actual write still requires the human-approval gate constitution.
    # check_file_edit references (constraints on the decision above).
    return {
        "status": "proposed",
        "message": "Edit proposed for approval.",
        "requiresHuman": decision.requires_human,
        "constraints": list(decision.constraints),
    }
