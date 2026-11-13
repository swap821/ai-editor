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
    # Each mission works in a folder of its own under GAGOS's workspace: the
    # copy its run stages, and promotes into, holds exactly its files.
    mission_root = Path(workspace_root) / mission_id
    mission_root.mkdir(parents=True, exist_ok=False)
    request = CouncilMissionRequest(
        mission_id=mission_id,
        goal=goal,
        workspace_root=str(mission_root),
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


def execute(
    mission_id: str,
    *,
    runtime_root: Path,
    bus: Any | None = None,
    spawner: Any | None = None,
    workspace_manager: Any | None = None,
) -> Any:
    """The council's execution of an approved mission, exactly as every
    originator gets it: the deliberated ledger gives the contract and the
    verdicts, the worker acts, the Testing queen grades it, and the change is
    promoted or the mission fails. Returns the :class:`CouncilRun`.

    *spawner* and *workspace_manager* are GAGOS's (:func:`run_gagos_mission`):
    its writer as the worker, and a stage of its own mission folder. The
    operator's route passes neither, and runs as before."""
    import asyncio

    from aios import config
    from aios.api.deps import get_council_memory_scope, get_emergency_stop
    from aios.council import CouncilOrchestrator
    from aios.council.gateway_reasoning import (
        build_council_llm_client,
        build_dissent_llm_client,
    )
    from aios.council.queen_verdict import has_blocking_verdict
    from aios.council.queens.planner import PlannerQueen
    from aios.infrastructure.intelligence.deliberation_store import (
        DeliberationStore,
    )
    from aios.infrastructure.missions.transition_journal_store import (
        MissionTransitionJournal,
    )
    from aios.runtime.run_ledger import RunLedgerStore

    ledger = RunLedgerStore(runtime_root).read(mission_id)
    # Defense in depth: never execute a ledger that carries a blocking verdict
    # (guards against an on-disk ledger tampered between deliberate and approve).
    if has_blocking_verdict(list(ledger.council_verdicts)):
        raise RuntimeError("ledger carries a blocking verdict; refusing to execute")
    council_state, council_memory, memory_authority = get_council_memory_scope(
        runtime_root
    )
    emergency_stop = get_emergency_stop()
    council_llm = build_council_llm_client(emergency_stop=emergency_stop)
    planner = PlannerQueen(llm=council_llm) if council_llm is not None else None
    # Organ 39: a genuinely independent second reviewer, real cloud provider
    # only (never Ollama -- that's always the King's own provider). None when
    # no cloud provider is configured or no operator is enrolled; deliberation
    # then simply never fires, matching king_complete's "None -> off".
    dissent = build_dissent_llm_client(emergency_stop=emergency_stop)
    staged: dict[str, Any] = {}
    if workspace_manager is not None:
        from aios.application.evidence import EvidenceAuthority, VerificationAuthority
        from aios.application.promotion.authority import PromotionAuthority
        from aios.application.promotion.runtime import WorkspacePromotionRuntime

        evidence = EvidenceAuthority()
        verification = VerificationAuthority(evidence)
        staged = {
            "workspace_manager": workspace_manager,
            "evidence_authority": evidence,
            "verification_authority": verification,
            "promotion_authority": PromotionAuthority(
                workspace_manager,
                verification=verification,
                emergency_stop=emergency_stop,
            ),
            "promotion_runtime": WorkspacePromotionRuntime(
                workspace_manager, runtime_root
            ),
        }
    orchestrator = CouncilOrchestrator(
        runtime_root=runtime_root,
        spawner=spawner,
        council_state=council_state,
        council_memory=council_memory,
        memory_authority=memory_authority,
        bus=bus,
        emergency_stop=emergency_stop,
        planner=planner,
        king_complete=council_llm.complete if council_llm is not None else None,
        dissent_complete=dissent[0].complete if dissent is not None else None,
        dissent_provider=dissent[1] if dissent is not None else "",
        dissent_exact_model_id=dissent[2] if dissent is not None else "",
        deliberation_store=DeliberationStore(config.DELIBERATION_DB_PATH),
        mission_journal=MissionTransitionJournal(
            config.MISSION_TRANSITION_JOURNAL_DB_PATH
        ),
        **staged,
    )
    return asyncio.run(
        orchestrator.execute(ledger.contract, list(ledger.council_verdicts))
    )


def prepare_workspace(
    mission_root: Path, *, repo_root: Path, base_commit: str, files: list[str]
) -> list[str]:
    """Fill a GAGOS mission's folder with its files as they are at
    *base_commit* in *repo_root*: the copy its run stages, the writer reads and
    promotion writes back to. A file the base does not have (a first test) is
    left for the writer to create. Returns the files copied. The folder must
    be empty: a mission runs once."""
    from git import Repo  # GitPython: the blob's bytes, exactly

    from aios.domain.capabilities.envelope import normalise_path

    mission_root = Path(mission_root)
    if any(mission_root.iterdir()):
        raise RuntimeError(f"the mission's folder is not empty: {mission_root}")
    copied = []
    repo = Repo(repo_root)
    try:
        tree = repo.commit(base_commit).tree
        for raw in files:
            rel = normalise_path(raw)
            try:
                blob = tree / rel
            except KeyError:
                continue
            target = mission_root.joinpath(*rel.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob.data_stream.read())
            copied.append(rel)
    finally:
        repo.close()
    return copied


def run_gagos_mission(
    mission_id: str,
    *,
    envelope: Any,
    runtime_root: Path,
    repo_root: Path,
    base_commit: str,
    write: Callable[..., Any],
    verify: Callable[..., Any],
    review: Callable[..., Any] | None = None,
    execute_with: Callable[..., Any] = execute,
    bus: Any | None = None,
) -> dict[str, Any]:
    """Run one GAGOS mission the council deliberated (move A3, 2026-11-13).

    The mission is approved by the slot it holds in the operator's envelope
    (organ 10, :meth:`MissionAuthority.approve_within_envelope`); its folder is
    filled with its files at *base_commit*; and the council executes it with
    GAGOS's writer as the worker (:class:`aios.runtime.gagos_writer
    .GagosWriterBackend`) in a stage of that folder. Promotion writes the
    verified change back into the folder, GAGOS's own, never a checkout.

    Returns ``{"state", "reason", "files"}``: state ``refused`` (the envelope
    no longer approves it; nothing ran), ``failed`` or ``completed``; files
    are the promoted texts, for delivery as a pull request."""
    from aios import config
    from aios.api.deps import get_emergency_stop
    from aios.application.capabilities.envelope import EnvelopeRefused
    from aios.application.missions.mission_service import MissionAuthority
    from aios.application.workspaces.staged import StagedWorkspaceManager
    from aios.domain.missions.mission_state import MissionState
    from aios.infrastructure.missions.sqlite_mission_repository import (
        MISSIONS_DB_NAME,
        SqliteMissionRepository,
    )
    from aios.infrastructure.missions.transition_journal_store import (
        MissionTransitionJournal,
    )
    from aios.runtime.gagos_writer import GagosWriterBackend
    from aios.runtime.spawner import WorkerSpawner

    def refused(reason: str) -> dict[str, Any]:
        return {"state": "refused", "reason": reason, "files": {}}

    missions = MissionAuthority(
        SqliteMissionRepository(Path(runtime_root) / MISSIONS_DB_NAME),
        export_dir=Path(runtime_root) / "mission_exports",
        emergency_stop=get_emergency_stop(),
    )
    record = missions.repository.get(mission_id)
    if record.contract.created_by != GAGOS_ORIGINATOR:
        return refused("not a mission GAGOS originated")
    if record.state is MissionState.AWAITING_APPROVAL:
        try:
            missions.approve_within_envelope(mission_id, envelope=envelope)
        except EnvelopeRefused as exc:
            return refused(f"not approved: {exc}")
        # Organ 42: the operator's route journals his approval at its HTTP
        # layer; the envelope's is journaled here, the same transition.
        MissionTransitionJournal(config.MISSION_TRANSITION_JOURNAL_DB_PATH).append(
            mission_id, "APPROVED"
        )
    elif record.state is not MissionState.APPROVED:
        return refused(f"the mission is {record.state.value}, not awaiting approval")
    mission_root = Path(record.contract.workspace_root)
    prepare_workspace(
        mission_root,
        repo_root=repo_root,
        base_commit=base_commit,
        files=list(record.contract.allowed_files),
    )
    backend = GagosWriterBackend(write=write, verify=verify, review=review)
    run = execute_with(
        mission_id,
        runtime_root=runtime_root,
        bus=bus,
        spawner=WorkerSpawner(runtime_root=runtime_root, backend=backend, bus=bus),
        workspace_manager=StagedWorkspaceManager(
            config.EXECUTOR_WORKSPACE_ROOT,
            enrolled_roots=(config.COUNCIL_WORKSPACE_ROOT,),
        ),
    )
    worker = getattr(getattr(run, "worker_run", None), "result", None)
    final = missions.repository.get(mission_id)
    if final.state is not MissionState.COMPLETED:
        why = (
            getattr(worker, "summary", "")
            if getattr(worker, "status", "") != "completed"
            else getattr(getattr(run, "report", None), "human_summary", "")
        )
        return {
            "state": "failed",
            "reason": str(why or f"the mission ended {final.state.value}")[:600],
            "files": {},
        }
    promoted = {
        rel: (mission_root / rel).read_bytes().decode("utf-8")
        for rel in (getattr(worker, "files_touched", None) or [])
    }
    return {"state": "completed", "reason": "", "files": promoted}


def gagos_workspace(root: Path) -> Path:
    """GAGOS's folder under the council workspace root *root*."""
    path = Path(root) / GAGOS_WORKSPACE
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = [
    "GAGOS_ORIGINATOR",
    "GAGOS_WORKSPACE",
    "deliberate",
    "execute",
    "gagos_workspace",
    "mission_kind",
    "originate_goal",
    "prepare_workspace",
    "run_gagos_mission",
]
