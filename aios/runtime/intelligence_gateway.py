"""Plan-only local/cloud reasoning gateway for Council Runtime workers."""
from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from aios import config
from aios.core.llm import LLMClient, OllamaClient
from aios.runtime.budget_guard import BudgetGuard
from aios.runtime.contracts import MissionContract, RiskLevel
from aios.runtime.secret_policy import SecretPolicy


class IntelligenceGatewayError(RuntimeError):
    """Raised when no permitted reasoning provider can return a plan."""


class ReasoningClient(Protocol):
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        ...


class RuntimeIntelligenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntelligenceRequest(RuntimeIntelligenceModel):
    mission_id: str
    worker_id: str
    purpose: Literal["plan", "summarize", "reflect", "repair"]
    prompt: str
    risk: RiskLevel
    allow_cloud: bool = False
    max_tokens: int = 1500
    timeout_seconds: int = 20


class IntelligenceResponse(RuntimeIntelligenceModel):
    provider: str
    model: str
    used_cloud: bool
    text: str
    cost_estimate: float | None = None
    fallback_used: bool = False
    policy: dict[str, Any] = Field(default_factory=dict)


class LocalOllamaReasoner:
    """Small adapter around the existing Ollama completion client."""

    def __init__(self, client: LLMClient | None = None, *, model: str | None = None) -> None:
        self.model = model or config.LLM_MODEL
        self.client = client or OllamaClient(model=self.model)

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.client.complete(prompt, system=system)


class IntelligenceGateway:
    """Route reasoning requests without giving workers provider access."""

    PLAN_SYSTEM_PROMPT = (
        "You are a planning-only assistant inside Council Runtime. "
        "Return concise implementation guidance. Do not claim approval, do not "
        "execute commands, and do not request secrets."
    )

    def __init__(
        self,
        *,
        local_client: ReasoningClient | None = None,
        local_model: str | None = None,
        cloud_clients: dict[str, ReasoningClient] | None = None,
        default_cloud_provider: str = "cloud",
        budget_guard: BudgetGuard | None = None,
        secret_policy: SecretPolicy | None = None,
    ) -> None:
        self.local_model = local_model or config.LLM_MODEL
        self.local_client = local_client or LocalOllamaReasoner(model=self.local_model)
        self.cloud_clients = cloud_clients or {}
        self.default_cloud_provider = default_cloud_provider
        self.budget_guard = budget_guard or BudgetGuard()
        self.secret_policy = secret_policy or SecretPolicy()

    def request(
        self,
        request: IntelligenceRequest,
        *,
        contract: MissionContract,
    ) -> IntelligenceResponse:
        if request.mission_id != contract.mission_id:
            raise ValueError("IntelligenceRequest mission_id does not match contract")
        secret_decision = self.secret_policy.inspect_text(request.prompt)
        safe_prompt = secret_decision.scrubbed
        budget = self.budget_guard.check_cloud_request(
            contract,
            estimated_tokens=request.max_tokens,
        )
        cloud_allowed = self._cloud_allowed(
            request,
            contract,
            secret_cloud_allowed=secret_decision.cloud_allowed,
            budget_allowed=budget.allowed,
        )
        policy: dict[str, Any] = {
            "allow_cloud_requested": request.allow_cloud,
            "cloud_allowed": cloud_allowed,
            "budget_allowed": budget.allowed,
            "budget_reason": budget.reason,
            "secret_detected": secret_decision.detected,
            "secret_findings": list(secret_decision.findings),
        }

        if cloud_allowed and self.cloud_clients:
            provider = self._choose_cloud_provider(contract)
            client = self.cloud_clients.get(provider)
            if client is not None:
                try:
                    raw = client.complete(safe_prompt, system=self.PLAN_SYSTEM_PROMPT)
                    text = self.secret_policy.redact_text(raw)
                    self.budget_guard.record_cloud_usage(
                        contract,
                        tokens=self._estimate_tokens(safe_prompt + text),
                        cost=0.0,
                    )
                    return IntelligenceResponse(
                        provider=provider,
                        model=str(contract.metadata.get("cloud_model", provider)),
                        used_cloud=True,
                        text=text,
                        cost_estimate=0.0,
                        fallback_used=False,
                        policy=policy,
                    )
                except Exception as exc:  # noqa: BLE001 - fallback is the policy
                    policy["cloud_error"] = str(exc)

        try:
            raw = self.local_client.complete(safe_prompt, system=self.PLAN_SYSTEM_PROMPT)
        except Exception as exc:  # noqa: BLE001 - normalize provider failures
            raise IntelligenceGatewayError(
                "local reasoning provider failed after cloud was denied or unavailable"
            ) from exc
        return IntelligenceResponse(
            provider="ollama",
            model=self.local_model,
            used_cloud=False,
            text=self.secret_policy.redact_text(raw),
            fallback_used=bool(request.allow_cloud),
            policy=policy,
        )

    def _cloud_allowed(
        self,
        request: IntelligenceRequest,
        contract: MissionContract,
        *,
        secret_cloud_allowed: bool,
        budget_allowed: bool,
    ) -> bool:
        if not request.allow_cloud:
            return False
        if request.risk == "RED" or contract.risk_level == "RED":
            return False
        if not secret_cloud_allowed:
            return False
        if not budget_allowed:
            return False
        return True

    def _choose_cloud_provider(self, contract: MissionContract) -> str:
        model_policy = contract.metadata.get("model_policy", {})
        if isinstance(model_policy, dict):
            provider = model_policy.get("provider")
            if isinstance(provider, str) and provider:
                return provider
        return self.default_cloud_provider

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


__all__ = [
    "IntelligenceGateway",
    "IntelligenceGatewayError",
    "IntelligenceRequest",
    "IntelligenceResponse",
    "LocalOllamaReasoner",
    "ReasoningClient",
]
