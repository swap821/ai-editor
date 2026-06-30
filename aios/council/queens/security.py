"""Security Queen wrapper around the deterministic security gateway."""
from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

from aios.council.queen_verdict import highest_risk
from aios.runtime.contracts import MissionContract, QueenVerdict, RiskLevel
from aios.security.gateway import Zone, classify

_ALLOWED_TOOLS = {
    "read_file",
    "write_file",
    "run_command",
    "request_approval",
    "request_plan",
    "request_change",
}

_PROTECTED_PATTERNS = (
    "aios/security/",
    "aios/core/executor.py",
    "aios/core/approvals.py",
    "aios/core/verifier.py",
    "aios/core/self_apply.py",
)


class SecurityQueen:
    """Classify a MissionContract without changing the frozen security core."""

    name = "security"

    def review(self, contract: MissionContract) -> QueenVerdict:
        checks: list[dict[str, Any]] = []
        constraints: list[str] = []
        risks: list[RiskLevel] = [contract.risk_level]
        deny_reasons: list[str] = []

        unknown_tools = sorted(set(contract.allowed_tools) - _ALLOWED_TOOLS)
        if unknown_tools:
            deny_reasons.append(f"Unknown allowed tool(s): {', '.join(unknown_tools)}")
            risks.append("RED")

        for tool in contract.allowed_tools:
            if tool in {"write_file", "run_command"}:
                risks.append("YELLOW")
                constraints.append(f"{tool} remains contract-gated and auditable.")
            if tool == "request_change":
                model_policy = contract.metadata.get("model_policy")
                if not isinstance(model_policy, dict) or not model_policy.get("mode"):
                    deny_reasons.append(
                        "request_change requires explicit metadata.model_policy"
                    )
                    risks.append("RED")
                else:
                    risks.append("YELLOW")
                    constraints.append(
                        "request_change remains IntelligenceGateway-gated with explicit model policy."
                    )

        for rule in contract.allowed_files:
            normalized = self._normalize_path_rule(rule)
            if self._looks_unsafe_path_rule(normalized):
                deny_reasons.append(f"Unsafe allowed file rule: {rule}")
                risks.append("RED")
            if self._matches_protected_foundation(normalized):
                deny_reasons.append(f"Protected foundation file is allowed: {rule}")
                risks.append("RED")

        for command in contract.verification_commands:
            gateway_command = self._gateway_command_for_verification(command)
            result = classify(gateway_command)
            checks.append(
                {
                    "kind": "verification_command",
                    "command": command,
                    "gateway_command": gateway_command,
                    "zone": result.zone.value,
                    "reason": result.reason,
                }
            )
            if result.zone is Zone.RED:
                deny_reasons.append(
                    f"Verification command blocked by gateway: {result.reason}"
                )
                risks.append("RED")
            elif result.zone is Zone.YELLOW:
                risks.append("YELLOW")
                constraints.append("Verification command requires approval semantics.")

        risk = highest_risk(risks)
        if deny_reasons:
            return QueenVerdict(
                queen=self.name,
                verdict="deny",
                risk="RED",
                reason="; ".join(deny_reasons),
                constraints=constraints,
                confidence=0.94,
                metadata={"gateway_checks": checks},
            )

        verdict = "allow_with_approval" if risk == "YELLOW" or contract.requires_approval else "allow"
        return QueenVerdict(
            queen=self.name,
            verdict=verdict,
            risk=risk,
            reason="MissionContract passed deterministic security review.",
            constraints=constraints,
            confidence=0.9,
            metadata={"gateway_checks": checks},
        )

    def _gateway_command_for_verification(self, command: str) -> str:
        """Normalize trusted pytest invocations before gateway classification."""

        try:
            parts = shlex.split(command, posix=os.name != "nt")
        except ValueError:
            return command
        if len(parts) >= 3:
            executable = Path(parts[0]).name.lower()
            if executable in {"python", "python.exe"} and parts[1:3] == ["-m", "pytest"]:
                return " ".join(["python", "-m", "pytest", *parts[3:]])
        return command

    def _normalize_path_rule(self, rule: str) -> str:
        return rule.replace("\\", "/").strip().lstrip("./")

    def _looks_unsafe_path_rule(self, rule: str) -> bool:
        if not rule:
            return True
        path = Path(rule)
        if path.is_absolute() or rule.startswith("../") or "/../" in rule:
            return True
        return len(rule) >= 2 and rule[1] == ":"

    def _matches_protected_foundation(self, rule: str) -> bool:
        clean = rule.rstrip("/")
        for protected in _PROTECTED_PATTERNS:
            protected_clean = protected.rstrip("/")
            if clean == protected_clean or clean.startswith(f"{protected_clean}/"):
                return True
        return False


__all__ = ["SecurityQueen"]
