"""Application broker: turn ActionEnvelope + policy into executable decisions.

The broker sits between the HTTP routes and the PolicyKernel. It is the only
place allowed to issue and consume approval tokens; the kernel stays pure and
deterministic.
"""
from __future__ import annotations

from typing import Optional

from aios.core.approvals import ApprovalError, ApprovalStore, ApprovedAction
from aios.domain.actions.envelope import ActionEnvelope, ActionType
from aios.domain.policy.decision import PolicyDecision
from aios.policy.kernel import PolicyKernel


class PolicyBrokerError(RuntimeError):
    """Raised when the broker cannot produce a usable PolicyDecision."""


class ActionBroker:
    """Issue approval capabilities and resolve ActionEnvelopes into decisions.

    The broker is stateless aside from its injected kernel and approval store.
    It never weakens a RED block, but it can resolve a YELLOW decision when a
    valid approval token is supplied.
    """

    def __init__(self, kernel: PolicyKernel, approvals: ApprovalStore) -> None:
        self.kernel = kernel
        self.approvals = approvals

    def submit(
        self,
        envelope: ActionEnvelope,
        approval_token: Optional[str] = None,
    ) -> PolicyDecision:
        """Resolve *envelope* into a decision, issuing or consuming tokens.

        Returns an allowed decision for GREEN actions. For YELLOW actions:
          - if *approval_token* is provided and valid, consumes it and returns
            an allowed decision;
          - otherwise issues a fresh token and returns a decision with
            ``requires_approval=True``.
        RED actions always raise ``PolicyBrokerError``.
        """
        decision = self.kernel.decide(envelope)

        if decision.blocked:
            raise PolicyBrokerError(decision.reason)

        if not decision.requires_approval:
            return decision

        # YELLOW action. If the caller supplied an approval token, consume it.
        if approval_token:
            approved_action = self._consume_approval_token(envelope, approval_token)
            return PolicyDecision(
                envelope_id=envelope.action_id,
                route=envelope.route,
                allowed=True,
                zone=decision.zone,
                reason="approval token consumed",
                audit_event=decision.audit_event,
            )

        # No token: issue one and pause for human approval.
        token = self._issue_approval_token(envelope)
        return PolicyDecision(
            envelope_id=envelope.action_id,
            route=envelope.route,
            requires_approval=True,
            zone=decision.zone,
            reason="human approval required",
            audit_event=decision.audit_event,
            approval_token=token,
        )

    def _issue_approval_token(self, envelope: ActionEnvelope) -> str:
        """Record the exact pending action and return an opaque token."""
        session_id = envelope.session_id
        if not session_id:
            raise PolicyBrokerError("session_id is required to issue an approval token")
        action_type = self._approval_action_type(envelope)
        try:
            return self.approvals.issue(action_type, envelope.payload, session_id)
        except ApprovalError as exc:
            raise PolicyBrokerError(str(exc)) from exc

    def _consume_approval_token(
        self, envelope: ActionEnvelope, token: str
    ) -> ApprovedAction:
        """Consume a token and verify it matches the envelope's session."""
        session_id = envelope.session_id
        if not session_id:
            raise PolicyBrokerError("session_id is required to consume an approval token")
        try:
            return self.approvals.consume(token, session_id)
        except ApprovalError as exc:
            raise PolicyBrokerError(str(exc)) from exc

    @staticmethod
    def _approval_action_type(envelope: ActionEnvelope) -> str:
        """Map envelope action type to the approval store's action vocabulary."""
        mapping: dict[ActionType, str] = {
            ActionType.COMMAND: "command",
            ActionType.ROLLBACK: "rollback",
            ActionType.FILES_EDIT: "edit",
            ActionType.PROPOSAL_APPLY: "edit",
            ActionType.KNOWLEDGE_INGEST: "create",
        }
        return mapping.get(envelope.action_type, "command")
