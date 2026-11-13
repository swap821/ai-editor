"""GAGOS's writer as a council worker backend (2026-11-13).

Move A3 on the aliveness map. A GAGOS mission the council deliberated and the
operator's envelope approved runs through the council's own execution: the
Worker Foundry stages the mission's workspace (organ 14), the spawner seals it
with a snapshot and records the run ledger, the Testing queen grades the
ledger, and promotion (organs 15, 16 and 41) applies the staged change to
GAGOS's own mission workspace, never the operator's checkout. This backend is
the worker inside that path: the workshop's own writer, which writes into the
stage and nowhere else.

What it adds to the council's worker is only the writer and the workshop's
checks, each injected by the caller:

* ``write(contract)`` returns the writer's new text for each file it changed
  (``{rel: text}``), or raises :class:`WriterRefused` with the reason;
* every file is written into the stage only when it is one of the mission's
  own files, a plain repo-relative path, and no part of its way down the stage
  is a link or a Windows reparse point (a junction would carry the write out
  of the stage): :func:`write_into_stage`;
* ``verify(edits)`` is the workshop's sandbox over the change, recorded as the
  runner's own command, its real counts and its exit code
  (:func:`aios.maintenance.sandbox_tests.ledger_entry`);
* ``review(edits, verdict)``, only for a change whose tests pass, is the
  reviewer judging the change against the operator's words.

The worker is ``completed`` only when its change is written, its tests pass
and the reviewer accepts it; anything else is ``failed`` with its reason, and
the council never promotes a worker that did not complete.
"""

from __future__ import annotations

import os
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from aios.runtime.backends import WorkerBackend, WorkerHandle
from aios.runtime.contracts import MissionContract, WorkerResult

#: What the backend is called in a handle and in the run ledger.
BACKEND_NAME = "gagos_writer"


class WriterRefused(RuntimeError):
    """The writer gave no change that may be written; the reason says why."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_link(path: Path) -> bool:
    """True for a symbolic link, a junction, or any other reparse point."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _allowed(contract: MissionContract) -> dict[str, str]:
    """The mission's own files, normalised, by their case-folded spelling (a
    Windows file system does not tell ``A.ts`` from ``a.ts``)."""
    from aios.domain.capabilities.envelope import normalise_path

    return {
        normalise_path(f).casefold(): normalise_path(f) for f in contract.allowed_files
    }


def write_into_stage(
    stage: Path, contract: MissionContract, edits: Mapping[str, str]
) -> dict[str, str]:
    """Write *edits* into *stage*, all or nothing as to their paths: every path
    is checked before the first byte is written. Returns what was written, by
    each file's own spelling in the mission."""
    from aios.domain.capabilities.envelope import (
        EnvelopeError,
        forbidden,
        normalise_path,
    )

    stage = Path(stage)
    if _is_link(stage):
        raise WriterRefused("the stage itself is a link")
    root = stage.resolve()
    allowed = _allowed(contract)
    plan: list[tuple[str, Path, str]] = []
    for raw, text in edits.items():
        try:
            rel = normalise_path(raw)
        except EnvelopeError as exc:
            raise WriterRefused(str(exc)) from exc
        if forbidden(rel):
            raise WriterRefused(f"{rel} is never GAGOS's to write")
        if rel.casefold() not in allowed:
            raise WriterRefused(f"{rel} is not one of the mission's files")
        rel = allowed[rel.casefold()]
        target = root.joinpath(*rel.split("/"))
        walked = root
        for part in rel.split("/"):
            walked = walked / part
            if _is_link(walked):
                raise WriterRefused(f"{rel}: {walked.relative_to(root)} is a link")
        if target.exists() and not target.is_file():
            raise WriterRefused(f"{rel} exists and is not a file")
        plan.append((rel, target, text))
    written: dict[str, str] = {}
    for rel, target, text in plan:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Checked again after the folders exist: nothing may have put a link
        # on the way between the check and the write.
        walked = root
        for part in rel.split("/"):
            walked = walked / part
            if _is_link(walked):
                raise WriterRefused(f"{rel}: {walked.relative_to(root)} is a link")
        try:
            target.resolve().relative_to(root)
        except ValueError as exc:
            raise WriterRefused(f"{rel} resolves outside the stage") from exc
        target.write_bytes(text.encode("utf-8"))
        written[rel] = text
    return written


