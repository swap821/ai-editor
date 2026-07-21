"""Fail-closed verification for exact, server-issued capabilities."""

from __future__ import annotations

from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.domain.capabilities.contracts import Capability, CapabilityBinding


class CapabilityVerifier:
    """Verify a capability against the complete action binding.

    Verification is intentionally separate from issuance.  Callers must supply
    a server-built binding containing the authenticated operator, device,
    authentication event, session, route, method, payload/resource digests and
    policy metadata.  A bearer token never supplies or overrides any of those
    fields.
    """

    def __init__(self, authority: CapabilityAuthority) -> None:
        self.authority = authority

    def verify(self, token: str, binding: CapabilityBinding) -> Capability:
        """Return the unconsumed capability only when every field matches."""
        capability = self.authority.inspect(token)
        if capability.binding != binding:
            raise CapabilityError("capability binding mismatch")
        if capability.revoked_at is not None:
            raise CapabilityError("capability revoked")
        if capability.consumed_at is not None:
            raise CapabilityError("capability already consumed")
        if capability.expires_at <= self.authority.clock():
            raise CapabilityError("capability expired")
        return capability

    def consume(self, token: str, binding: CapabilityBinding) -> Capability:
        """Atomically consume a previously verified exact capability."""
        self.verify(token, binding)
        return self.authority.consume(token, binding)
