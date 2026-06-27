"""Budget controls for Council Runtime intelligence routing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aios.runtime.contracts import MissionContract


@dataclass(frozen=True)
class ModelPolicy:
    mode: str = "local"
    allow_cloud: bool = False
    max_cloud_calls: int = 0
    max_tokens_per_request: int = 1500
    max_tokens_total: int = 6000
    mission_cloud_budget: float | None = None
    daily_cloud_budget: float | None = None
    fallback: str = "local_ollama"
    deny_when_budget_exceeded: bool = True


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    reason: str = ""
    fallback: str = "local_ollama"


@dataclass
class BudgetUsage:
    cloud_calls: int = 0
    tokens_total: int = 0
    cost_total: float = 0.0


@dataclass
class BudgetGuard:
    """In-memory budget accounting for a spawner/runtime process."""

    usage_by_mission: dict[str, BudgetUsage] = field(default_factory=dict)
    daily_cost_total: float = 0.0

    def policy_for(self, contract: MissionContract) -> ModelPolicy:
        raw = contract.metadata.get("model_policy", {})
        if not isinstance(raw, dict):
            raw = {}
        return ModelPolicy(
            mode=str(raw.get("mode", "local")),
            allow_cloud=bool(raw.get("allow_cloud", False)),
            max_cloud_calls=int(raw.get("max_cloud_calls", 0)),
            max_tokens_per_request=int(raw.get("max_tokens_per_request", 1500)),
            max_tokens_total=int(raw.get("max_tokens_total", 6000)),
            mission_cloud_budget=self._optional_float(raw.get("mission_cloud_budget")),
            daily_cloud_budget=self._optional_float(raw.get("daily_cloud_budget")),
            fallback=str(raw.get("fallback", "local_ollama")),
            deny_when_budget_exceeded=bool(raw.get("deny_when_budget_exceeded", True)),
        )

    def check_cloud_request(
        self,
        contract: MissionContract,
        *,
        estimated_tokens: int,
        estimated_cost: float = 0.0,
    ) -> BudgetDecision:
        policy = self.policy_for(contract)
        if policy.mode == "local" or not policy.allow_cloud:
            return BudgetDecision(False, "cloud disabled by model_policy", policy.fallback)
        if estimated_tokens > policy.max_tokens_per_request:
            return BudgetDecision(False, "request token budget exceeded", policy.fallback)
        usage = self.usage_by_mission.setdefault(contract.mission_id, BudgetUsage())
        if usage.cloud_calls >= policy.max_cloud_calls:
            return BudgetDecision(False, "mission cloud call budget exceeded", policy.fallback)
        if usage.tokens_total + estimated_tokens > policy.max_tokens_total:
            return BudgetDecision(False, "mission token budget exceeded", policy.fallback)
        if (
            policy.mission_cloud_budget is not None
            and usage.cost_total + estimated_cost > policy.mission_cloud_budget
        ):
            return BudgetDecision(False, "mission cloud cost budget exceeded", policy.fallback)
        if (
            policy.daily_cloud_budget is not None
            and self.daily_cost_total + estimated_cost > policy.daily_cloud_budget
        ):
            return BudgetDecision(False, "daily cloud cost budget exceeded", policy.fallback)
        return BudgetDecision(True, fallback=policy.fallback)

    def record_cloud_usage(
        self,
        contract: MissionContract,
        *,
        tokens: int,
        cost: float = 0.0,
    ) -> None:
        usage = self.usage_by_mission.setdefault(contract.mission_id, BudgetUsage())
        usage.cloud_calls += 1
        usage.tokens_total += tokens
        usage.cost_total += cost
        self.daily_cost_total += cost

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        return float(value)


__all__ = ["BudgetDecision", "BudgetGuard", "BudgetUsage", "ModelPolicy"]
