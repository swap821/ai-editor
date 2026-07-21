"""Execution-debugger surface: a real, read-only view of Council mission
execution state. Reuses the same mission-artifact scan ``/api/v1/council/
missions`` already performs (KingReport + RunLedger) rather than duplicating
it, framed for a lower-level "what's actually running" debugging view.

Council missions run to completion (or failure) through the worker/
orchestrator pipeline atomically — there is no interruptible step-machine or
pause point in the runtime's execution model (confirmed: RunLedger is a
post-hoc completion record with no in-progress step index). Rather than
fabricate a step/resume action that would silently no-op, those two routes
say so explicitly (501) instead of pretending to control execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aios.api.routes.council import council_missions, get_council_runtime_root
from aios.api.action_guard import enforce_action_boundary

router = APIRouter(
    tags=["Execution Debugger"], dependencies=[Depends(enforce_action_boundary)]
)


@router.get("/api/v1/execution/debugger/state")
def execution_debugger_state(
    limit: int = 20,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Real Council mission execution state (same source as the dashboard)."""
    missions = council_missions(limit=limit, runtime_root=runtime_root)
    return {
        "missions": missions["missions"],
        "count": missions["count"],
        "steppable": False,
        "note": (
            "Council missions execute atomically through the worker pipeline; "
            "there is no interruptible step-machine to pause/resume."
        ),
    }


class DebuggerControlRequest(BaseModel):
    mission_id: str = Field(..., alias="missionId", min_length=1)

    model_config = {"populate_by_name": True}


@router.post("/api/v1/execution/debugger/step")
def execution_debugger_step(req: DebuggerControlRequest) -> dict[str, Any]:
    raise HTTPException(
        status_code=501,
        detail=(
            "Not supported: Council missions have no interruptible step-machine "
            "to step through. This route exists so the UI gets an honest, "
            "explicit answer instead of a phantom-endpoint 404."
        ),
    )


@router.post("/api/v1/execution/debugger/resume")
def execution_debugger_resume(req: DebuggerControlRequest) -> dict[str, Any]:
    raise HTTPException(
        status_code=501,
        detail=(
            "Not supported: Council missions run to completion or failure and "
            "cannot be paused mid-execution, so there is nothing to resume. "
            "This route exists so the UI gets an honest, explicit answer "
            "instead of a phantom-endpoint 404."
        ),
    )
