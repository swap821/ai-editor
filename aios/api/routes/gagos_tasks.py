"""The operator's tasks for GAGOS: the counter's three doors (2026-11-03).

He describes a change on one file, or on up to five together, in plain words; GAGOS's workshop reads the
ledger's open tasks, has its writers make the change, runs the tests in the
sandbox, asks Claude Code to review it, and opens its own PR. This module only
puts tasks into that ledger, lists them with how far each has come, and lets him
cancel one nobody has taken yet. It never runs a writer and never calls a model.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import require_privileged_operator
from aios.domain.identity.models import Principal
from aios.maintenance.daily_work import (
    ledger_path,
    MAX_TASK_CHARS,
    MAX_TASK_FILES,
    DailyLedger,
    TaskRefused,
)

router = APIRouter(
    tags=["gagos-tasks"], dependencies=[Depends(enforce_action_boundary)]
)

_TASK_ID = re.compile(r"^gt-[0-9a-f]{10}$")
_SAID_BY = "the operator (the counter)"


def get_gagos_task_ledger() -> DailyLedger:
    """The workshop's own ledger file; tests override this with a tmp_path one."""
    return DailyLedger(ledger_path())


class AddTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str = Field(min_length=1, max_length=512)
    text: str = Field(min_length=1, max_length=MAX_TASK_CHARS)
    # More files the same task changes together (2026-11-03, D14).
    also: list[Annotated[str, Field(min_length=1, max_length=512)]] = Field(
        default_factory=list, max_length=MAX_TASK_FILES - 1
    )


def _known_task(ledger: DailyLedger, task_id: str) -> dict:
    # A malformed id can never name a task, so it is the same 404 as an unknown one.
    task = ledger.task(task_id) if _TASK_ID.match(task_id) else None
    if task is None:
        raise HTTPException(status_code=404, detail="no such task")
    return task


@router.get("/api/gagos/tasks")
def list_tasks(
    principal: Principal = Depends(require_privileged_operator),
    ledger: DailyLedger = Depends(get_gagos_task_ledger),
) -> dict:
    return {"tasks": ledger.task_progress()}


@router.post("/api/gagos/tasks", status_code=201)
def add_task(
    body: AddTaskRequest,
    principal: Principal = Depends(require_privileged_operator),
    ledger: DailyLedger = Depends(get_gagos_task_ledger),
) -> dict:
    try:
        task_id = ledger.add_task(
            body.file, body.text, said_by=_SAID_BY, also=tuple(body.also)
        )
    except TaskRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"task": ledger.task(task_id)}


@router.post("/api/gagos/tasks/{task_id}/cancel")
def cancel_task(
    task_id: str,
    principal: Principal = Depends(require_privileged_operator),
    ledger: DailyLedger = Depends(get_gagos_task_ledger),
) -> dict:
    task = _known_task(ledger, task_id)
    if not ledger.cancel_task(task_id):
        raise HTTPException(
            status_code=409,
            detail=f"the task is {task['status']}; only an open task can be cancelled",
        )
    return {"task": ledger.task(task_id)}
