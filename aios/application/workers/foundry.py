"""The one Worker Foundry for temporary execution strategies."""
from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aios.application.workers.scheduler import WorkerScheduler
from aios.application.workers.strategies.legacy import (
    CodeWorkerStrategy,
    DeterministicWorkerStrategy,
    InspectionWorkerStrategy,
    ResearchWorkerStrategy,
    RolePassWorkerStrategy,
    StrategyUnavailable,
    SwarmWorkerStrategy,
    TestWorkerStrategy,
    ToolLoopWorkerStrategy,
)
from aios.domain.workers.worker_contract import (
    WorkerLifecycle,
    WorkerPrincipal,
    WorkerSpec,
    WorkerState,
    WorkerStrategyName,
    contract_digest,
)
from aios.core.events import CanonicalEvent, CanonicalEventType, EventPhase, TrustLevel
from aios.runtime.cortex_bus import CortexBus


class UnknownWorkerStrategy(KeyError):
    """Raised instead of silently choosing a different execution strategy."""


class WorkerStrategy(Protocol):
    name: WorkerStrategyName

    async def run(self, request: "WorkerExecutionRequest") -> Any:
        ...


@dataclass(frozen=True)
class WorkerExecutionRequest:
    spec: WorkerSpec
    contract: Any
    principal: WorkerPrincipal
    context: dict[str, Any] = field(default_factory=dict)


