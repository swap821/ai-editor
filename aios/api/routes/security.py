"""Security-audit surface: real read access to the tamper-evident audit
ledger, real Ed25519 signing-key rotation, and a gated sandbox-reset action.

Extracted as its own router (not folded into system.py) because every route
here is security-operator-facing rather than general system observability.
"""
from __future__ import annotations

import shutil
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aios import config
from aios.api.deps import require_privileged_operator
from aios.domain.identity.models import Principal
from aios.security.audit_logger import (
    AuditError,
    get_anchor,
    list_recent_entries,
    log_action,
    rotate_audit_key,
    verify_chain,
)
from aios.api.action_guard import enforce_action_boundary

router = APIRouter(tags=["Security"], dependencies=[Depends(enforce_action_boundary)])


@router.get("/api/v1/security/audit")
def security_audit(limit: int = 50, zone: Optional[str] = None) -> dict[str, Any]:
    """Return recent audit-ledger entries plus chain-integrity status.

    Real data from the Ed25519-signed hash-chained ledger
    (``aios/security/audit_logger.py``) — not a stub.
    """
    if zone is not None and zone.upper() not in ("GREEN", "YELLOW", "RED"):
        raise HTTPException(status_code=422, detail=f"invalid zone: {zone!r}")
    try:
        entries = list_recent_entries(limit, zone=zone.upper() if zone else None)
        chain = verify_chain()
        anchor = get_anchor()
    except AuditError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "entries": entries,
        "chainValid": chain.valid,
        "chainReason": chain.reason,
        "totalEntries": chain.total_entries,
        "anchor": anchor,
    }


class RotateTokensRequest(BaseModel):
    confirm: bool = Field(False, description="Must be explicitly true to rotate tokens")

@router.post("/api/v1/security/tokens/rotate")
def security_rotate_tokens(
    req: RotateTokensRequest,
    principal: Principal = Depends(require_privileged_operator),
) -> dict[str, Any]:
    """Rotate the audit-ledger's Ed25519 signing key.

    Old entries remain verifiable under the retired key; new entries sign
    with the fresh one. The rotation itself is recorded in the ledger.
    """
    if not req.confirm:
        raise HTTPException(status_code=422, detail="confirm must be true to rotate tokens")
        
    try:
        new_key_id = rotate_audit_key()
        log_action(principal.principal_id, "rotated audit signing key", "YELLOW")
    except AuditError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "rotated", "newKeyId": new_key_id}


class SandboxClearRequest(BaseModel):
    confirm: bool = Field(
        False, description="Must be explicitly true; this deletes sandbox scope-root contents."
    )


@router.post("/api/v1/security/sandbox/clear")
def security_sandbox_clear(
    req: SandboxClearRequest,
    principal: Principal = Depends(require_privileged_operator),
) -> dict[str, Any]:
    """Delete the contents of every configured sandbox scope root.

    Fail-closed on the confirmation flag and on scope: only ever removes
    children of ``config.SCOPE_ROOTS`` (the training_ground/lab playgrounds),
    never the project's own source tree — the same invariant
    ``RollbackEngine`` enforces for git snapshots.
    """
    if not req.confirm:
        raise HTTPException(status_code=422, detail="confirm must be true to clear the sandbox")

    roots = config.SCOPE_ROOTS
    if not roots:
        raise HTTPException(status_code=409, detail="no sandbox scope roots configured")

    removed: list[str] = []
    for root in roots:
        root_resolved = root.resolve()
        if root_resolved == config.PROJECT_ROOT:
            # Should never happen given config, but this is the one action in
            # the codebase that recursively deletes files — the same
            # hard-refusal RollbackEngine applies to its own scope root.
            raise HTTPException(status_code=409, detail="refusing to clear the project root")
        if not root_resolved.exists():
            continue
        for child in root_resolved.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                removed.append(str(child))
            except OSError as exc:
                log_action(principal.principal_id, f"sandbox clear failed for {child}: {exc}", "RED")
                raise HTTPException(status_code=500, detail=f"failed to remove {child}: {exc}") from exc

    log_action(principal.principal_id, f"cleared sandbox scope roots ({len(removed)} entries removed)", "YELLOW")
    return {"status": "cleared", "removedCount": len(removed), "removed": removed}
