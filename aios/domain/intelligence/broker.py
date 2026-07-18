"""Canonical Frontier Intelligence Hiring Broker."""
from typing import Mapping, Sequence

from aios.domain.intelligence.contracts import HiringRequest, HiringDecision
from aios.domain.intelligence.privacy import PrivacyBroker


class HiringBroker:
    """The canonical intelligence boundary governing provider selection.
    
    Ensures that no model or component can independently bypass privacy policies,
    budget constraints, or fallback mechanisms.
    """

    def __init__(self) -> None:
        self.privacy_broker = PrivacyBroker()
        
        # In a real system, these would be injected or fetched from a registry
        # We simulate a basic capability mapping here to validate the contract
        self._provider_capabilities: Mapping[str, list[str]] = {
            "ollama": ["reasoning", "coding", "fast", "local"],
            "bedrock": ["reasoning", "coding", "frontier"],
            "gemini": ["reasoning", "coding", "frontier", "multimodal"],
            "openai": ["reasoning", "coding", "frontier"],
            "anthropic": ["reasoning", "coding", "frontier"],
        }
        
        self._cost_tiers: Mapping[str, int] = {
            "free": 0,
            "low": 1,
            "high": 2
        }
        
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
            p for p in eligible_providers
            if self._has_capabilities(p, request.required_capabilities)
        ]
        
        # 3. Cost gate
        budget_tier = self._cost_tiers.get(request.cost_budget, 0)
        affordable_providers = [
            p for p in capable_providers
            if self._cost_tiers.get(self._provider_costs.get(p, "high"), 2) <= budget_tier
        ]
        
        # Determine human approval necessity
        human_approval_required = False
        if request.data_classification == "confidential" and any(p not in ("ollama", "local") for p in affordable_providers):
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
                human_approval_required=False
            )
            
        # Select the best provider (prefer lowest cost among capable, then stable sort)
        affordable_providers.sort(key=lambda p: (self._cost_tiers.get(self._provider_costs.get(p, "high"), 2), p))
        selected = affordable_providers[0]
        
        return HiringDecision(
            eligible_providers=affordable_providers,
            selected_provider=selected,
            selected_model="auto",  # Defer to core router for specific model tag
            reason="Selected provider meets all constraints within budget.",
            redactions=[],
            external_data_scope=request.data_classification if selected not in ("ollama", "local") else "none",
            cost_limit=request.cost_budget,
            fallback_order=affordable_providers[1:],
            human_approval_required=human_approval_required
        )

    def _has_capabilities(self, provider: str, required: Sequence[str]) -> bool:
        caps = self._provider_capabilities.get(provider, [])
        return all(req in caps for req in required)
