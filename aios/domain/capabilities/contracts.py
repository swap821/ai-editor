"""Immutable capability binding and lifecycle contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class CapabilityBinding:
    """The complete action a capability may authorize."""

    operator_id: str
    device_id: str
    authentication_event_id: str
    session_id: str
    action_type: str
    route: str
    http_method: str
    payload_digest: str
    resource_digest: str
    mission_id: Optional[str]
    contract_digest: Optional[str]
    policy_version: str
    scope: str
    verification_requirement: str

    def __post_init__(self) -> None:
        required = {
            "operator_id": self.operator_id,
            "device_id": self.device_id,
            "authentication_event_id": self.authentication_event_id,
            "session_id": self.session_id,
            "action_type": self.action_type,
            "route": self.route,
            "http_method": self.http_method,
            "payload_digest": self.payload_digest,
            "resource_digest": self.resource_digest,
            "policy_version": self.policy_version,
            "scope": self.scope,
            "verification_requirement": self.verification_requirement,
        }
        if any(not isinstance(value, str) or not value.strip() for value in required.values()):
            raise ValueError("capability binding fields must be non-empty strings")
        for name in ("mission_id", "contract_digest"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be non-empty when provided")
        object.__setattr__(self, "http_method", self.http_method.upper())


@dataclass(frozen=True)
class Capability:
    """Durable capability record; the bearer token itself is never retained."""

    capability_id: str
    binding: CapabilityBinding
    issued_at: float
    expires_at: float
    nonce: str
    action_payload: Optional[dict[str, Any]] = None
    consumed_at: Optional[float] = None
    revoked_at: Optional[float] = None


@dataclass(frozen=True)
class ConsumedCapabilityProof:
    """Server-created proof of a consumed exact capability."""

    capability_id: str
    token_digest: str
    operator_id: str
    device_id: str
    authentication_event_id: str
    session_id: str
    action_type: str
    route: str
    http_method: str
    payload_digest: str
    resource_digest: str
    mission_id: Optional[str]
    contract_digest: Optional[str]
    policy_version: str
    scope: str
    verification_requirement: str
    consumed_at: float
    expires_at: float
    revoked_at: Optional[float] = None

