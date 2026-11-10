"""GAGOS's workshop writers, admitted by the Worker Foundry (2026-11-10).

The consistency plan of 2026-11-04 ("one engine for work, the Foundry") asked
for the workshop's writers to stop running on a thread pool of their own. Each
writer's call is now a worker the Foundry admits, as the swarm's legs are
(:mod:`aios.application.workers.swarm_foundry`): the operator's emergency stop
is checked at admission, the scheduler bounds how many write at once (the
workshop's ``WRITERS_AT_ONCE``), and every lifecycle transition -- requested,
admitted, started, completed or failed, dissolved -- lands on the cortex bus.
The bus is one SQLite outbox, so the workshop's process appends to the same
bus the backend's dispatcher reads, and the face can see GAGOS's writers.

What a writer does is unchanged: one governed call through the one gateway,
then the workshop's own unattended checks. Nothing a model wrote is executed
here; the sandbox, the review and the operator's merge stay their own steps.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from aios.application.workers.foundry import WorkerFoundry, WorkerExecutionRequest
from aios.domain.workers.worker_contract import WorkerStrategyName

#: How long one writer may run (its model call and its checks) before it fails
#: and frees its slot. The thread itself finishes on its own; the batch waits.
WRITER_LEG_TIMEOUT_S = 1800


@dataclass(frozen=True)
class WorkshopWriterContract:
    """What the Foundry admits for one writer of one batch."""

    mission_id: str
    writer: str
    files: tuple[str, ...]
    allowed_tools: tuple[str, ...] = ()
    max_steps: int = 1
    timeout_seconds: int = WRITER_LEG_TIMEOUT_S
    priority: int = 0
    scope: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def digest(self) -> str:
        return f"workshop-writer:{self.mission_id}:{self.writer}:{','.join(self.files)}"


class WorkshopWriterTimedOut(TimeoutError):
    """A writer ran past its contract's timeout; its slot is freed for others."""


class WorkshopWriterStrategy:
    """Runs one writer's call and checks in a worker thread, so writers run side
    by side within the scheduler's bound."""

    name = WorkerStrategyName.CODE

    async def run(self, request: WorkerExecutionRequest) -> Any:
        run = request.context["run"]
        timeout = max(1, int(request.spec.timeout_seconds))
        try:
            return await asyncio.wait_for(asyncio.to_thread(run), timeout)
        except asyncio.TimeoutError as exc:
            raise WorkshopWriterTimedOut(
                f"the writer {request.spec.caste or ''} ran past {timeout}s"
            ) from exc


@dataclass(frozen=True)
class WriterLeg:
    """One writer's work in a batch: who writes, which files, and the call."""

    writer: str
    files: tuple[str, ...]
    run: Callable[[], Any]


class WorkshopFoundry:
    """Admits each writer of a workshop batch as a Foundry worker."""

    def __init__(
        self, *, emergency_stop: Any, bus: Any | None = None, writers_at_once: int = 2
    ) -> None:
        bound = max(1, int(writers_at_once))
        self.foundry = WorkerFoundry(
            strategies={WorkerStrategyName.CODE.value: WorkshopWriterStrategy()},
            emergency_stop=emergency_stop,
            bus=bus,
            max_active=bound,
            max_per_mission=bound,
        )

    def run_batch(
        self,
        mission_id: str,
        legs: Sequence[WriterLeg],
        *,
        timeout_seconds: int = WRITER_LEG_TIMEOUT_S,
    ) -> list[BaseException | None]:
        """Run every leg as an admitted worker of *mission_id*. Returns, in the
        legs' order, None for a leg that finished and the exception for one that
        was refused (an engaged emergency stop) or failed: one leg's failure
        never stops the others."""

        async def batch() -> list[Any]:
            return await asyncio.gather(
                *(
                    self.foundry.run(
                        WorkshopWriterContract(
                            mission_id=mission_id,
                            writer=leg.writer,
                            files=tuple(leg.files),
                            timeout_seconds=max(1, int(timeout_seconds)),
                            scope={"files": list(leg.files)},
                            metadata={"worker_strategy": WorkerStrategyName.CODE.value},
                        ),
                        strategy=WorkerStrategyName.CODE,
                        caste=leg.writer,
                        context={"run": leg.run},
                    )
                    for leg in legs
                ),
                return_exceptions=True,
            )

        if not legs:
            return []
        outcomes = asyncio.run(batch())
        return [o if isinstance(o, BaseException) else None for o in outcomes]


__all__ = [
    "WRITER_LEG_TIMEOUT_S",
    "WorkshopFoundry",
    "WorkshopWriterContract",
    "WorkshopWriterStrategy",
    "WorkshopWriterTimedOut",
    "WriterLeg",
]
