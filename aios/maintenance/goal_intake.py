"""Goals through the clerk: phase 1 of the operator's one-system plan (2026-11-11).

The README's mission flow begins: "01 The human declares the goal -> 02 Shared
understanding identifies constraints and uncertainty -> 03 The local clerk
classifies the task and prepares a briefing". Until now GAGOS's tasks went
straight to one-shot writers beside those organs. Here each goal goes to the
local clerk (organs 35-38) first, through the clerk's own governed service,
which records every job in the clerk's provenance store:

1. ``triage`` -- severity, area, and whether a frontier brain or the operator
   must look before any change (``escalate``);
2. ``prepare_briefing`` -- the goal restated, the files exactly as named, the
   constraints and what decides "done": the briefing a stronger model reads.

Both are asked exactly as organ 37's qualification asks them
(``aios.domain.local_workforce.goal_jobs``), so a model granted a job has been
measured on that job. A briefed goal also becomes the Queen Council's own
:class:`CouncilMissionRequest`, kept for phase 2 (the council plans it) and
phase 3 (it runs as a mission under the operator's daily envelope).

The clerk is advisory: it decides no authority, writes no file, runs nothing,
and blocks nothing. A clerk that cannot answer -- no model granted the job
yet, or an answer that is not a triage or a briefing -- leaves the goal
waiting for it, saying why; nothing is guessed in its place, and the
workshop's writers work on the goal as before.

``check_context_completeness`` is not asked: its qualification case hands the
model its answer, so a grant would not show the model can judge a goal.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from aios.domain.local_workforce.goal_jobs import (
    BRIEFING_SCHEMA,
    TRIAGE_SCHEMA,
    briefing_prompt,
    read_briefing,
    read_triage,
    triage_prompt,
)

#: The states a goal's intake can be in.
AWAITING_CLERK = "awaiting_clerk"
ESCALATED = "escalated"
BRIEFED = "briefed"
INTAKE_STATES = (AWAITING_CLERK, ESCALATED, BRIEFED)

#: How long one clerk job may take, and what its answer may spend.
CLERK_JOB_S = 180
CLERK_TOKENS = 400


def goal_text(task: Mapping[str, Any]) -> str:
    """The goal as the clerk reads it: the operator's words and his files."""
    files = [task["rel"], *task.get("also", [])]
    return f"{str(task['text']).strip()} (files: {', '.join(files)})"


def _request(job_id: str, profile: Any, payload: str, schema: Mapping[str, str]):
    from aios.domain.local_workforce.contracts import LocalJobRequest

    return LocalJobRequest(
        job_id=job_id,
        job_profile=profile,
        input_schema_version="1.0",
        # The job id names the goal; the payload carries no other reference.
        evidence_references=frozenset(),
        redacted_payload=payload,
        token_budget=CLERK_TOKENS,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=CLERK_JOB_S),
        required_output_schema=dict(schema),
    )


def _ask(
    service: Any,
    job_id: str,
    profile: Any,
    prompt: str,
    schema: Mapping[str, str],
    read: Callable[[Mapping[str, Any]], tuple[bool, str]],
) -> tuple[dict | None, str, str]:
    """One clerk job: ``(answer, model, why-not)``; the answer is None when the
    clerk did not complete it with an answer the job's reader accepts."""
    result = service.run_advisory_job(_request(job_id, profile, prompt, schema))
    if result.status != "completed" or not result.schema_valid:
        why = result.failure_reason or f"the clerk's job ended {result.status}"
        return None, result.model_id, why
    answer = dict(result.structured_output or {})
    ok, why = read(answer)
    if not ok:
        return None, result.model_id, f"the clerk's answer is not valid: {why}"
    return answer, result.model_id, ""


def mission_request(
    task: Mapping[str, Any], briefing: Mapping[str, Any], project_root: str
) -> dict:
    """The Queen Council's own request type, filled from the clerk's briefing
    (phase 2 hands it to the council's planner). Its scope is the operator's
    files, never the clerk's: a file the clerk names that he did not is not in
    it. Risk stays the request's default; the operator's daily envelope
    (phase 3) decides what may run."""
    from aios.council.queens.planner import CouncilMissionRequest

    named = [task["rel"], *task.get("also", [])]
    request = CouncilMissionRequest(
        mission_id=f"goal-{task['task_id']}",
        goal=str(briefing["goal"]).strip(),
        workspace_root=project_root,
        allowed_files=named,
        created_by="gagos_clerk",
    )
    out = dataclasses.asdict(request)
    out["workspace_root"] = str(out["workspace_root"])
    out["done_when"] = str(briefing["done_when"]).strip()
    out["constraints"] = [str(c).strip() for c in briefing["constraints"]]
    return out


