"""Strengthen-only constitution adapter.

This module turns the constitution snapshot into enforcement decisions for v10
planning flows. It may block, require review, or explain existing policy. It may
not downgrade security-gateway RED decisions or auto-approve YELLOW work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from aios.core import router
from aios.policy.constitution import Constitution, build_constitution, normalize_repo_path
from aios.runtime.budget_guard import BudgetGuard
from aios.runtime.castes import caste_contract_issues, caste_from_contract
from aios.runtime.contracts import MissionContract, RiskLevel
from aios.security import gateway


@dataclass(frozen=True)
class EnforcementDecision:
    allowed: bool
    risk: RiskLevel
    reason: str
    source: str
    requires_human: bool = False
    fallback: str | None = None
    constraints: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


class ConstitutionEnforcer:
    """Typed facade over existing fail-closed runtime gates."""

    def __init__(
        self,
        *,
        constitution: Constitution | None = None,
        budget_guard: BudgetGuard | None = None,
    ) -> None:
        self.constitution = constitution if constitution is not None else build_constitution()
        self.budget_guard = (
            budget_guard
            if budget_guard is not None
            else BudgetGuard(mode=self.constitution.resource_mode)
        )

    def check_file_edit(self, path: str, *, actor: str = "worker") -> EnforcementDecision:
        normalized = normalize_repo_path(path)
        if self.constitution.is_frozen_path(normalized):
            return EnforcementDecision(
                allowed=False,
                risk="RED",
                reason=f"frozen core path blocked for {actor}: {normalized}",
                source="constitution",
                constraints=("human Section VIII review required for any proposal",),
                metadata={"path": normalized, "actor": actor},
            )
        return EnforcementDecision(
            allowed=True,
            risk="YELLOW",
            reason="file edit is outside frozen core; existing scope, audit, approval, verifier, and rollback gates still apply",
            source="constitution",
            requires_human=True,
            constraints=(
                "scope check",
                "audit entry before write",
                "human approval when classified YELLOW",
                "verifier",
                "rollback support",
            ),
            metadata={"path": normalized, "actor": actor},
        )

    def check_command(self, command: str, *, session_id: str | None = None) -> EnforcementDecision:
        decision = gateway.validate_command(command, session_id=session_id)
        return EnforcementDecision(
            allowed=decision.status == "ALLOW",
            risk=decision.zone.value,  # type: ignore[arg-type]
            reason=f"{decision.status}: {decision.reason}",
            source="security_gateway",
            requires_human=decision.status == "REQUIRE_HUMAN",
            constraints=("security gateway decision is authoritative",),
            metadata={"gateway_status": decision.status},
        )

    def check_cloud_request(
        self,
        contract: MissionContract,
        *,
        task: str,
        estimated_tokens: int,
        estimated_cost: float = 0.0,
    ) -> EnforcementDecision:
        task_key = task.strip().lower()
        cloud_probe = router.Provider(
            name="constitution-cloud-probe",
            privacy=router.PRIVACY_CLOUD,
            cost=router.COST_HIGH,
            available=True,
            models=("policy-probe",),
        )
        policy = router.Policy(
            cloud_tasks=frozenset(self.constitution.router_cloud_tasks),
            max_cost=self.constitution.router_max_cost,
            prefer_local=self.constitution.router_prefer_local,
        )
        if not router.policy_allows(policy, task_key, cloud_probe):
            return EnforcementDecision(
                allowed=False,
                risk="YELLOW",
                reason=f"cloud request blocked by router policy for task '{task_key}'",
                source="router_policy",
                fallback="local_ollama",
                constraints=("cloud may not bypass AIOS_ROUTER_CLOUD_TASKS or cost policy",),
                metadata={"task": task_key},
            )

        budget = self.budget_guard.check_cloud_request(
            contract,
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
        )
        if not budget.allowed:
            return EnforcementDecision(
                allowed=False,
                risk="YELLOW",
                reason=budget.reason,
                source="budget_guard",
                fallback=budget.fallback,
                constraints=("resource ecology is fail-closed for cloud requests",),
                metadata={"task": task_key},
            )

        return EnforcementDecision(
            allowed=True,
            risk="YELLOW",
            reason="cloud request is eligible under router policy and mission budget",
            source="router_policy+budget_guard",
            fallback=budget.fallback,
            constraints=("provider credentials/configuration are still required",),
            metadata={"task": task_key},
        )

    def check_caste_spawn(self, contract: MissionContract) -> EnforcementDecision:
        try:
            profile = caste_from_contract(contract)
            issues = caste_contract_issues(contract)
        except ValueError as exc:
            return EnforcementDecision(
                allowed=False,
                risk="YELLOW",
                reason=str(exc),
                source="caste_system",
                requires_human=True,
                constraints=("unknown castes cannot spawn without review",),
            )

        if issues:
            return EnforcementDecision(
                allowed=False,
                risk=contract.risk_level,
                reason="; ".join(issues),
                source="caste_system",
                requires_human=True,
                constraints=("caste profile violations must be corrected before spawn",),
                metadata={"caste": profile.name if profile is not None else None},
            )

        caste_name = profile.name if profile is not None else "unspecified"
        return EnforcementDecision(
            allowed=True,
            risk=contract.risk_level,
            reason=f"caste spawn contract is compatible with {caste_name} profile",
            source="caste_system",
            requires_human=contract.requires_approval,
            constraints=("worker is ephemeral single-task evidence-only runtime",),
            metadata={"caste": caste_name},
        )


__all__ = ["ConstitutionEnforcer", "EnforcementDecision"]
