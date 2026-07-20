"""The one Worker Foundry for temporary execution strategies."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aios.application.workers.scheduler import WorkerScheduler
from aios.application.workspaces import StagedWorkspaceManager
from aios.application.workspaces.staged import WorkspacePathViolation
from aios.application.workers.strategies.legacy import (
    DeterministicWorkerStrategy,
    StrategyUnavailable,
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

    async def run(self, request: "WorkerExecutionRequest") -> Any: ...


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
        workspace_manager: StagedWorkspaceManager | None = None,
        max_active: int = 4,
        max_per_mission: int = 1,
    ) -> None:
        self.runtime_root = Path(runtime_root).resolve() if runtime_root else None
        self.spawner = spawner
        self.scheduler = scheduler or WorkerScheduler(
            max_active=max_active,
            max_per_mission=max_per_mission,
            emergency_stop=emergency_stop,
        )
        deterministic = DeterministicWorkerStrategy(spawner)
        # Only deterministic execution has a default production handler.  The
        # other adapters remain available for explicit injection in tests or a
        # future governed runtime, but must not be advertised as callable
        # production strategies while they would raise StrategyUnavailable.
        defaults: dict[str, WorkerStrategy] = {
            deterministic.name.value: deterministic,
        }
        if strategies:
            defaults.update(strategies)
        self._strategies = defaults
        self._lifecycles: dict[str, WorkerLifecycle] = {}
        self._principals: dict[str, WorkerPrincipal] = {}
        self._bus = bus
        self._lifecycle_observer = lifecycle_observer
        self._emergency_stop = emergency_stop
        self.workspace_manager = workspace_manager

    @property
    def strategies(self) -> tuple[str, ...]:
        return tuple(sorted(self._strategies))

    def select(
        self, strategy: str | WorkerStrategyName | None, contract: Any
    ) -> WorkerStrategy:
        raw = strategy or _contract_strategy(contract)
        key = (
            (raw.value if isinstance(raw, WorkerStrategyName) else str(raw))
            .strip()
            .lower()
            .replace("-", "_")
        )
        aliases = {
            # Existing Council Runtime names are explicit strategy aliases,
            # not a permissive unknown-strategy fallback.
            "code": "deterministic",
            "hybrid_plan_worker": "deterministic",
            "deterministic_worker": "deterministic",
            "tool_agent": "tool_loop",
            "tool_loop_worker": "tool_loop",
            "role_pass_worker": "role_pass",
            "swarm_worker": "swarm",
        }
        selected = self._strategies.get(key)
        if selected is None:
            aliased_key = aliases.get(key, key)
            selected = self._strategies.get(aliased_key)
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
        contract = self._stage_contract(contract)
        worker_id = f"worker-{uuid.uuid4().hex[:12]}"
        mission_id = str(getattr(contract, "mission_id"))
        digest = contract_digest(contract)
        metadata = dict(getattr(contract, "metadata", {}) or {})
        metadata.update(context or {})
        if self.runtime_root is not None:
            metadata.setdefault("runtime_root", str(self.runtime_root))
        budgets = _contract_budgets(contract)
        spec = WorkerSpec(
            worker_id=worker_id,
            mission_id=mission_id,
            contract_digest=digest,
            strategy=selected.name,
            caste=caste,
            priority=int(metadata.get("priority", getattr(contract, "priority", 0))),
            max_steps=int(getattr(contract, "max_steps", budgets.get("max_steps", 1))),
            timeout_seconds=int(
                getattr(contract, "timeout_seconds", budgets.get("timeout_seconds", 1))
            ),
            allowed_tools=tuple(
                str(item) for item in (getattr(contract, "allowed_tools", ()) or ())
            ),
            scope=dict(getattr(contract, "scope", {}) or {}),
            budgets=budgets,
            data_classification=str(metadata.get("data_classification", "internal")),
            executor_policy=str(metadata.get("executor_policy", "default")),
            metadata={"strategy": selected.name.value},
        )
        principal = WorkerPrincipal(
            principal_id=f"principal:worker:{worker_id}",
            worker_id=worker_id,
            mission_id=mission_id,
            contract_digest=digest,
            parent_principal_id=parent_principal_id,
            metadata={
                "strategy": selected.name.value,
                "caste": caste,
                "allowed_tools": list(spec.allowed_tools),
                "scope": dict(spec.scope),
                "budgets": dict(spec.budgets),
                "data_classification": spec.data_classification,
                "executor_policy": spec.executor_policy,
            },
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
                self._set_state(
                    spec, WorkerState.DISSOLVED, "worker resources released"
                )

        return await self.scheduler.submit(spec, execute)

    def _stage_contract(self, contract: Any) -> Any:
        """Replace the enrolled project root with a mission-owned stage."""
        if self.workspace_manager is None:
            return contract
        project_root = getattr(contract, "workspace_root", None)
        if not project_root:
            raise WorkspacePathViolation(
                "worker contract must declare an enrolled workspace root"
            )
        lease = self.workspace_manager.stage(
            str(getattr(contract, "mission_id")), project_root
        )
        metadata = dict(getattr(contract, "metadata", {}) or {})
        metadata["project_root"] = lease.project_root
        metadata["staged_workspace"] = lease.model_dump(mode="json")
        scope = dict(getattr(contract, "scope", {}) or {})
        scope["workspace_root"] = lease.workspace_path
        return contract.model_copy(
            update={
                "workspace_root": lease.workspace_path,
                "scope": scope,
                "metadata": metadata,
            }
        )

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
            event_type = _event_type_for_state(state)
            if event_type is None:
                return
            principal = self._principals.get(spec.worker_id)
            canonical = CanonicalEvent(
                event_type=event_type,
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
                    "worker_id": spec.worker_id,
                    "worker_principal_id": (
                        principal.principal_id if principal is not None else ""
                    ),
                    "mission_id": spec.mission_id,
                    "allowed_tools": list(spec.allowed_tools),
                    "scope": dict(spec.scope),
                    "budgets": dict(spec.budgets),
                    "data_classification": spec.data_classification,
                    "executor_policy": spec.executor_policy,
                    "reason": reason,
                },
            )
            self._bus.append(canonical)


def _contract_strategy(contract: Any) -> str:
    metadata = getattr(contract, "metadata", {}) or {}
    return str(
        metadata.get("worker_strategy")
        or metadata.get("strategy")
        or getattr(contract, "worker_type", "deterministic")
    )


def _result_state(result: Any) -> WorkerState:
    status = str(
        getattr(result, "status", result) if result is not None else "completed"
    )
    if status in {"awaiting_capability", "awaiting_approval"}:
        return WorkerState.AWAITING_CAPABILITY
    if status in {"failed", "timeout", "killed", "contract_violation"}:
        return WorkerState.FAILED
    return WorkerState.COMPLETED


def _event_type_for_state(state: WorkerState) -> str | None:
    """Map internal lifecycle states to the canonical worker vocabulary."""

    mapping = {
        WorkerState.REQUESTED: CanonicalEventType.WORKER_REQUESTED,
        WorkerState.ADMITTED: CanonicalEventType.WORKER_ADMITTED,
        # BORN is an internal state; STARTED is the durable/public event.
        WorkerState.RUNNING: CanonicalEventType.WORKER_STARTED,
        WorkerState.AWAITING_CAPABILITY: CanonicalEventType.WORKER_AWAITING_CAPABILITY,
        WorkerState.COMPLETED: CanonicalEventType.WORKER_COMPLETED,
        WorkerState.FAILED: CanonicalEventType.WORKER_FAILED,
        WorkerState.KILLED: CanonicalEventType.WORKER_KILLED,
        WorkerState.DISSOLVED: CanonicalEventType.WORKER_DISSOLVED,
    }
    event_type = mapping.get(state)
    return event_type.value if event_type is not None else None


def _contract_budgets(contract: Any) -> dict[str, Any]:
    budget = getattr(contract, "budget", None)
    if budget is None:
        return {
            "max_steps": int(getattr(contract, "max_steps", 1)),
            "timeout_seconds": int(getattr(contract, "timeout_seconds", 1)),
        }
    if hasattr(budget, "model_dump"):
        return dict(budget.model_dump(mode="json"))
    if isinstance(budget, dict):
        return dict(budget)
    return {"value": str(budget)}


__all__ = [
    "StrategyUnavailable",
    "UnknownWorkerStrategy",
    "WorkerExecutionRequest",
    "WorkerFoundry",
    "WorkerStrategy",
]
