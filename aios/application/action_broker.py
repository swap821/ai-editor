"""ActionBroker: the application boundary between requests and authority.

The production constructor uses the durable exact ``CapabilityAuthority``.
The optional approval-store mode remains only as a compatibility adapter for
historical unit tests and is never constructed by the production dependency
graph.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Optional

from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.domain.actions.envelope import ActionEnvelope, ActionType
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.policy.decision import PolicyDecision

if TYPE_CHECKING:
    from aios.policy.kernel import PolicyKernel


class PolicyBrokerError(RuntimeError):
    """Raised when the broker cannot produce a usable PolicyDecision."""


class ActionBroker:
    """Submit one immutable envelope to policy and exact capability authority.

    ``capabilities`` is the production dependency. ``approvals`` is accepted
    only for the old unit-test adapter and deliberately has no production
    provider. A broker never executes an action; it only returns the policy
    verdict or a single-use capability requirement.
    """

    def __init__(
        self,
        kernel: PolicyKernel,
        approvals: Any | None = None,
        *,
        capabilities: CapabilityAuthority | None = None,
    ) -> None:
        if approvals is not None and capabilities is not None:
            raise ValueError("choose exact capabilities or legacy approvals, not both")
        if approvals is None and capabilities is None:
            raise ValueError("ActionBroker requires an exact capability authority")
        self.kernel = kernel
        self.approvals = approvals
        self.capabilities = capabilities

    def submit(
        self,
        envelope: ActionEnvelope,
        approval_token: Optional[str] = None,
        *,
        capability_token: Optional[str] = None,
        capability_binding: CapabilityBinding | None = None,
        issue_capability: bool = False,
    ) -> PolicyDecision:
        """Resolve *envelope* into a policy decision.

        Production callers pass ``capability_binding`` and optionally
        ``capability_token``. The positional ``approval_token`` remains an
        explicit compatibility alias for the legacy test adapter only.
        """
        if self.capabilities is not None:
            if approval_token is not None:
                raise PolicyBrokerError("legacy approval tokens are not valid in production")
            return self._submit_exact(
                envelope,
                capability_token,
                capability_binding,
                issue_capability=issue_capability,
            )
        return self._submit_legacy(envelope, approval_token)

    def _submit_exact(
        self,
        envelope: ActionEnvelope,
        token: Optional[str],
        binding: CapabilityBinding | None,
        *,
        issue_capability: bool = False,
    ) -> PolicyDecision:
        if binding is not None:
            self._validate_binding(envelope, binding)
        if token:
            try:
                # A valid consume is the completion of the logical action
                # whose issuance was rate-limited; inspect it before skipping
                # the second bucket increment on this retry.
                self.capabilities.inspect(token)
            except CapabilityError as exc:
                # Invalid bearer attempts are still counted against the same
                # templated route bucket; only a valid completion skips the
                # second increment for the logical issue/consume pair.
                self.kernel.check_endpoint_rate_limit(
                    self.kernel.rate_limited_route_path(envelope.route)
                    or envelope.route,
                    envelope.principal.client_ip,
                )
                raise PolicyBrokerError(str(exc)) from exc
        decision = self.kernel.decide(envelope, check_rate_limit=token is None)

        if decision.blocked:
            return decision

        # A GREEN action is authorised by its complete immutable envelope and
        # does not need a bearer capability.  Capability binding is mandatory
        # for every YELLOW issue/consume path; allowing a missing binding there
        # would turn a guard dependency into an approval bypass.
        if binding is None:
            if token or decision.requires_approval or issue_capability:
                raise PolicyBrokerError("exact capability binding is required")
            return decision
        if token:
            try:
                self.capabilities.consume(token, binding)
            except CapabilityError as exc:
                raise PolicyBrokerError(str(exc)) from exc
            return replace(
                decision,
                allowed=True,
                requires_approval=False,
                reason="exact capability consumed",
            )

        if not decision.requires_approval and not issue_capability:
            return decision
        if issue_capability or decision.requires_approval:
            try:
                issued = self.capabilities.issue(binding, action_payload=envelope.payload)
            except CapabilityError as exc:
                raise PolicyBrokerError(str(exc)) from exc
            return replace(
                decision,
                allowed=False,
                requires_approval=True,
                approval_token=issued,
            )

        return decision

    @staticmethod
    def _validate_binding(envelope: ActionEnvelope, binding: CapabilityBinding) -> None:
        binding_action_type = {
            ActionType.COUNCIL_MISSION_ROLLBACK: "rollback",
        }.get(envelope.action_type, envelope.action_type.value)
        if envelope.action_type is ActionType.GENERATE:
            requested = envelope.requested_capability or ""
            binding_action_type = requested.rsplit(".", 1)[-1]
        expected = {
            "operator_id": envelope.operator_id,
            "device_id": envelope.device_id,
            "authentication_event_id": envelope.authentication_event_id,
            "session_id": envelope.session_id,
            "action_type": binding_action_type,
            "route": envelope.route,
            "http_method": envelope.http_method,
            "payload_digest": envelope.payload_digest,
            "resource_digest": envelope.resource_digest,
            "mission_id": envelope.mission_id,
            "contract_digest": envelope.contract_digest,
            "policy_version": envelope.policy_version,
        }
        for field, value in expected.items():
            if getattr(binding, field) != value:
                raise PolicyBrokerError(f"capability binding mismatch for {field}")

    def _submit_legacy(
        self,
        envelope: ActionEnvelope,
        approval_token: Optional[str],
    ) -> PolicyDecision:
        """Compatibility adapter for the pre-R4 ApprovalStore test surface."""
        decision = self.kernel.decide(envelope)

        if decision.blocked:
            raise PolicyBrokerError(decision.reason)
        if not decision.requires_approval:
            return decision

        if approval_token:
            approved_action = self._peek_approval_token(envelope, approval_token)
            expected_action_type = self._approval_action_type(envelope)
            if (
                approved_action.action_type != expected_action_type
                or approved_action.payload != envelope.payload
                or approved_action.route != envelope.route
                or approved_action.http_method != envelope.http_method.upper()
            ):
                raise PolicyBrokerError(
                    "approval capability does not match the complete action envelope"
                )
            self._consume_approval_token(envelope, approval_token)
            return PolicyDecision(
                envelope_id=envelope.action_id,
                route=envelope.route,
                allowed=True,
                zone=decision.zone,
                reason="approval token consumed",
                audit_event=decision.audit_event,
            )

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
        """Record the exact pending action for the compatibility adapter."""
        session_id = envelope.session_id
        if not session_id:
            raise PolicyBrokerError("session_id is required to issue an approval token")
        action_type = self._approval_action_type(envelope)
        try:
            return self.approvals.issue(
                action_type,
                envelope.payload,
                session_id,
                route=envelope.route,
                http_method=envelope.http_method,
            )
        except Exception as exc:  # legacy adapter boundary
            raise PolicyBrokerError(str(exc)) from exc

    def _consume_approval_token(self, envelope: ActionEnvelope, token: str) -> Any:
        """Consume a compatibility token for the envelope's session."""
        session_id = envelope.session_id
        if not session_id:
            raise PolicyBrokerError("session_id is required to consume an approval token")
        try:
            return self.approvals.consume(token, session_id)
        except Exception as exc:  # legacy adapter boundary
            raise PolicyBrokerError(str(exc)) from exc

    def _peek_approval_token(self, envelope: ActionEnvelope, token: str) -> Any:
        session_id = envelope.session_id
        if not session_id:
            raise PolicyBrokerError("session_id is required to inspect an approval token")
        try:
            return self.approvals.peek(token, session_id)
        except Exception as exc:  # legacy adapter boundary
            raise PolicyBrokerError(str(exc)) from exc

    @staticmethod
    def _approval_action_type(envelope: ActionEnvelope) -> str:
        """Map envelope action type to the compatibility store vocabulary."""
        mapping: dict[ActionType, str] = {
            ActionType.COMMAND: "command",
            ActionType.ROLLBACK: "rollback",
            ActionType.FILES_EDIT: "edit",
            ActionType.PROPOSAL_APPLY: "edit",
            ActionType.KNOWLEDGE_INGEST: "create",
        }
        return mapping.get(envelope.action_type, "command")
