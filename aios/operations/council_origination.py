"""Council origination: one deliberation for every originator (2026-11-12).

The operator originates a council mission at his route
(``POST /api/v1/council/missions``, a privileged operator). GAGOS originates
one for a goal the local clerk has briefed, but only inside the operator's
daily envelope (organ 9's envelope authority, which he signs once a day; his
choice, "Envelope via organs 9+10"). Both deliberate the same way, built once
here (:func:`deliberate`): the Queens deliberate, no worker spawns, and the
mission is recorded by the Mission Authority (organ 10) as awaiting approval,
or blocked.

GAGOS's origination (:func:`originate_goal`) adds nothing to what may run:

* it takes one slot of the live envelope first, so a goal outside the
  envelope's folders, kinds or count, or with no envelope signed, is refused
  with the envelope's own reason, and no council is convened;
* the goal is the operator's own words (the clerk's briefing rides along as
  advisory metadata, never as the goal), and passes the same injection check
  as his route;
* the mission is verified by the workshop's sandbox
  (``metadata.sandbox_verification``, :mod:`aios.council.sandbox_spec`), its
  scope is exactly his files, and it carries the slot it holds;
* nothing here approves or runs a mission: approval within the envelope and
  the run are the next steps, each checked against the slot again.

A slot is spent by the origination itself: a mission the council blocks, or
whose deliberation fails, has used one of the day's missions. The envelope
counts attempts, so a goal the council keeps refusing cannot be retried past
the operator's number.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

#: Who GAGOS originates as: never the operator who signed the envelope.
GAGOS_ORIGINATOR = "gagos"
#: The folder under the council workspace root GAGOS's missions use.
GAGOS_WORKSPACE = "gagos"


def deliberate(request: Any, *, runtime_root: Path, bus: Any | None = None) -> Any:
    """The council's deliberation, exactly as every originator gets it: the
    Queens deliberate, no worker spawns, the King reports awaiting approval or
    blocked. Returns the :class:`CouncilRun`."""
    # Providers and stores come from the dependency module, the one place
    # allowed to construct them (tests/architecture/test_intelligence_boundary).
    from aios import config
    from aios.api.deps import get_council_memory_scope, get_emergency_stop
    from aios.council import CouncilOrchestrator
    from aios.council.gateway_reasoning import build_council_llm_client
    from aios.council.queens.planner import PlannerQueen
    from aios.infrastructure.missions.transition_journal_store import (
        MissionTransitionJournal,
    )

    council_state, council_memory, memory_authority = get_council_memory_scope(
        runtime_root
    )
    emergency_stop = get_emergency_stop()
    council_llm = build_council_llm_client(emergency_stop=emergency_stop)
    planner = PlannerQueen(llm=council_llm) if council_llm is not None else None
    return CouncilOrchestrator(
        runtime_root=runtime_root,
        council_state=council_state,
        council_memory=council_memory,
        memory_authority=memory_authority,
        bus=bus,
        emergency_stop=emergency_stop,
        planner=planner,
        king_complete=council_llm.complete if council_llm is not None else None,
        mission_journal=MissionTransitionJournal(
            config.MISSION_TRANSITION_JOURNAL_DB_PATH
        ),
    ).deliberate(request)


def mission_kind(files: list[str]) -> str:
    """The envelope kind a mission over *files* is: ``tests`` when every file
    is a test file, else ``code``."""
    from aios.domain.capabilities.envelope import is_test_file, normalise_path

    return "tests" if all(is_test_file(normalise_path(f)) for f in files) else "code"


def _refused(reason: str, **extra: Any) -> dict[str, Any]:
    return {"state": "refused", "reason": reason, "mission_id": None, **extra}


def originate_goal(
    task: Mapping[str, Any],
    seen: Mapping[str, Any],
    *,
    envelope: Any,
    workspace_root: Path,
    runtime_root: Path,
    deliberate_with: Callable[..., Any] = deliberate,
    detect_injection: Callable[[str], str | None] | None = None,
    constitution_digest: Callable[[], str | None] = lambda: None,
) -> dict[str, Any]:
    """GAGOS originates the council mission for one briefed goal, inside the
    operator's envelope: ``{"state", "reason", "mission_id", ...}`` where state
    is ``refused`` (outside the envelope, or the goal fails the injection
    check; no council convened), ``blocked`` (the council denied or deferred
    it) or ``awaiting_approval``. *seen* is the clerk's intake of the goal.

    *envelope* is organ 9's :class:`EnvelopeAuthority`; *workspace_root* the
    council workspace GAGOS's missions use."""
    from aios.council import CouncilMissionRequest
    from aios.council.sandbox_spec import SANDBOX_KEY
    from aios.application.capabilities.envelope import EnvelopeRefused
    from aios.infrastructure.identity.sqlite_store import credential_digest

    if detect_injection is None:
        from aios.core.injection_scan import detect_injection as _detect

        detect_injection = _detect
    if (seen or {}).get("state") != "briefed":
        return _refused("only a goal the clerk briefed, not escalated, originates")
    files = [str(task["rel"]), *[str(f) for f in task.get("also", [])]]
    goal = str(task["text"]).strip()
    why = detect_injection(goal)
    if why:
        return _refused(f"the goal fails the injection check: {why}")
    mission_id = f"mission-{uuid.uuid4().hex[:12]}"
    try:
        slot = envelope.admit(
            mission_id=mission_id,
            files=files,
            kind=mission_kind(files),
            originator=GAGOS_ORIGINATOR,
        )
    except EnvelopeRefused as exc:
        return _refused(f"outside the operator's envelope: {exc}")
    signer = envelope.live()
    if signer is None:
        return _refused("the envelope ended while the slot was taken")
    briefing = ((seen or {}).get("clerk") or {}).get("briefing") or {}
    request = CouncilMissionRequest(
        mission_id=mission_id,
        goal=goal,
        workspace_root=str(workspace_root),
        allowed_files=files,
        allowed_tools=["read_file", "write_file"],
        created_by=GAGOS_ORIGINATOR,
        operator_id=signer.operator_id,
        operator_identity_digest=credential_digest(signer.operator_id),
        constitution_digest=constitution_digest(),
        requires_governed_intelligence=True,
        metadata={
            SANDBOX_KEY: {"files": files},
            "gagos_goal": str(task["task_id"]),
            "envelope": {
                "envelope_id": slot.envelope_id,
                "slot": slot.slot,
                "of": slot.of,
                "slot_digest": slot.slot_digest,
            },
            # Advisory: the operator's words above decide.
            "clerk_briefing": {
                "constraints": list(briefing.get("constraints") or []),
                "done_when": str(briefing.get("done_when") or ""),
            },
        },
    )
    try:
        run = deliberate_with(request, runtime_root=runtime_root)
    except Exception as exc:  # noqa: BLE001 - recorded with its slot, never raised into the hour
        return {
            "state": "failed",
            "reason": f"the council's deliberation failed: {type(exc).__name__}: {exc}"[
                :400
            ],
            "mission_id": mission_id,
            "envelope_id": slot.envelope_id,
            "slot": slot.slot,
        }
    report = getattr(run, "report", None)
    status = str(getattr(report, "status", "") or "")
    state = "awaiting_approval" if status == "awaiting_approval" else "blocked"
    return {
        "state": state,
        "reason": ""
        if state == "awaiting_approval"
        else str(
            getattr(report, "human_summary", "")
            or status
            or "the council did not pass it"
        ),
        "mission_id": mission_id,
        "envelope_id": slot.envelope_id,
        "slot": slot.slot,
    }


def gagos_workspace(root: Path) -> Path:
    """GAGOS's folder under the council workspace root *root*."""
    path = Path(root) / GAGOS_WORKSPACE
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = [
    "GAGOS_ORIGINATOR",
    "GAGOS_WORKSPACE",
    "deliberate",
    "gagos_workspace",
    "mission_kind",
    "originate_goal",
]
