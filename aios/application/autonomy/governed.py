"""One governed learning loop over the existing AutonomyLedger and Cerebellum."""

from __future__ import annotations

import hashlib
from typing import Any

from aios.core.autonomy import AutonomyLedger
from aios.core.verification_strength import VerificationStrength
from aios.domain.autonomy import (
    ActionClassKey,
    AutonomyDecision,
    AutonomyDecisionStatus,
    AutonomyOutcome,
    CerebellumProposal,
)
from aios.security.secret_scanner import scan_and_redact


class GovernedAutonomy:
    """Proposal/reuse/outcome loop; it never grants authority to a model."""

    _FORBIDDEN_ACTIONS = frozenset(
        {
            "network_request",
            "secret_access",
            "package_install",
            "control_plane_modify",
            "policy_modify",
            "credential_manage",
        }
    )
    _FORBIDDEN_CLASSIFICATIONS = frozenset({"SECRET", "NEVER_EXTERNAL"})

    def __init__(
        self,
        *,
        ledger: AutonomyLedger,
        enabled: bool = False,
        profile_name: str = "production",
        production_gate_open: bool = False,
        emergency_stop: Any | None = None,
    ) -> None:
        self.ledger = ledger
        self.enabled = bool(enabled)
        self.profile_name = profile_name.strip().lower()
        self.production_gate_open = bool(production_gate_open)
        self.emergency_stop = emergency_stop

    def disable(self) -> None:
        """Disable local autonomy after an emergency stop or operator action."""
        self.enabled = False

    @staticmethod
    def key_digest(key: ActionClassKey) -> str:
        return hashlib.sha256(key.model_dump_json().encode("utf-8")).hexdigest()

    def evaluate(
        self,
        key: ActionClassKey,
        *,
        enabled: bool | None = None,
    ) -> AutonomyDecision:
        """Return ALLOW only for an earned, narrow, reversible action class."""
        if self.emergency_stop is not None:
            try:
                self.emergency_stop.assert_operational()
            except Exception:  # noqa: BLE001 - emergency latch denies autonomy
                return AutonomyDecision(
                    status=AutonomyDecisionStatus.DENY,
                    key_digest=self.key_digest(key),
                    ledger_status="emergency_stopped",
                    reason_codes=("EMERGENCY_STOP_ENGAGED",),
                    profile_enabled=False,
                )
        profile_enabled = self.enabled if enabled is None else bool(enabled)
        if self.profile_name == "production" and not self.production_gate_open:
            profile_enabled = False
        digest = self.key_digest(key)
        if key.action_type in self._FORBIDDEN_ACTIONS:
            return AutonomyDecision(
                status=AutonomyDecisionStatus.DENY,
                key_digest=digest,
                ledger_status="forbidden",
                reason_codes=("ACTION_CLASS_NOT_EARNABLE",),
                profile_enabled=profile_enabled,
            )
        if key.data_classification.upper() in self._FORBIDDEN_CLASSIFICATIONS:
            return AutonomyDecision(
                status=AutonomyDecisionStatus.DENY,
                key_digest=digest,
                ledger_status="forbidden",
                reason_codes=("DATA_CLASS_NOT_EARNABLE",),
                profile_enabled=profile_enabled,
            )
        if self.profile_name == "production" and not profile_enabled:
            return self._requires_capability(digest, "AUTONOMY_DISABLED")
        signature = self._ledger_signature(key)
        row = self.ledger.record_for_scoped(signature)
        if not profile_enabled:
            return self._requires_capability(digest, "AUTONOMY_DISABLED")
        if not self.ledger.is_earned_scoped(signature, enabled=True):
            return AutonomyDecision(
                status=AutonomyDecisionStatus.REQUIRE_CAPABILITY,
                key_digest=digest,
                ledger_status=str((row or {}).get("status", "unearned")),
                reason_codes=("EVIDENCE_STREAK_REQUIRED",),
                profile_enabled=True,
            )
        return AutonomyDecision(
            status=AutonomyDecisionStatus.ALLOW_AUTONOMOUS,
            key_digest=digest,
            ledger_status="earned",
            reason_codes=("VERIFIED_PATTERN_REUSED",),
            profile_enabled=True,
        )

    def record_outcome(
        self,
        key: ActionClassKey,
        outcome: AutonomyOutcome,
    ) -> dict[str, Any]:
        """Record verifier-backed reuse; any anomaly is a failure and decay."""
        success = (
            outcome.passed
            and outcome.reversible
            and not outcome.scope_violation
            and not outcome.hidden_network
            and not outcome.secret_access
            and not outcome.audit_anomaly
        )
        return self.ledger.record_scoped_outcome(
            self._ledger_signature(key),
            action_type=key.action_type,
            target_shape=self._target_shape(key),
            success=success,
            strength=outcome.strength,
        )

    def revoke(self, key: ActionClassKey) -> bool:
        return self.ledger.revoke_scoped(self._ledger_signature(key))

    def propose_cerebellum(
        self,
        goal: str,
        key: ActionClassKey,
        *,
        cerebellum: Any,
    ) -> CerebellumProposal | None:
        """Use Cerebellum only as a fast proposal source."""
        playbook = cerebellum.match(goal)
        if playbook is None:
            return None
        return CerebellumProposal(
            playbook_id=int(playbook.id),
            goal_pattern=str(playbook.goal_pattern),
            key_digest=self.key_digest(key),
            metadata={"source": "cerebellum", "status": str(playbook.status)},
        )

    def _ledger_signature(self, key: ActionClassKey) -> str:
        return self.ledger.scoped_signature(
            key.action_type,
            key.target,
            project_id=key.project_id,
            tool=key.tool,
            path_class=key.path_class,
            verification_plan_digest=key.verification_plan_digest,
            policy_version=key.policy_version,
            model_id=key.model_id,
            data_classification=key.data_classification,
        )

    @staticmethod
    def _target_shape(key: ActionClassKey) -> str:
        safe_target = scan_and_redact(key.target).scrubbed
        return f"{key.project_id}:{key.path_class}:{key.tool}:{safe_target}"

    @staticmethod
    def _requires_capability(digest: str, reason: str) -> AutonomyDecision:
        return AutonomyDecision(
            status=AutonomyDecisionStatus.REQUIRE_CAPABILITY,
            key_digest=digest,
            ledger_status="disabled",
            reason_codes=(reason,),
            profile_enabled=False,
        )


__all__ = ["GovernedAutonomy"]