class WorkerFoundry:
    """Admit, schedule and dissolve temporary workers through one boundary."""

    def __init__(
        self,
        *,
        runtime_root: str | Path | None = None,
        spawner: Any | None = None,
        scheduler: WorkerScheduler | None = None,
        strategies: dict[str, WorkerStrategy] | None = None,
        bus: CortexBus | None = None,
        lifecycle_observer: Any | None = None,
        emergency_stop: Any | None = None,
        max_active: int = 4,
        max_per_mission: int = 1,
    ) -> None:
        self.runtime_root = Path(runtime_root).resolve() if runtime_root else None
        self.scheduler = scheduler or WorkerScheduler(
            max_active=max_active,
            max_per_mission=max_per_mission,
        )
        deterministic = DeterministicWorkerStrategy(spawner)
        defaults: dict[str, WorkerStrategy] = {
            strategy.name.value: strategy
            for strategy in (
                deterministic,
                ToolLoopWorkerStrategy(),
                RolePassWorkerStrategy(),
                SwarmWorkerStrategy(),
                ResearchWorkerStrategy(),
                CodeWorkerStrategy(),
                TestWorkerStrategy(),
                InspectionWorkerStrategy(),
            )
        }
        if strategies:
            defaults.update(strategies)
        self._strategies = defaults
        self._lifecycles: dict[str, WorkerLifecycle] = {}
        self._principals: dict[str, WorkerPrincipal] = {}
        self._bus = bus
        self._lifecycle_observer = lifecycle_observer
        self._emergency_stop = emergency_stop

    @property
    def strategies(self) -> tuple[str, ...]:
        return tuple(sorted(self._strategies))

    def select(self, strategy: str | WorkerStrategyName | None, contract: Any) -> WorkerStrategy:
        raw = strategy or _contract_strategy(contract)
        key = (raw.value if isinstance(raw, WorkerStrategyName) else str(raw)).strip().lower().replace("-", "_")
        aliases = {
            # Existing Council Runtime names are explicit strategy aliases,
            # not a permissive unknown-strategy fallback.
            "hybrid_plan_worker": "deterministic",
            "deterministic_worker": "deterministic",
            "tool_agent": "tool_loop",
            "tool_loop_worker": "tool_loop",
            "role_pass_worker": "role_pass",
            "swarm_worker": "swarm",
        }
        key = aliases.get(key, key)
        selected = self._strategies.get(key)
        if selected is None:
            raise UnknownWorkerStrategy(key)
        return selected

    def lifecycle(self, worker_id: str) -> WorkerLifecycle | None:
        return self._lifecycles.get(worker_id)

    def principal(self, worker_id: str) -> WorkerPrincipal | None:
        return self._principals.get(worker_id)

    async def run(
        self,
        contract: Any,
        *,
        strategy: str | WorkerStrategyName | None = None,
        caste: str | None = None,
        parent_principal_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        if self._emergency_stop is not None:
            self._emergency_stop.assert_operational()
        selected = self.select(strategy, contract)
        worker_id = f"worker-{uuid.uuid4().hex[:12]}"
        mission_id = str(getattr(contract, "mission_id"))
        digest = contract_digest(contract)
        metadata = dict(context or {})
        if self.runtime_root is not None:
            metadata.setdefault("runtime_root", str(self.runtime_root))
        spec = WorkerSpec(
            worker_id=worker_id,
            mission_id=mission_id,
            contract_digest=digest,
            strategy=selected.name,
            caste=caste,
            priority=int(metadata.get("priority", getattr(contract, "priority", 0))),
            max_steps=int(getattr(contract, "max_steps", 1)),
            timeout_seconds=int(getattr(contract, "timeout_seconds", 1)),
            metadata={"strategy": selected.name.value},
        )
        principal = WorkerPrincipal(
            principal_id=f"principal:worker:{worker_id}",
            worker_id=worker_id,
            mission_id=mission_id,
            contract_digest=digest,
            parent_principal_id=parent_principal_id,
            metadata={"strategy": selected.name.value, "caste": caste},
        )
        self._principals[worker_id] = principal
        self._set_state(spec, WorkerState.REQUESTED, "foundry request")
        self._set_state(spec, WorkerState.ADMITTED, "scheduler admission")
        request = WorkerExecutionRequest(spec, contract, principal, metadata)

        async def execute() -> Any:
            self._set_state(spec, WorkerState.BORN, "strategy admitted")
            self._set_state(spec, WorkerState.RUNNING, "strategy running")
            try:
                result = selected.run(request)
                if inspect.isawaitable(result):
                    result = await result
            except asyncio.CancelledError:
                self._set_state(spec, WorkerState.KILLED, "scheduler cancellation")
                raise
            except Exception as exc:
                self._set_state(spec, WorkerState.FAILED, str(exc))
                raise
            else:
                self._set_state(spec, _result_state(result), "strategy completed")
                return result
            finally:
                self._set_state(spec, WorkerState.DISSOLVED, "worker resources released")

        return await self.scheduler.submit(spec, execute)

    def _set_state(self, spec: WorkerSpec, state: WorkerState, reason: str) -> None:
        lifecycle = WorkerLifecycle(
            worker_id=spec.worker_id,
            mission_id=spec.mission_id,
            state=state,
            strategy=spec.strategy,
            reason=reason,
        )
        self._lifecycles[spec.worker_id] = lifecycle
        if self._lifecycle_observer is not None:
            self._lifecycle_observer(lifecycle)
        if self._bus is not None:
            canonical = CanonicalEvent(
                event_type=CanonicalEventType.TOOL_LIFECYCLE_CHANGED.value,
                phase=EventPhase.REFLEX.value,
                status=state.value,
                trust=TrustLevel.VERIFIED.value,
                source="worker_foundry",
                session_id=spec.mission_id,
                mission_id=spec.mission_id,
                worker_id=spec.worker_id,
                payload={
                    "state": state.value,
                    "strategy": spec.strategy.value,
                    "contract_digest": spec.contract_digest,
                    "reason": reason,
                },
            )
            self._bus.append(
                canonical.event_type,
                spec.worker_id,
                canonical.to_dict(),
            )


def _contract_strategy(contract: Any) -> str:
    metadata = getattr(contract, "metadata", {}) or {}
    return str(
        metadata.get("worker_strategy")
        or metadata.get("strategy")
        or getattr(contract, "worker_type", "deterministic")
    )


def _result_state(result: Any) -> WorkerState:
    status = str(getattr(result, "status", result) if result is not None else "completed")
    if status in {"awaiting_capability", "awaiting_approval"}:
        return WorkerState.AWAITING_CAPABILITY
    if status in {"failed", "timeout", "killed", "contract_violation"}:
        return WorkerState.FAILED
    return WorkerState.COMPLETED


__all__ = [
    "StrategyUnavailable",
    "UnknownWorkerStrategy",
    "WorkerExecutionRequest",
    "WorkerFoundry",
    "WorkerStrategy",
]
