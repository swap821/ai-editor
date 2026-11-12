"""The operator's tasks for GAGOS: the counter's three doors (2026-11-03).

He describes a change on one file, or on up to five together, in plain words; GAGOS's workshop reads the
ledger's open tasks, has its writers make the change, runs the tests in the
sandbox, asks Claude Code to review it, and opens its own PR. This module only
puts tasks into that ledger, lists them with how far each has come, and lets him
cancel one nobody has taken yet. It never runs a writer and never calls a model.

GAGOS's daily envelope (2026-11-12) is his here too: he signs it, reads it, and
ends it (organ 9's envelope authority, :mod:`aios.application.capabilities
.envelope`). GAGOS's missions are admitted into it elsewhere; this module only
carries his acts.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from aios import config
from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import get_emergency_stop, require_privileged_operator
from aios.application.capabilities.envelope import EnvelopeAuthority, EnvelopeRefused
from aios.domain.capabilities.envelope import (
    MAX_HOURS,
    MAX_MISSIONS,
    EnvelopeError,
    EnvelopeTerms,
)
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


def get_gagos_envelope_authority() -> EnvelopeAuthority:
    """Organ 9's envelope authority, beside the exact capabilities and governed
    by the one durable stop; tests override this."""
    return EnvelopeAuthority(
        db_path=config.CAPABILITY_DB_PATH, emergency_stop=get_emergency_stop()
    )


class SignEnvelopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    folders: list[Annotated[str, Field(min_length=1, max_length=512)]] = Field(
        min_length=1, max_length=20
    )
    kinds: list[Annotated[str, Field(min_length=1, max_length=16)]] = Field(
        min_length=1, max_length=4
    )
    maxMissions: int = Field(ge=1, le=MAX_MISSIONS)
    hours: int = Field(ge=1, le=MAX_HOURS)


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


@router.get("/api/gagos/envelope")
def envelope_status(
    principal: Principal = Depends(require_privileged_operator),
    authority: EnvelopeAuthority = Depends(get_gagos_envelope_authority),
) -> dict:
    return {"envelope": authority.status()}


@router.post("/api/gagos/envelope", status_code=201)
def sign_envelope(
    body: SignEnvelopeRequest,
    principal: Principal = Depends(require_privileged_operator),
    authority: EnvelopeAuthority = Depends(get_gagos_envelope_authority),
) -> dict:
    """His once-a-day signature: GAGOS may originate up to *maxMissions*
    missions in *folders*, of *kinds*, for *hours*, delivered by PR only. A
    newer signature ends the older envelope."""
    try:
        terms = EnvelopeTerms.build(
            folders=body.folders,
            kinds=body.kinds,
            max_missions=body.maxMissions,
            hours=body.hours,
        )
        authority.sign(terms, principal=principal)
    except (EnvelopeError, EnvelopeRefused) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"envelope": authority.status()}


@router.post("/api/gagos/envelope/revoke")
def revoke_envelope(
    principal: Principal = Depends(require_privileged_operator),
    authority: EnvelopeAuthority = Depends(get_gagos_envelope_authority),
) -> dict:
    ended = authority.revoke(principal=principal)
    return {"ended": ended, "envelope": authority.status()}
