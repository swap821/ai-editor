"""Routing Queen — deterministic adapter for worker-strategy and model routing.

This Queen does not call external models. It inspects the MissionContract and
recommends the safest matching worker strategy, adding constraints that narrow
scope rather than widening it.
"""
from __future__ import annotations

from aios.runtime.contracts import MissionContract, QueenEvidence, QueenVerdict


class RoutingQueen:
    """Recommend a bounded worker strategy and provider constraints."""

    name = "routing"

    def review(self, contract: MissionContract) -> QueenVerdict:
        strategy = self._select_strategy(contract)
        provider_constraints = self._provider_constraints(contract)
        constraints = [f"routing: worker strategy locked to {strategy}"]
        if provider_constraints:
            constraints.append(f"routing: provider constraints = {provider_constraints}")

        return QueenVerdict(
            queen=self.name,
            verdict="allow",
            risk=contract.risk_level,
            reason=f"Routing Queen recommends {strategy} with bounded provider constraints.",
            constraints=constraints,
            confidence=0.88,
            confidence_basis="deterministic contract inspection",
            evidence=QueenEvidence(
                basis="contract.worker_type, allowed_tools, metadata.model_policy",
                checks=[
                    {"kind": "strategy", "value": strategy},
                    {"kind": "provider_constraints", "value": provider_constraints},
                ],
            ),
            recommended_worker_strategy=strategy,
            unresolved_questions=[],
            metadata={
                "recommended_strategy": strategy,
                "provider_constraints": provider_constraints,
            },
        )

    def _select_strategy(self, contract: MissionContract) -> str:
        worker = contract.worker_type.lower()
        if "swarm" in worker:
            return "swarm_strategy"
        if "role_pass" in worker:
            return "role_pass_strategy"
        if "tool" in worker or "agent" in worker:
            return "tool_loop_strategy"
        if "deterministic" in worker or "code" in worker:
            return "deterministic_worker_strategy"
        return "hybrid_plan_worker"

    def _provider_constraints(self, contract: MissionContract) -> list[str]:
        model_policy = contract.metadata.get("model_policy")
        if isinstance(model_policy, dict):
            mode = model_policy.get("mode")
            if mode == "local_only":
                return ["local_only"]
            if mode == "cloud_with_approval":
                return ["cloud_with_approval"]
        if contract.risk_level == "RED":
            return ["prefer_local"]
        return []


__all__ = ["RoutingQueen"]
