"""The ant colony's workers, admitted by the Worker Foundry (2026-11-09).

The operator, 2026-11-04: "It has 4 models of workforce can be multiple workers
working that's y o made queens and ant-colony inspired workers are we honestly
using those". They were not: production refused the swarm outright ("route it
through WorkerFoundry before enabling", ``generate_pipeline``), because its
castes ran tool agents outside the one boundary every acting worker must cross.

Here each caste leg (scout, decomposer, cloud broker, worker, quorum,
synthesizer) is a worker the Foundry admits: the emergency stop is checked at
admission, the scheduler bounds how many run, and every lifecycle transition
(requested, admitted, started, completed or failed, dissolved) lands on the
cortex bus like any other worker's. What a leg does is unchanged: its tool
agent's every tool stays behind the executor gate and the operator's approvals.

The swarm's scheduler is its own (the colony's legs share one mission, which the
backend Foundry would run one at a time), on one long-lived event loop: the
turn stream is synchronous, and the scheduler's futures belong to the loop that
created them, so every leg is submitted to that one loop from whatever thread
runs it.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from aios import config
from aios.application.workers.foundry import WorkerFoundry, WorkerExecutionRequest
from aios.domain.workers.worker_contract import WorkerStrategyName

T = TypeVar("T")

#: How many swarm turns' worth of legs the process runs at once.
TURNS_AT_ONCE = 4
#: How long one leg may run before it fails and frees its slot.
LEG_TIMEOUT_S = 600


@dataclass(frozen=True)
class SwarmLegContract:
    """What the Foundry admits for one caste leg."""

    mission_id: str
    caste: str
    allowed_tools: tuple[str, ...] = ()
    max_steps: int = 1
    timeout_seconds: int = 600
    priority: int = 0
    scope: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def digest(self) -> str:
        return (
            f"swarm-leg:{self.mission_id}:{self.caste}:{','.join(self.allowed_tools)}"
        )


class SwarmLegTimedOut(TimeoutError):
    """A leg ran past its contract's timeout; its slot is freed for others."""


class SwarmLegStrategy:
    """Runs one leg's tool agent in a worker thread, so legs run side by side.

    A leg that runs past its contract's timeout fails, and its scheduler slot is
    released: the correctness review of 2026-11-09 held four hung legs and
    watched another turn's leg wait forever. The thread itself cannot be
    killed; it finishes or stops at its agent's own next check, as a single
    agent's would.
    """

    name = WorkerStrategyName.SWARM

    async def run(self, request: WorkerExecutionRequest) -> Any:
        run = request.context["run"]
        timeout = max(1, int(request.spec.timeout_seconds))
        try:
            return await asyncio.wait_for(asyncio.to_thread(run), timeout)
        except asyncio.TimeoutError as exc:
            raise SwarmLegTimedOut(
                f"the {request.spec.caste or 'swarm'} leg ran past {timeout}s"
            ) from exc


class SwarmFoundry:
    """Admits each caste leg of a swarm turn as a Foundry worker."""

    def __init__(
        self,
        *,
        emergency_stop: Any,
        bus: Any | None = None,
        max_workers: int = config.SWARM_MAX_WORKERS,
    ) -> None:
        bound = max(1, int(max_workers))
        self.foundry = WorkerFoundry(
            strategies={WorkerStrategyName.SWARM.value: SwarmLegStrategy()},
            emergency_stop=emergency_stop,
            bus=bus,
            # One turn is held to its own bound; the process to several turns'
            # worth, so one turn's stuck legs cannot take every slot.
            max_active=bound * TURNS_AT_ONCE,
            max_per_mission=bound,
        )
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="swarm-foundry", daemon=True
        )
        self._thread.start()

    def admit(
        self,
        mission_id: str,
        caste: str,
        run: Callable[[], T],
        *,
        allowed_tools: tuple[str, ...] = (),
        max_steps: int = 1,
        timeout_seconds: int = LEG_TIMEOUT_S,
    ) -> T:
        """Run *run* as one admitted worker of *mission_id*; its result, or the
        refusal (an emergency stop) as the exception it raised."""
        contract = SwarmLegContract(
            mission_id=mission_id,
            caste=caste,
            allowed_tools=tuple(sorted(allowed_tools)),
            max_steps=max(1, int(max_steps)),
            timeout_seconds=max(1, int(timeout_seconds)),
            metadata={"worker_strategy": WorkerStrategyName.SWARM.value},
        )
        future = asyncio.run_coroutine_threadsafe(
            self.foundry.run(
                contract,
                strategy=WorkerStrategyName.SWARM,
                caste=caste,
                context={"run": run},
            ),
            self._loop,
        )
        return future.result()

    def mission(self) -> str:
        """A fresh mission id for one swarm turn."""
        return f"swarm-{uuid.uuid4().hex[:12]}"

    def close(self) -> None:
        """Stop the loop and its thread (the backend's singleton lives as long as
        the process; a test closes what it opens)."""
        if self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._loop.close()


__all__ = ["SwarmFoundry", "SwarmLegContract", "SwarmLegStrategy", "SwarmLegTimedOut"]
