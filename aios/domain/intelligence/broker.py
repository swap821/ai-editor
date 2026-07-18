"""Canonical Frontier Intelligence Hiring Broker."""

from dataclasses import dataclass
from typing import Mapping, Sequence

from aios.application.models.privacy_broker import PrivacyBroker as ModelPrivacyBroker
from aios.core import router
from aios.domain.intelligence.contracts import HiringRequest, HiringDecision
from aios.domain.intelligence.privacy import PrivacyBroker
from aios.domain.privacy import ModelCallRequest, PrivacyDecision


@dataclass(frozen=True)
class HiringSelection:
    """Policy- and privacy-bound routes for one executable model request."""

    decision: HiringDecision
    privacy: PrivacyDecision
    routes: tuple[router.Route, ...]


class HiringBroker:
    """The canonical intelligence boundary governing provider selection.

    Ensures that no model or component can independently bypass privacy policies,
    budget constraints, or fallback mechanisms.
    """

    def __init__(self) -> None:
        self.privacy_broker = PrivacyBroker()
        self.model_privacy_broker = ModelPrivacyBroker()

        # In a real system, these would be injected or fetched from a registry
        # We simulate a basic capability mapping here to validate the contract
        self._provider_capabilities: Mapping[str, list[str]] = {
            "ollama": ["reasoning", "coding", "fast", "local"],
            "bedrock": ["reasoning", "coding", "frontier"],
            "gemini": ["reasoning", "coding", "frontier", "multimodal"],
            "openai": ["reasoning", "coding", "frontier"],
            "anthropic": ["reasoning", "coding", "frontier"],
        }

        self._cost_tiers: Mapping[str, int] = {"free": 0, "low": 1, "high": 2}

        self._provider_costs: Mapping[str, str] = {
            "ollama": "free",
            "bedrock": "high",
            "gemini": "low",
            "openai": "high",
            "anthropic": "high",
        }

    def evaluate_request(self, request: HiringRequest) -> HiringDecision:
        """Evaluate a hiring request and return a deterministic decision."""
        # 1. Privacy gate (MUST run first)
        eligible_providers = self.privacy_broker.filter_eligible_providers(request)

        # 2. Capability gate
        capable_providers = [
            p
            for p in eligible_providers
            if self._has_capabilities(p, request.required_capabilities)
        ]

        # 3. Cost gate
        budget_tier = self._cost_tiers.get(request.cost_budget, 0)
        affordable_providers = [
            p
            for p in capable_providers
            if self._cost_tiers.get(self._provider_costs.get(p, "high"), 2)
            <= budget_tier
        ]

        # Determine human approval necessity
        human_approval_required = False
        if request.data_classification == "confidential" and any(
            p not in ("ollama", "local") for p in affordable_providers
        ):
            human_approval_required = True

        if not affordable_providers:
            return HiringDecision(
                eligible_providers=[],
                selected_provider=None,
                selected_model=None,
                reason="No candidate provider meets privacy, capability, and cost constraints.",
                redactions=[],
                external_data_scope="none",
                cost_limit=request.cost_budget,
                fallback_order=[],
                human_approval_required=False,
            )

        # Select the best provider (prefer lowest cost among capable, then stable sort)
        affordable_providers.sort(
            key=lambda p: (
                self._cost_tiers.get(self._provider_costs.get(p, "high"), 2),
                p,
            )
        )
        selected = affordable_providers[0]

        return HiringDecision(
            eligible_providers=affordable_providers,
            selected_provider=selected,
            selected_model="auto",  # Defer to core router for specific model tag
            reason="Selected provider meets all constraints within budget.",
            redactions=[],
            external_data_scope=request.data_classification
            if selected not in ("ollama", "local")
            else "none",
            cost_limit=request.cost_budget,
            fallback_order=affordable_providers[1:],
            human_approval_required=human_approval_required,
        )

    def select_model_call(
        self,
        request: ModelCallRequest,
        providers: Sequence[router.Provider],
        *,
        policy: router.Policy = router.LOCAL_FIRST,
        require_tools: bool = False,
    ) -> HiringSelection:
        """Select an executable route from injected runtime provider facts.

        This is the production HiringBroker seam.  Provider availability,
        model identifiers, and cost metadata come from the injected provider
        rows; this method never constructs or probes an adapter.  Privacy is
        evaluated before the router sees a candidate, and the router policy is
        the operator-owned cloud/cost gate.
        """
        privacy = self.model_privacy_broker.evaluate(request)
        eligible = [
            provider
            for provider in providers
            if provider.name in privacy.allowed_providers
        ]
        routes = tuple(
            router.candidates(
                request.task,
                eligible,
                policy=policy,
                require_tools=require_tools,
            )
        )
        selected = routes[0] if routes else None
        decision = HiringDecision(
            eligible_providers=[route.provider for route in routes],
            selected_provider=selected.provider if selected else None,
            selected_model=selected.model if selected else None,
            reason=(
                selected.reason
                if selected
                else "No policy-allowed, available provider can execute this request."
            ),
            redactions=list(privacy.redactions),
            external_data_scope=(
                request.data_classification.value
                if selected and selected.privacy == router.PRIVACY_CLOUD
                else "none"
            ),
            cost_limit=policy.max_cost,
            fallback_order=[route.provider for route in routes[1:]],
            human_approval_required=(
                selected is not None
                and selected.privacy == router.PRIVACY_CLOUD
                and request.data_classification.value
                in {"SENSITIVE", "SECRET", "NEVER_EXTERNAL"}
            ),
        )
        return HiringSelection(decision=decision, privacy=privacy, routes=routes)

    def _has_capabilities(self, provider: str, required: Sequence[str]) -> bool:
        caps = self._provider_capabilities.get(provider, [])
        return all(req in caps for req in required)
