"""Deterministic privacy and redaction boundary for model exposure."""
from __future__ import annotations

from aios.domain.privacy import (
    DataClassification,
    ModelCallRequest,
    PrivacyDecision,
)
from aios.runtime.secret_policy import SecretPolicy


class PrivacyViolation(RuntimeError):
    """Raised when a model request would violate its egress policy."""


_LOCAL_PROVIDERS = frozenset({"ollama", "local"})
_NON_EXTERNAL = frozenset(
    {DataClassification.SECRET, DataClassification.NEVER_EXTERNAL}
)


class PrivacyBroker:
    """Evaluate data egress before a provider is selected or called."""

    def __init__(self, secret_policy: SecretPolicy | None = None) -> None:
        self.secret_policy = secret_policy or SecretPolicy()

    def evaluate(
        self,
        request: ModelCallRequest,
        *,
        provider: str | None = None,
    ) -> PrivacyDecision:
        inspected = self.secret_policy.inspect_text(request.prompt)
        policy = request.policy
        allowed = list(policy.allowed_providers)
        reasons: list[str] = []
        local_only = policy.local_only or request.data_classification in _NON_EXTERNAL
        if inspected.detected:
            reasons.append("SECRET_REDACTED")
            local_only = True
        if request.data_classification in _NON_EXTERNAL:
            reasons.append("CLASSIFICATION_NEVER_EXTERNAL")
        if local_only:
            allowed = [name for name in allowed if name in _LOCAL_PROVIDERS]
            if not allowed:
                allowed = ["ollama"]
        if provider is not None:
            if provider not in allowed:
                reasons.append("PROVIDER_NOT_ALLOWLISTED")
                return PrivacyDecision(
                    allowed=False,
                    data_classification=request.data_classification,
                    scrubbed_prompt=inspected.scrubbed,
                    redactions=inspected.findings,
                    allowed_providers=tuple(allowed),
                    reason_codes=tuple(reasons),
                    local_only=local_only,
                )
        return PrivacyDecision(
            allowed=bool(allowed),
            data_classification=request.data_classification,
            scrubbed_prompt=inspected.scrubbed,
            redactions=inspected.findings,
            allowed_providers=tuple(dict.fromkeys(allowed)),
            reason_codes=tuple(reasons),
            local_only=local_only,
        )

    def require(self, request: ModelCallRequest, *, provider: str) -> PrivacyDecision:
        decision = self.evaluate(request, provider=provider)
        if not decision.allowed:
            raise PrivacyViolation(
                f"provider {provider!r} denied: {', '.join(decision.reason_codes) or 'policy'}"
            )
        return decision


__all__ = ["PrivacyBroker", "PrivacyViolation"]
