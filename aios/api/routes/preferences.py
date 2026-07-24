"""Operator Taste Model routes (organ 27).

Real production caller for ``OperatorPreferenceStore`` -- previously the
store was constructed only in tests (``tests/test_human_representation_
store.py``); no route could ever save or read a real ``OperatorPreferenceV1``.

This route captures ONLY explicit, operator-stated preferences:
``source_type`` is fixed server-side to ``"explicit_user"`` -- there is no
request field a caller can set to submit any other source_type, so "capture
only explicit preferences" holds structurally, not merely by validation.
``status`` is fixed to ``"active"``: an explicit, direct statement needs no
separate proposal/review step, and the context compiler (organ 31) already
filters ``active_preferences`` on ``status == "active"``
(``aios/application/intelligence/context_compiler.py``).
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import get_operator_preference_store
from aios.application.memory.human_representation import (
    is_operator_preference_expired,
)
from aios.domain.memory.human_representation import OperatorPreferenceV1
from aios.infrastructure.memory.human_representation_store import (
    OperatorPreferenceStore,
)

router = APIRouter(dependencies=[Depends(enforce_action_boundary)])


def _preference_id(scope: str, domain: str, key: str) -> str:
    """Deterministic per (scope, domain, key) id -- re-submitting the "same"
    preference updates the existing row (and lets a genuine value change go
    through SemanticFacts' own contradiction check) instead of silently
    leaving stale duplicate rows behind for the same taste dimension."""
    raw = f"{scope}|{domain}|{key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class OperatorPreferenceRequest(BaseModel):
    """Body for ``POST /api/v1/preferences``. There is deliberately no
    ``source_type`` or ``status`` field: both are fixed server-side."""

    domain: str = Field(..., min_length=1, max_length=200)
    key: str = Field(..., min_length=1, max_length=200)
    value: Any
    scope: str = Field(..., min_length=1, max_length=200)
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    review_after: Optional[str] = Field(None, alias="reviewAfter")

    model_config = {"populate_by_name": True}


@router.post("/api/v1/preferences")
def save_operator_preference(
    req: OperatorPreferenceRequest,
    store: OperatorPreferenceStore = Depends(get_operator_preference_store),
) -> dict[str, Any]:
    """Capture one explicit operator preference."""
    preference_id = _preference_id(req.scope, req.domain, req.key)
    pref = OperatorPreferenceV1(
        preference_id=preference_id,
        domain=req.domain,
        key=req.key,
        value=req.value,
        scope=req.scope,
        confidence=req.confidence,
        source_type="explicit_user",
        review_after=req.review_after,
        status="active",
    )
    result = store.save(pref)
    if not result.saved:
        if result.reason == "contradiction":
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": result.reason,
                    "conflictObject": result.conflict_object,
                },
            )
        raise HTTPException(status_code=422, detail=result.reason)
    saved = store.get(preference_id)
    if saved is None:  # pragma: no cover - save() just committed this row
        raise HTTPException(status_code=500, detail="preference save did not persist")
    return {"preference": saved.as_dict(), "preferenceId": preference_id}


@router.get("/api/v1/preferences")
def list_operator_preferences(
    scope: str,
    store: OperatorPreferenceStore = Depends(get_operator_preference_store),
) -> dict[str, Any]:
    """Every explicit preference recorded for one scope -- always
    scope-filtered (organ 27's own leak-prevention requirement: there is no
    "every scope" listing). Each entry carries a real, computed expiry flag
    rather than requiring the caller to re-derive it."""
    if not scope.strip():
        raise HTTPException(status_code=422, detail="scope is required")
    preferences = store.list_for_scope(scope)
    return {
        "scope": scope,
        "preferences": [
            {**pref.as_dict(), "isExpired": is_operator_preference_expired(pref)}
            for pref in preferences
        ],
    }


@router.get("/api/v1/preferences/active")
def list_active_operator_preferences(
    scope: str,
    store: OperatorPreferenceStore = Depends(get_operator_preference_store),
) -> dict[str, Any]:
    """The subset of ``list_operator_preferences`` a real consumer would
    feed forward as Organ 31's ``active_preferences`` -- ``status ==
    "active"`` AND not expired. Excludes withdrawn/superseded/rejected/
    expired preferences rather than leaving that filtering to every caller."""
    if not scope.strip():
        raise HTTPException(status_code=422, detail="scope is required")
    preferences = [
        pref
        for pref in store.list_active_for_scope(scope)
        if not is_operator_preference_expired(pref)
    ]
    return {"scope": scope, "preferences": [pref.as_dict() for pref in preferences]}


@router.post("/api/v1/preferences/{preference_id}/withdraw")
def withdraw_operator_preference(
    preference_id: str,
    store: OperatorPreferenceStore = Depends(get_operator_preference_store),
) -> dict[str, Any]:
    """Retract a previously stated explicit preference.

    Marks the typed record ``status="withdrawn"`` durably. It does not
    retract the underlying SemanticFacts row (this store never reimplements
    that write path -- see the module docstring on ``OperatorPreferenceStore``
    in ``aios/infrastructure/memory/human_representation_store.py``); an
    operator who then states a genuinely different value for the same
    domain+key+scope still resolves that through the existing human-gated
    ``POST /api/v1/memory/facts/reconcile`` path, unchanged.
    """
    withdrawn = store.withdraw(preference_id)
    if not withdrawn:
        raise HTTPException(status_code=404, detail="preference not found")
    return {"preferenceId": preference_id, "status": "withdrawn"}


__all__ = ["router"]
