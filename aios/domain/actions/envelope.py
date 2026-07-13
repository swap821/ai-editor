"""Immutable action request envelope -- the single input to the Policy Kernel."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


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
    SECURITY_SANDBOX_CLEAR = "security_sandbox_clear"
    SYSTEM_CONFIG = "system_config"
    SYSTEM_RESTART = "system_restart"
    AUTH_SESSION_CREATE = "auth_session_create"
    AUTH_SESSION_DESTROY = "auth_session_destroy"
    INTENT_PREVIEW = "intent_preview"
    PROJECT_PASSPORT_SCAN = "project_passport_scan"
    PROJECT_SCOPE_HINTS = "project_scope_hints"
    DEVELOPMENT_AUTONOMY_REVOKE = "development_autonomy_revoke"
    DEVELOPMENT_CURRICULUM = "development_curriculum"
    DEVELOPMENT_CURRICULUM_ACCEPT = "development_curriculum_accept"
    EXECUTION_DEBUGGER_STEP = "execution_debugger_step"
    EXECUTION_DEBUGGER_RESUME = "execution_debugger_resume"
    MEMORY_COMPACT = "memory_compact"
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

    @property
    def session_id(self) -> Optional[str]:
        return self.principal.session_id
