"""Immutable action request envelope -- the single input to the Policy Kernel."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from aios.domain.capabilities.digest import payload_digest as _payload_digest
from aios.domain.capabilities.digest import resource_digest as _resource_digest


class ActionType(str, Enum):
    """Canonical action categories recognised by the deterministic policy kernel.

    The enum values are stable strings so they can be persisted in audit logs
    and approval stores without coupling to Python symbol names.
    """

    COMMAND = "command"
    APPROVAL_RESOLUTION = "approval_resolution"
    ROLLBACK = "rollback"
    EDIT = "edit"
    CREATE = "create"
    DELETE = "delete"
    PROPOSAL_APPLY = "proposal_apply"
    PROPOSAL_REJECT = "proposal_reject"
    PLAN = "plan"
    REFLECT = "reflect"
    CHAT = "chat"
    HUMAN_STATE_CORRECT = "human_state_correct"
    GENERATE = "generate"
    TERMINAL = "terminal"
    MEMORY_SEARCH = "memory_search"
    MEMORY_CONSOLIDATE = "memory_consolidate"
    KNOWLEDGE_INGEST = "knowledge_ingest"
    KNOWLEDGE_DELETE = "knowledge_delete"
    FACT_PROPOSE = "fact_propose"
    FACT_RECONCILE = "fact_reconcile"
    FACT_APPROVE = "fact_approve"
    FACT_REJECT = "fact_reject"
    CONVERSATION_START = "conversation_start"
    CONVERSATION_CORRECT = "conversation_correct"
    CONVERSATION_CLEAR = "conversation_clear"
    ALIGNMENT_FEEDBACK = "alignment_feedback"
    POLICY_PROPOSE = "policy_propose"
    POLICY_VOTE = "policy_vote"
    POLICY_ENACT = "policy_enact"
    POLICY_SUSPEND = "policy_suspend"
    COUNCIL_MISSION = "council_mission"
    COUNCIL_MISSION_ROLLBACK = "council_mission_rollback"
    COUNCIL_APPROVE = "council_approve"
    COUNCIL_REJECT = "council_reject"
    COUNCIL_SERVICE_START = "council_service_start"
    COUNCIL_SERVICE_STOP = "council_service_stop"
    PHEROMONE_DEPOSIT = "pheromone_deposit"
    PHEROMONE_REINFORCE = "pheromone_reinforce"
    PHEROMONE_DECAY = "pheromone_decay"
    RUNTIME_SURFACE_EMIT = "runtime_surface_emit"
    RUNTIME_SURFACE_REVOKE = "runtime_surface_revoke"
    RUNTIME_SURFACE_SWEEP = "runtime_surface_sweep"
    RUNTIME_ROLLBACK_REGISTER = "runtime_rollback_register"
    RUNTIME_ROLLBACK_PRUNE = "runtime_rollback_prune"
    HIBERNATION_RUN = "hibernation_run"
    AUDIT_ANCHOR_VERIFY = "audit_anchor_verify"
    V10_VULTURE_SCAN = "v10_vulture_scan"
    V10_ECOSYSTEM_SCAN = "v10_ecosystem_scan"
    VOICE_TRANSCRIBE = "voice_transcribe"
    VOICE_SPEAK = "voice_speak"
    FILES_READ = "files_read"
    FILES_EDIT = "files_edit"
    SECURITY_CLASSIFY = "security_classify"
    SECURITY_TOKENS_ROTATE = "security_tokens_rotate"
    SECURITY_API_TOKEN_ROTATE = "security_api_token_rotate"
    SECURITY_SANDBOX_CLEAR = "security_sandbox_clear"
    SYSTEM_CONFIG = "system_config"
    SYSTEM_RESTART = "system_restart"
    AUTH_SESSION_CREATE = "auth_session_create"
    AUTH_SESSION_DESTROY = "auth_session_destroy"
    AUTH_OPERATOR_ENROLL = "auth_operator_enroll"
    AUTH_OPERATOR_LOGIN = "auth_operator_login"
    AUTH_OPERATOR_REAUTH = "auth_operator_reauth"
    EMERGENCY_STOP_ENGAGE = "emergency_stop_engage"
    EMERGENCY_STOP_CLEAR = "emergency_stop_clear"
    INTENT_PREVIEW = "intent_preview"
    PROJECT_PASSPORT_SCAN = "project_passport_scan"
    PROJECT_SCOPE_HINTS = "project_scope_hints"
    PREFERENCE_SAVE = "preference_save"
    PREFERENCE_WITHDRAW = "preference_withdraw"
    DEVELOPMENT_AUTONOMY_REVOKE = "development_autonomy_revoke"
    DEVELOPMENT_CURRICULUM = "development_curriculum"
    DEVELOPMENT_CURRICULUM_ACCEPT = "development_curriculum_accept"
    EXECUTION_DEBUGGER_STEP = "execution_debugger_step"
    EXECUTION_DEBUGGER_RESUME = "execution_debugger_resume"
    MEMORY_COMPACT = "memory_compact"
    LOCAL_WORKFORCE_REFRESH = "local_workforce_refresh"
    LOCAL_WORKFORCE_APPROVE = "local_workforce_approve"
    LOCAL_WORKFORCE_QUALIFY = "local_workforce_qualify"
    LOCAL_WORKFORCE_HEALTH_CHECK = "local_workforce_health_check"
    LOCAL_WORKFORCE_PROFILES = "local_workforce_profiles"
    INTELLIGENCE_HIRING = "intelligence_hiring"
    SKILL_REUSE = "skill_reuse"
    SKILL_ACTIVATION = "skill_activation"
    MAINTENANCE_SCAN = "maintenance_scan"
    MAINTENANCE_REPAIR_CREATE = "maintenance_repair_create"
    MAINTENANCE_REPAIR_APPROVE = "maintenance_repair_approve"
    MAINTENANCE_REPAIR_RUN = "maintenance_repair_run"
    CONSTITUTIONAL_AMENDMENT_PROPOSE = "constitutional_amendment_propose"
    CONSTITUTIONAL_AMENDMENT_CRITIQUE = "constitutional_amendment_critique"
    CONSTITUTIONAL_AMENDMENT_SIMULATE = "constitutional_amendment_simulate"
    #: Must stay literally equal to `aios.domain.governance.amendments.
    #: CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION` -- `ratify_amendment()` checks
    #: a consumed capability's `action_type` against that domain constant
    #: directly, never this enum, so the two values must never drift apart.
    CONSTITUTIONAL_AMENDMENT_RATIFY = "constitutional_amendment_ratify"
    CONSTITUTIONAL_AMENDMENT_REJECT = "constitutional_amendment_reject"
    CONSTITUTIONAL_AMENDMENT_ACTIVATE = "constitutional_amendment_activate"
    CONSTITUTIONAL_AMENDMENT_ROLLBACK = "constitutional_amendment_rollback"
    CONSTITUTIONAL_LESSON_PROPOSE = "constitutional_lesson_propose"
    CONSTITUTIONAL_LESSON_DRAFT_AMENDMENT = "constitutional_lesson_draft_amendment"
    CONSTITUTIONAL_LESSON_CHECK_SIMULATIONS = "constitutional_lesson_check_simulations"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Principal:
    """Identity context for an action request."""

    session_id: Optional[str] = None
    actor_source: str = "session"  # e.g. "session", "server-session", "public"
    client_ip: str = "127.0.0.1"


@dataclass(frozen=True)
class ActionEnvelope:
    """Immutable request to perform one mutating action.

    This is the single object the deterministic policy kernel consumes.
    Nothing in the envelope is secret; payloads that contain credentials must
    be redacted before the envelope is constructed.
    """

    route: str
    action_type: ActionType
    http_method: str = "POST"
    payload: dict[str, Any] = field(default_factory=dict)
    principal: Principal = field(default_factory=Principal)
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # R4: the complete immutable authority binding.  These fields are optional
    # only for legacy domain callers; production request builders must provide
    # the authenticated identity and policy context explicitly.
    operator_id: Optional[str] = None
    device_id: Optional[str] = None
    authentication_event_id: Optional[str] = None
    mission_id: Optional[str] = None
    contract_digest: Optional[str] = None
    constitution_digest: Optional[str] = None
    resource: Any = field(default_factory=dict)
    resource_digest: Optional[str] = None
    payload_digest: Optional[str] = None
    policy_version: str = "v1"
    data_classification: str = "PROJECT_INTERNAL"
    requested_capability: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        """Normalize and validate the exact action binding at construction."""
        if not self.route.strip():
            raise ValueError("route must be non-empty")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be an object")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if not self.data_classification.strip():
            raise ValueError("data_classification must be non-empty")
        for name in (
            "operator_id",
            "device_id",
            "authentication_event_id",
            "mission_id",
            "contract_digest",
            "constitution_digest",
            "requested_capability",
        ):
            value = getattr(self, name)
            if value is not None and not str(value).strip():
                raise ValueError(f"{name} must be non-empty when provided")

        object.__setattr__(self, "http_method", self.http_method.upper())
        computed_payload_digest = _payload_digest(self.payload)
        if (
            self.payload_digest is not None
            and self.payload_digest != computed_payload_digest
        ):
            raise ValueError("payload_digest does not match payload")
        object.__setattr__(self, "payload_digest", computed_payload_digest)

        computed_resource_digest = _resource_digest(self.resource)
        if (
            self.resource_digest is not None
            and self.resource_digest != computed_resource_digest
        ):
            raise ValueError("resource_digest does not match resource")
        object.__setattr__(self, "resource_digest", computed_resource_digest)

        if not self.correlation_id.strip():
            raise ValueError("correlation_id must be non-empty")

    @property
    def session_id(self) -> Optional[str]:
        return self.principal.session_id
