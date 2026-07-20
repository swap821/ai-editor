"""Immutable policy decision -- the deterministic output of the Policy Kernel."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from aios.security.gateway import Zone


@dataclass(frozen=True)
class PolicyDecision:
    """Deterministic authority verdict for a single ActionEnvelope.

    A decision is one of:
      - allowed + not blocked   -> execute now
      - blocked                 -> refuse permanently (RED)
      - requires_approval       -> pause for human approval (YELLOW)

    The kernel never issues approval tokens directly; that is the ActionBroker's
    responsibility, so that token lifecycle stays in the application layer.
    """

    envelope_id: str
    route: str
    allowed: bool = False
    blocked: bool = False
    requires_approval: bool = False
    zone: Zone = Zone.RED
    reason: str = ""
    audit_event: str = ""
    approval_token: Optional[str] = None
    consumed_capability_proof: Optional[Any] = None
    decision_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.allowed and self.blocked:
            raise ValueError("a decision cannot be both allowed and blocked")
        if self.allowed and self.requires_approval:
            raise ValueError("a decision cannot be both allowed and require approval")
        if self.blocked and self.requires_approval:
            raise ValueError("a decision cannot be both blocked and require approval")