class GagosWriterBackend(WorkerBackend):
    """The council worker that is GAGOS's writer, writing only into its stage."""

    backend_name = BACKEND_NAME

    def __init__(
        self,
        *,
        write: Callable[[MissionContract], Mapping[str, str]],
        verify: Callable[[Mapping[str, str]], Any],
        review: Callable[[Mapping[str, str], Any], tuple[bool, str]] | None = None,
    ) -> None:
        self.write = write
        self.verify = verify
        self.review = review
        self._contracts: dict[str, MissionContract] = {}

    async def spawn(self, contract: MissionContract) -> WorkerHandle:
        worker_id = f"worker-{uuid.uuid4().hex[:12]}"
        self._contracts[worker_id] = contract
        return WorkerHandle(
            worker_id=worker_id,
            mission_id=contract.mission_id,
            backend=self.backend_name,
            status="running",
        )

    async def reap(self, handle: WorkerHandle) -> WorkerResult:
        contract = self._contracts.pop(handle.worker_id)
        started_at = _utc_now()
        evidence: dict[str, Any] = {}
        files: list[str] = []
        try:
            stage = _stage_of(contract)
            edits = dict(self.write(contract))
            if not edits:
                raise WriterRefused("the writer changed no file")
            edits = write_into_stage(stage, contract, edits)
            files = list(edits)
            from aios.maintenance.sandbox_tests import PASSED, ledger_entry

            verdict = self.verify(edits)
            evidence["verification"] = [ledger_entry(verdict, rels=files)]
            evidence["sandbox"] = {
                "outcome": verdict.outcome,
                "summary": verdict.summary,
            }
            if verdict.outcome != PASSED:
                status, summary = (
                    "failed",
                    f"the sandbox: {verdict.outcome}: {verdict.summary}",
                )
            elif self.review is None:
                status, summary = "completed", f"the sandbox: {verdict.summary}"
            else:
                accepted, reason = self.review(edits, verdict)
                evidence["review"] = {"accepted": bool(accepted), "reason": reason}
                status = "completed" if accepted else "failed"
                summary = (
                    f"the sandbox: {verdict.summary}; the reviewer accepts: {reason}"
                    if accepted
                    else f"the reviewer rejects: {reason}"
                )
        except WriterRefused as exc:
            status, summary = "failed", f"the writer: {exc}"
        except Exception as exc:  # noqa: BLE001 - a worker's failure is its result, never the council's crash
            status, summary = "failed", f"{type(exc).__name__}: {exc}"
        handle.status = "dead"
        return WorkerResult(
            mission_id=contract.mission_id,
            worker_id=handle.worker_id,
            status=status,
            summary=summary[:2000],
            files_touched=files,
            evidence=evidence,
            risk_after=contract.risk_level,
            started_at=started_at,
            ended_at=_utc_now(),
        )

    async def kill(self, handle: WorkerHandle, reason: str) -> None:
        self._contracts.pop(handle.worker_id, None)
        handle.status = "killed"


def _stage_of(contract: MissionContract) -> Path:
    """The mission's stage, or :class:`WriterRefused`: GAGOS writes only into
    a workspace the Foundry staged for this mission, never into the project."""
    lease = (contract.metadata or {}).get("staged_workspace") or {}
    path = lease.get("workspace_path")
    if (
        not path
        or lease.get("mission_id") != contract.mission_id
        or Path(path).resolve() != Path(contract.workspace_root).resolve()
    ):
        raise WriterRefused("no stage of this mission to write into")
    return Path(path)


__all__ = [
    "BACKEND_NAME",
    "GagosWriterBackend",
    "WriterRefused",
    "write_into_stage",
]
