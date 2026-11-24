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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from aios import config
from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import (
    get_authenticated_principal,
    get_emergency_stop,
    require_privileged_operator,
)
from aios.application.observability import brief as gagos_brief
from aios.application.capabilities.envelope import EnvelopeAuthority, EnvelopeRefused
from aios.application.capabilities.skill_envelope import (
    SkillEnvelopeAuthority,
    SkillEnvelopeRefused,
)
from aios.domain.capabilities.skill_envelope import (
    MAX_ACTIVATIONS,
    MAX_DAYS,
    SkillEnvelopeError,
    SkillEnvelopeTerms,
)
from aios.domain.capabilities.envelope import (
    MAX_DAYS as MAX_ENVELOPE_DAYS,
    MAX_HOURS,
    MAX_MISSIONS,
    EnvelopeError,
    EnvelopeTerms,
)
from aios.domain.identity.models import Principal, PrincipalType
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
    #: 0: a day envelope. 1 to 30: a standing one (2026-11-24), hours 24,
    #: maxMissions a cap per UTC day.
    days: int = Field(default=0, ge=0, le=MAX_ENVELOPE_DAYS)


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
    """His signature: GAGOS may originate up to *maxMissions* missions in
    *folders*, of *kinds*, for *hours* -- or, with *days*, up to *maxMissions*
    a day for that many days -- delivered by PR only. A newer signature ends
    the older envelope."""
    try:
        terms = EnvelopeTerms.build(
            folders=body.folders,
            kinds=body.kinds,
            max_missions=body.maxMissions,
            hours=body.hours,
            days=body.days,
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


# -- the standing skill envelope (the operator, 2026-11-18) ---------------------


def get_gagos_skill_envelope_authority() -> SkillEnvelopeAuthority:
    """The skill envelope authority, beside the mission envelope in the
    capabilities store and governed by the same durable stop; tests override
    this."""
    return SkillEnvelopeAuthority(
        db_path=config.CAPABILITY_DB_PATH, emergency_stop=get_emergency_stop()
    )


class SignSkillEnvelopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    days: int = Field(ge=1, le=MAX_DAYS)
    maxActivations: int = Field(ge=1, le=MAX_ACTIVATIONS)


@router.get("/api/gagos/skill-envelope")
def skill_envelope_status(
    principal: Principal = Depends(require_privileged_operator),
    authority: SkillEnvelopeAuthority = Depends(get_gagos_skill_envelope_authority),
) -> dict:
    return {"skillEnvelope": authority.status()}


@router.post("/api/gagos/skill-envelope", status_code=201)
def sign_skill_envelope(
    body: SignSkillEnvelopeRequest,
    principal: Principal = Depends(require_privileged_operator),
    authority: SkillEnvelopeAuthority = Depends(get_gagos_skill_envelope_authority),
) -> dict:
    """His standing signature for skills: for *days*, GAGOS may activate up
    to *maxActivations* review-ready candidate skills without asking him each
    time; never a suspended one. A newer signature ends the older envelope,
    and the emergency stop ends it for good."""
    try:
        terms = SkillEnvelopeTerms.build(
            days=body.days, max_activations=body.maxActivations
        )
        authority.sign(terms, principal=principal)
    except (SkillEnvelopeError, SkillEnvelopeRefused) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"skillEnvelope": authority.status()}


@router.post("/api/gagos/skill-envelope/revoke")
def revoke_skill_envelope(
    principal: Principal = Depends(require_privileged_operator),
    authority: SkillEnvelopeAuthority = Depends(get_gagos_skill_envelope_authority),
) -> dict:
    ended = authority.revoke(principal=principal)
    return {"ended": ended, "skillEnvelope": authority.status()}


# -- GAGOS speaks first (2026-11-24) ---------------------------------------------

#: How far back a first brief looks when the face has never asked before.
BRIEF_FIRST_LOOK = timedelta(hours=24)
#: The furthest back a brief looks, however long he was away.
BRIEF_LONGEST_LOOK = timedelta(days=30)


def require_operator_session(
    principal: Principal = Depends(get_authenticated_principal),
) -> Principal:
    """A signed-in operator. The brief only reads, so it needs no fresh
    re-authentication; everything that changes something stays privileged."""
    if principal.principal_type is not PrincipalType.OPERATOR:
        raise HTTPException(status_code=403, detail="Human Sovereign operator required")
    return principal


def get_organ_ledger_path() -> Path:
    """The organ ledger the brief reads; tests override this."""
    return config.PROJECT_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"


def _stop_engaged() -> bool:
    stop = get_emergency_stop()
    try:
        return bool(stop is not None and stop.is_engaged())
    except Exception:  # noqa: BLE001 - an unreadable stop is reported, not hidden
        return True


@router.get("/api/gagos/brief")
def brief(
    since: str | None = None,
    principal: Principal = Depends(require_operator_session),
    ledger: DailyLedger = Depends(get_gagos_task_ledger),
    envelope: EnvelopeAuthority = Depends(get_gagos_envelope_authority),
    skills: SkillEnvelopeAuthority = Depends(get_gagos_skill_envelope_authority),
    organ_ledger: Path = Depends(get_organ_ledger_path),
    stop_engaged: bool = Depends(_stop_engaged),
) -> dict:
    """What GAGOS tells him first when he opens the face (the operator,
    2026-11-24: GAGOS should behave like Jarvis): what it did since *since*,
    what waits on him, what broke. Facts only, read from its own stores."""
    now = datetime.now(timezone.utc)
    start = now - BRIEF_FIRST_LOOK
    if since:
        try:
            asked = datetime.fromisoformat(since)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="since is not a time") from exc
        if asked.tzinfo is None:
            asked = asked.replace(tzinfo=timezone.utc)
        start = min(max(asked, now - BRIEF_LONGEST_LOOK), now)
    told = gagos_brief.gather(
        since=start,
        now=now,
        ledger_db=ledger.path,
        organ_ledger_path=organ_ledger,
        mission_envelope=envelope.status(),
        skill_envelope=skills.status(),
        stop_engaged=stop_engaged,
    )
    return {"brief": told.as_dict()}