def intake(
    task: Mapping[str, Any],
    service: Any,
    *,
    project_root: str,
    redact: Callable[[str], str] = lambda text: text,
    attempt: str | None = None,
) -> dict:
    """The clerk's intake of one goal: ``{"state", "clerk", "reason",
    "mission_request"}``. *service* is the clerk's governed service
    (``LocalWorkforceService.run_advisory_job``).

    Each intake is its own attempt (*attempt*, a UTC stamp by default): a goal
    waiting for the clerk is asked again in a later hour, and the clerk's
    provenance store keys every job by its id (2026-11-12: the second hour's
    ask of a waiting goal failed "UNIQUE constraint failed:
    local_job_requests.job_id"). Each step's job id is in the outcome, so the
    ledger points at the clerk's own record of it."""
    from aios.domain.local_workforce.contracts import LocalJobProfile

    tid = task["task_id"]
    attempt = attempt or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    triage_id = f"goal-{tid}-{attempt}-triage"
    briefing_id = f"goal-{tid}-{attempt}-briefing"
    goal = redact(goal_text(task))
    clerk: dict[str, Any] = {}

    def waiting(step: str, job_id: str, model: str, why: str) -> dict:
        clerk[step] = {"job_id": job_id, "model": model, "error": why}
        return {
            "state": AWAITING_CLERK,
            "clerk": clerk,
            "reason": f"{step}: {why}",
            "mission_request": None,
        }

    triage, model, why = _ask(
        service,
        triage_id,
        LocalJobProfile.TRIAGE,
        triage_prompt(goal),
        TRIAGE_SCHEMA,
        read_triage,
    )
    if triage is None:
        return waiting("triage", triage_id, model, why)
    clerk["triage"] = {"job_id": triage_id, "model": model, **triage}

    briefing, model, why = _ask(
        service,
        briefing_id,
        LocalJobProfile.PREPARE_BRIEFING,
        briefing_prompt(goal),
        BRIEFING_SCHEMA,
        read_briefing,
    )
    if briefing is None:
        return waiting("briefing", briefing_id, model, why)
    clerk["briefing"] = {"job_id": briefing_id, "model": model, **briefing}
    request = mission_request(task, briefing, project_root)
    if triage["escalate"]:
        return {
            "state": ESCALATED,
            "clerk": clerk,
            "reason": (
                f"the clerk's triage escalates it ({triage['severity']}, "
                f"{triage['area']})"
            ),
            "mission_request": request,
        }
    return {"state": BRIEFED, "clerk": clerk, "reason": "", "mission_request": request}


def writer_briefing(seen: Mapping[str, Any] | None) -> str:
    """What a writer reads of the clerk's intake, beside the operator's words:
    the briefing's constraints and what decides "done", and the triage when it
    escalates. Empty when the clerk has not briefed the goal."""
    if not seen or seen.get("state") not in (BRIEFED, ESCALATED):
        return ""
    clerk = seen.get("clerk") or {}
    briefing = clerk.get("briefing") or {}
    parts = []
    constraints = [
        str(c).strip() for c in briefing.get("constraints") or [] if str(c).strip()
    ]
    if constraints:
        parts.append("Constraints: " + "; ".join(constraints) + ".")
    done = str(briefing.get("done_when") or "").strip()
    if done:
        parts.append(f"Done when: {done}")
    if seen.get("state") == ESCALATED:
        triage = clerk.get("triage") or {}
        parts.append(
            f"The clerk's triage escalates it ({triage.get('severity')}, "
            f"{triage.get('area')}): change only what the task needs."
        )
    return " ".join(parts)


def pending(
    tasks: Sequence[Mapping[str, Any]], intakes: Mapping[str, Mapping[str, Any]]
) -> list:
    """Open tasks the clerk has not briefed yet (new, or still waiting for it)."""
    return [
        t
        for t in tasks
        if t["task_id"] not in intakes
        or intakes[t["task_id"]]["state"] == AWAITING_CLERK
    ]


__all__ = [
    "AWAITING_CLERK",
    "BRIEFED",
    "ESCALATED",
    "INTAKE_STATES",
    "goal_text",
    "intake",
    "mission_request",
    "pending",
    "writer_briefing",
]
