"""Policy Kernel -- single authority facade for request, action, and feature policy."""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from aios import config
from aios.core import router
from aios.core.autonomy import AutonomyLedger
from aios.domain.actions.envelope import ActionEnvelope, ActionType
from aios.domain.policy.decision import PolicyDecision
from aios.interfaces.http import edge_security
from aios.policy.constitution import Constitution, build_constitution
from aios.runtime import profiles
from aios.security.gateway import (
    GatewayDecision,
    RateLimiter,
    Zone,
    classify,
    validate_command,
)


@dataclass(frozen=True)
class RouteAuthority:
    authority_class: str
    rate_limit_per_minute: int
    actor_source: str
    confirm_required: bool = False
    audit_event: str = ""
    body_limit_bytes: int | None = None
    action_type: ActionType = ActionType.UNKNOWN
    capability_required: Optional[str] = None
    policy_version: str = "v1"


@dataclass(frozen=True)
class AuthorityDecision:
    allowed: bool = False
    blocked: bool = False
    requires_approval: bool = False
    zone: Zone = Zone.RED
    reason: str = ""
    command: str = ""


@dataclass(frozen=True)
class ExecutionPolicy:
    """Container-vs-host execution decision produced by the policy kernel."""

    backend: str
    isolated: bool
    reason: str


_ROUTE_AUTHORITY: dict[str, RouteAuthority] = {
    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    "/api/v1/reflect": RouteAuthority(
        "GREEN", 120, "session", audit_event="reflect", action_type=ActionType.REFLECT
    ),
    "/api/v1/plan": RouteAuthority(
        "GREEN", 120, "session", audit_event="plan", action_type=ActionType.PLAN
    ),
    "/api/v1/execute": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="approved_execute",
        action_type=ActionType.COMMAND,
    ),
    "/api/v1/approval/req": RouteAuthority(
        "YELLOW",
        10,
        "session",
        audit_event="approval_decision",
        action_type=ActionType.APPROVAL_RESOLUTION,
    ),
    "/api/v1/rollback": RouteAuthority(
        "YELLOW", 10, "session", audit_event="rollback", action_type=ActionType.ROLLBACK
    ),
    "/api/v1/self-analysis/proposals/{proposal_id}/apply": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="proposal_apply",
        action_type=ActionType.PROPOSAL_APPLY,
    ),
    "/api/v1/self-analysis/proposals/{proposal_id}/reject": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="proposal_reject",
        action_type=ActionType.PROPOSAL_REJECT,
    ),
    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #
    "/api/v1/auth/session": RouteAuthority(
        "GREEN",
        60,
        "public",
        audit_event="auth_session",
        action_type=ActionType.AUTH_SESSION_CREATE,
    ),
    "/api/v1/auth/enroll": RouteAuthority(
        # Bootstrap is already one-time and identity-gated inside the
        # enrollment service; no existing Human Sovereign exists yet from
        # which an exact capability could be issued.
        "GREEN",
        3,
        "public",
        audit_event="auth_operator_enroll",
        action_type=ActionType.AUTH_OPERATOR_ENROLL,
    ),
    "/api/v1/auth/login": RouteAuthority(
        "GREEN",
        10,
        "public",
        audit_event="auth_operator_login",
        action_type=ActionType.AUTH_OPERATOR_LOGIN,
    ),
    "/api/v1/auth/reauth": RouteAuthority(
        # The credential itself is the authentication proof and the handler
        # rotates the session; requiring a pre-existing capability here would
        # make the privileged authentication bootstrap circular.
        "GREEN",
        10,
        "session",
        audit_event="auth_operator_reauth",
        action_type=ActionType.AUTH_OPERATOR_REAUTH,
    ),
    "/api/v1/governance/emergency-stop/engage": RouteAuthority(
        "YELLOW",
        5,
        "server-session",
        audit_event="emergency_stop_engage",
        action_type=ActionType.EMERGENCY_STOP_ENGAGE,
        capability_required="emergency_stop.engage",
    ),
    "/api/v1/governance/emergency-stop/clear": RouteAuthority(
        "YELLOW",
        5,
        "server-session",
        audit_event="emergency_stop_clear",
        action_type=ActionType.EMERGENCY_STOP_CLEAR,
        capability_required="emergency_stop.clear",
    ),
    # ------------------------------------------------------------------ #
    # Council
    # ------------------------------------------------------------------ #
    "/api/v1/council/missions": RouteAuthority(
        "YELLOW",
        20,
        "session",
        audit_event="council_mission",
        action_type=ActionType.COUNCIL_MISSION,
    ),
    "/api/v1/council/missions/{mission_id}/rollback": RouteAuthority(
        "YELLOW",
        60,
        "session",
        audit_event="council_mission_rollback",
        action_type=ActionType.COUNCIL_MISSION_ROLLBACK,
    ),
    "/api/v1/council/approve": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="council_approve",
        action_type=ActionType.COUNCIL_APPROVE,
    ),
    "/api/v1/council/reject": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="council_reject",
        action_type=ActionType.COUNCIL_REJECT,
    ),
    # ------------------------------------------------------------------ #
    # Local Workforce
    # ------------------------------------------------------------------ #
    "/api/v1/local-workforce/refresh": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="local_workforce_refresh",
        action_type=ActionType.LOCAL_WORKFORCE_REFRESH,
    ),
    "/api/v1/local-workforce/{model_id}/approve": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="local_workforce_approve",
        action_type=ActionType.LOCAL_WORKFORCE_APPROVE,
    ),
    "/api/v1/local-workforce/{model_id}/profiles": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="local_workforce_profiles",
        action_type=ActionType.LOCAL_WORKFORCE_PROFILES,
    ),
    "/api/v1/hiring/call": RouteAuthority(
        "YELLOW",
        20,
        "session",
        audit_event="intelligence_hiring",
        action_type=ActionType.INTELLIGENCE_HIRING,
    ),
    "/api/v1/skills/reuse": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="skill_reuse",
        action_type=ActionType.SKILL_REUSE,
    ),
    "/api/v1/skills/{skill_id}/versions/{version}/activate": RouteAuthority(
        "YELLOW",
        10,
        "session",
        audit_event="skill_activate",
        action_type=ActionType.SKILL_ACTIVATION,
    ),
    "/api/v1/maintenance/scans": RouteAuthority(
        "YELLOW",
        20,
        "session",
        audit_event="maintenance_scan",
        action_type=ActionType.MAINTENANCE_SCAN,
    ),
    "/api/v1/maintenance/repairs/missions": RouteAuthority(
        "YELLOW",
        20,
        "session",
        audit_event="maintenance_repair_create",
        action_type=ActionType.MAINTENANCE_REPAIR_CREATE,
    ),
    "/api/v1/maintenance/repairs/run": RouteAuthority(
        "YELLOW",
        20,
        "session",
        audit_event="maintenance_repair_run",
        action_type=ActionType.MAINTENANCE_REPAIR_RUN,
    ),
    "/api/v1/maintenance/repairs/{mission_id}/status": RouteAuthority(
        "GREEN",
        60,
        "session",
        audit_event="maintenance_repair_status",
        action_type=ActionType.PLAN,
    ),
    "/api/v1/local-workforce/{model_id}/qualify": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="local_workforce_qualify",
        action_type=ActionType.LOCAL_WORKFORCE_QUALIFY,
    ),
    "/api/v1/local-workforce/{model_id}/health-check": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="local_workforce_health_check",
        action_type=ActionType.LOCAL_WORKFORCE_HEALTH_CHECK,
    ),
    # ------------------------------------------------------------------ #
    # Execution debugger
    # ------------------------------------------------------------------ #
    "/api/v1/execution/debugger/step": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="execution_debugger_step",
        action_type=ActionType.EXECUTION_DEBUGGER_STEP,
    ),
    "/api/v1/execution/debugger/resume": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="execution_debugger_resume",
        action_type=ActionType.EXECUTION_DEBUGGER_RESUME,
    ),
    # ------------------------------------------------------------------ #
    # Development
    # ------------------------------------------------------------------ #
    "/api/v1/development/autonomy/revoke": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="development_autonomy_revoke",
        action_type=ActionType.DEVELOPMENT_AUTONOMY_REVOKE,
    ),
    "/api/v1/development/curriculum": RouteAuthority(
        "GREEN",
        30,
        "server-session",
        audit_event="development_curriculum",
        action_type=ActionType.DEVELOPMENT_CURRICULUM,
    ),
    "/api/v1/development/curriculum/proposals/accept": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="development_curriculum_accept",
        action_type=ActionType.DEVELOPMENT_CURRICULUM_ACCEPT,
    ),
    # ------------------------------------------------------------------ #
    # Memory
    # ------------------------------------------------------------------ #
    "/api/v1/memory/search": RouteAuthority(
        "GREEN",
        120,
        "session",
        audit_event="memory_search",
        action_type=ActionType.MEMORY_SEARCH,
    ),
    "/api/v1/memory/consolidate": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="memory_consolidate",
        action_type=ActionType.MEMORY_CONSOLIDATE,
    ),
    "/api/v1/conversation/session": RouteAuthority(
        "GREEN",
        120,
        "session",
        audit_event="conversation_start",
        action_type=ActionType.CONVERSATION_START,
    ),
    "/api/v1/conversation/correction": RouteAuthority(
        "GREEN",
        120,
        "session",
        audit_event="conversation_correct",
        action_type=ActionType.CONVERSATION_CORRECT,
    ),
    "/api/v1/alignment/feedback": RouteAuthority(
        "GREEN",
        120,
        "session",
        audit_event="alignment_feedback",
        action_type=ActionType.ALIGNMENT_FEEDBACK,
    ),
    "/api/v1/conversation/correction/clear": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="conversation_clear",
        action_type=ActionType.CONVERSATION_CLEAR,
    ),
    "/api/v1/memory/facts/pending/{proposal_id}/approve": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="fact_approve",
        action_type=ActionType.FACT_APPROVE,
    ),
    "/api/v1/memory/facts/pending/{proposal_id}/reject": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="fact_reject",
        action_type=ActionType.FACT_REJECT,
    ),
    "/api/v1/memory/facts": RouteAuthority(
        "GREEN",
        120,
        "session",
        audit_event="fact_propose",
        action_type=ActionType.FACT_PROPOSE,
    ),
    "/api/v1/memory/facts/reconcile": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="fact_reconcile",
        action_type=ActionType.FACT_RECONCILE,
    ),
    "/api/v1/knowledge/ingest": RouteAuthority(
        "YELLOW",
        30,
        "server-session",
        audit_event="knowledge_ingest",
        action_type=ActionType.KNOWLEDGE_INGEST,
    ),
    "/api/v1/knowledge/sources/{source_id}": RouteAuthority(
        "YELLOW",
        30,
        "server-session",
        audit_event="knowledge_delete",
        action_type=ActionType.KNOWLEDGE_DELETE,
    ),
    # ------------------------------------------------------------------ #
    # Projects
    # ------------------------------------------------------------------ #
    "/api/v1/projects/passport/scan": RouteAuthority(
        "GREEN",
        30,
        "session",
        audit_event="project_passport_scan",
        action_type=ActionType.PROJECT_PASSPORT_SCAN,
    ),
    "/api/v1/projects/scope-hints": RouteAuthority(
        "GREEN",
        60,
        "session",
        audit_event="project_scope_hints",
        action_type=ActionType.PROJECT_SCOPE_HINTS,
    ),
    # ------------------------------------------------------------------ #
    # Security
    # ------------------------------------------------------------------ #
    "/api/v1/security/tokens/rotate": RouteAuthority(
        "YELLOW",
        3,
        "server-session",
        confirm_required=True,
        audit_event="audit_key_rotate",
        action_type=ActionType.SECURITY_TOKENS_ROTATE,
    ),
    "/api/v1/security/sandbox/clear": RouteAuthority(
        "RED",
        10,
        "server-session",
        confirm_required=True,
        audit_event="sandbox_clear",
        action_type=ActionType.SECURITY_SANDBOX_CLEAR,
    ),
    # ------------------------------------------------------------------ #
    # Files
    # ------------------------------------------------------------------ #
    "/api/v1/files/read": RouteAuthority(
        "GREEN",
        120,
        "session",
        audit_event="files_read",
        action_type=ActionType.FILES_READ,
    ),
    "/api/v1/files/edit": RouteAuthority(
        "YELLOW",
        60,
        "session",
        audit_event="files_edit",
        action_type=ActionType.FILES_EDIT,
    ),
    # ------------------------------------------------------------------ #
    # Sovereignty / runtime
    # ------------------------------------------------------------------ #
    "/api/v1/hibernation/run": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="hibernation_run",
        action_type=ActionType.HIBERNATION_RUN,
    ),
    "/api/v1/audit/anchor/verify": RouteAuthority(
        "YELLOW",
        20,
        "server-session",
        audit_event="audit_anchor_verify",
        action_type=ActionType.AUDIT_ANCHOR_VERIFY,
    ),
    "/api/v1/policy/propose": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="policy_propose",
        action_type=ActionType.POLICY_PROPOSE,
    ),
    "/api/v1/pheromones/deposit": RouteAuthority(
        "YELLOW",
        60,
        "server-session",
        audit_event="pheromone_deposit",
        action_type=ActionType.PHEROMONE_DEPOSIT,
    ),
    "/api/v1/pheromones/reinforce": RouteAuthority(
        "YELLOW",
        60,
        "server-session",
        audit_event="pheromone_reinforce",
        action_type=ActionType.PHEROMONE_REINFORCE,
    ),
    "/api/v1/pheromones/decay": RouteAuthority(
        "YELLOW",
        5,
        "server-session",
        audit_event="pheromone_decay",
        action_type=ActionType.PHEROMONE_DECAY,
    ),
    "/api/v1/runtime/surface/emit": RouteAuthority(
        "YELLOW",
        60,
        "server-session",
        audit_event="surface_emit",
        action_type=ActionType.RUNTIME_SURFACE_EMIT,
    ),
    "/api/v1/runtime/surface/{signal_id}": RouteAuthority(
        "YELLOW",
        30,
        "server-session",
        audit_event="surface_revoke",
        action_type=ActionType.RUNTIME_SURFACE_REVOKE,
    ),
    "/api/v1/runtime/surface/sweep": RouteAuthority(
        "YELLOW",
        5,
        "server-session",
        audit_event="surface_sweep",
        action_type=ActionType.RUNTIME_SURFACE_SWEEP,
    ),
    "/api/v1/runtime/rollbacks/register": RouteAuthority(
        "YELLOW",
        30,
        "server-session",
        audit_event="rollback_register",
        action_type=ActionType.RUNTIME_ROLLBACK_REGISTER,
    ),
    "/api/v1/runtime/rollbacks/prune": RouteAuthority(
        "YELLOW",
        5,
        "server-session",
        audit_event="rollback_prune",
        action_type=ActionType.RUNTIME_ROLLBACK_PRUNE,
    ),
    "/api/v1/policy/{policy_id}/vote": RouteAuthority(
        "YELLOW",
        20,
        "server-session",
        audit_event="policy_vote",
        action_type=ActionType.POLICY_VOTE,
    ),
    "/api/v1/policy/{policy_id}/enact": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="policy_enact",
        action_type=ActionType.POLICY_ENACT,
    ),
    "/api/v1/policy/{policy_id}/suspend": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="policy_suspend",
        action_type=ActionType.POLICY_SUSPEND,
    ),
    "/api/v1/council/services/{name}/start": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="council_service_start",
        action_type=ActionType.COUNCIL_SERVICE_START,
    ),
    "/api/v1/council/services/{name}/stop": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="council_service_stop",
        action_type=ActionType.COUNCIL_SERVICE_STOP,
    ),
    # ------------------------------------------------------------------ #
    # System
    # ------------------------------------------------------------------ #
    "/api/v1/intent/preview": RouteAuthority(
        "GREEN",
        120,
        "session",
        audit_event="intent_preview",
        action_type=ActionType.INTENT_PREVIEW,
    ),
    "/api/v1/security/classify": RouteAuthority(
        "GREEN",
        120,
        "session",
        audit_event="security_classify",
        action_type=ActionType.SECURITY_CLASSIFY,
    ),
    "/api/v1/system/config": RouteAuthority(
        "YELLOW",
        10,
        "server-session",
        audit_event="system_config",
        action_type=ActionType.SYSTEM_CONFIG,
    ),
    "/api/v1/system/restart": RouteAuthority(
        "RED",
        3,
        "server-session",
        confirm_required=True,
        audit_event="system_restart",
        action_type=ActionType.SYSTEM_RESTART,
    ),
    # ------------------------------------------------------------------ #
    # V10 sanitation
    # ------------------------------------------------------------------ #
    "/api/v1/v10/vulture/scan": RouteAuthority(
        "YELLOW",
        5,
        "server-session",
        audit_event="v10_vulture_scan",
        body_limit_bytes=128_000,
        action_type=ActionType.V10_VULTURE_SCAN,
    ),
    "/api/v1/v10/ecosystem/scan": RouteAuthority(
        "YELLOW",
        5,
        "server-session",
        audit_event="v10_ecosystem_scan",
        body_limit_bytes=32_000,
        action_type=ActionType.V10_ECOSYSTEM_SCAN,
    ),
    # ------------------------------------------------------------------ #
    # Voice
    # ------------------------------------------------------------------ #
    "/api/v1/voice/transcribe": RouteAuthority(
        "YELLOW",
        30,
        "session",
        audit_event="voice_transcribe",
        action_type=ActionType.VOICE_TRANSCRIBE,
    ),
    "/api/v1/voice/speak": RouteAuthority(
        "YELLOW",
        60,
        "session",
        audit_event="voice_speak",
        action_type=ActionType.VOICE_SPEAK,
    ),
    # ------------------------------------------------------------------ #
    # Main app routes
    # ------------------------------------------------------------------ #
    "/api/v1/chat": RouteAuthority(
        "GREEN", 120, "session", audit_event="chat", action_type=ActionType.CHAT
    ),
    "/api/generate": RouteAuthority(
        "GREEN", 120, "session", audit_event="generate", action_type=ActionType.GENERATE
    ),
    "/api/terminal": RouteAuthority(
        "YELLOW",
        20,
        "session",
        audit_event="terminal_command",
        action_type=ActionType.COMMAND,
    ),
    "/api/v1/memory/compact": RouteAuthority(
        "YELLOW",
        5,
        "server-session",
        audit_event="memory_compact",
        action_type=ActionType.MEMORY_COMPACT,
    ),
}

# A path can expose more than one HTTP mutation.  Keep the path registry as
# the public route metadata surface, but make the method-specific authority
# explicit wherever the same path has different actions.  In particular,
# ``/auth/session`` is session creation on POST and session destruction on
# DELETE; treating DELETE as the POST action would make the envelope lie about
# the mutation it is authorising.
_METHOD_ROUTE_AUTHORITY: dict[tuple[str, str], RouteAuthority] = {
    (
        "DELETE",
        "/api/v1/auth/session",
    ): RouteAuthority(
        "GREEN",
        60,
        "public",
        audit_event="auth_session_destroy",
        action_type=ActionType.AUTH_SESSION_DESTROY,
    ),
    (
        "GET",
        "/api/v1/maintenance/scans",
    ): RouteAuthority(
        "GREEN",
        120,
        "session",
        audit_event="maintenance_scan_list",
        action_type=ActionType.PLAN,
    ),
    (
        "GET",
        "/api/v1/maintenance/findings",
    ): RouteAuthority(
        "GREEN",
        120,
        "session",
        audit_event="maintenance_finding_list",
        action_type=ActionType.PLAN,
    ),
}


def _route_match(route: str, path: str) -> bool:
    route_parts = route.split("/")
    path_parts = path.split("/")
    if len(route_parts) != len(path_parts):
        return False
    for rp, pp in zip(route_parts, path_parts):
        if rp.startswith("{") and rp.endswith("}"):
            continue
        if rp != pp:
            return False
    return True


class PolicyKernel:
    """Runtime authority facade for the AI-OS API."""

    def __init__(
        self,
        *,
        rate_limiter: RateLimiter | None = None,
        autonomy_ledger: AutonomyLedger | None = None,
        constitution: Constitution | None = None,
    ) -> None:
        self.rate_limiter = rate_limiter or RateLimiter()
        self.autonomy = autonomy_ledger or AutonomyLedger()
        self.constitution = constitution or build_constitution()
        self._route_table = _ROUTE_AUTHORITY
        # Unknown routes are never allowed to inherit a permissive policy.
        self._fallback = RouteAuthority(
            "RED",
            0,
            "unknown",
            confirm_required=True,
            audit_event="policy_unknown_route",
            action_type=ActionType.UNKNOWN,
        )
        self._endpoint_hits: dict[str, list[tuple[str, float]]] = {}
        self._endpoint_hits_lock = threading.Lock()
        self._window_s = 60.0
        self._active_profile: Optional[profiles.RuntimeProfile] = None
        self._active_profile_lock = threading.Lock()

    @property
    def route_table(self) -> dict[str, RouteAuthority]:
        return self._route_table

    @property
    def rate_limit_endpoints(self) -> dict[str, int]:
        return {
            path: meta.rate_limit_per_minute for path, meta in self._route_table.items()
        }

    @property
    def endpoint_hits(self) -> dict[str, list[tuple[str, float]]]:
        return self._endpoint_hits

    def route_authority(self, path: str, method: str | None = None) -> RouteAuthority:
        """Return method-aware authority metadata, failing closed when unknown."""
        if method:
            method_authority = _METHOD_ROUTE_AUTHORITY.get((method.upper(), path))
            if method_authority is not None:
                return method_authority
        exact = self._route_table.get(path)
        if exact is not None:
            return exact
        for route, authority in self._route_table.items():
            if _route_match(route, path):
                return authority
        return self._fallback

    def rate_limited_route_path(self, path: str) -> str | None:
        """Return the literal or templated route key used by the rate limiter."""
        if path in self.rate_limit_endpoints:
            return path
        for route_path in self.rate_limit_endpoints:
            if (
                "{" in route_path
                and "}" in route_path
                and _route_match(route_path, path)
            ):
                return route_path
        return None

    def check_api_token_or_loopback(self, request: Request) -> Optional[JSONResponse]:
        """Delegate to the HTTP edge token/origin check."""
        return edge_security.check_api_token_or_loopback(request)

    def check_mutation_origin_or_token(
        self, request: Request
    ) -> Optional[JSONResponse]:
        """Delegate to the HTTP edge CSRF/mutation check."""
        return edge_security.check_mutation_origin_or_token(request)

    def request_authority(self, request: Request) -> dict[str, Any]:
        """Run request-level checks and return an authority summary.

        Raises HTTPException when the edge checks deny the request.
        """
        auth_error = self.check_api_token_or_loopback(request)
        if auth_error is not None:
            body = (
                auth_error.body
                if hasattr(auth_error, "body")
                else {"detail": "unauthorised"}
            )
            raise HTTPException(status_code=auth_error.status_code, detail=body)
        mutation_error = self.check_mutation_origin_or_token(request)
        if mutation_error is not None:
            body = (
                mutation_error.body
                if hasattr(mutation_error, "body")
                else {"detail": "forbidden"}
            )
            raise HTTPException(status_code=mutation_error.status_code, detail=body)
        return {
            "allowed": True,
            "path": request.url.path,
            "authority": self.route_authority(request.url.path),
        }

    def check_endpoint_rate_limit(self, path: str, client_ip: str) -> None:
        """Raise HTTP 429 if *client_ip* exceeds the per-minute cap for *path*."""
        cap = self.rate_limit_endpoints.get(path)
        if cap is None:
            return
        key = f"{path}|{client_ip}"
        now = time.monotonic()
        cutoff = now - self._window_s
        with self._endpoint_hits_lock:
            hits = [t for t in self._endpoint_hits.get(key, []) if t[1] > cutoff]
            if len(hits) >= cap:
                self._endpoint_hits[key] = hits
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for {path}. Limit is {cap} per {int(self._window_s)}s.",
                )
            hits.append((key, now))
            self._endpoint_hits[key] = hits

    def evaluate_action(
        self, command: str, *, session_id: Optional[str] = None
    ) -> AuthorityDecision:
        """Evaluate a single command for zone, approval, and earned autonomy."""
        max_chars = max(config.MAX_COMMAND_CHARS, 1)
        if len(command) > max_chars:
            return AuthorityDecision(
                blocked=True,
                zone=Zone.RED,
                reason=f"command exceeds {config.MAX_COMMAND_CHARS} character limit",
                command=command,
            )
        decision = validate_command(
            command, session_id=session_id, rate_limiter=self.rate_limiter
        )
        if decision.status == "BLOCK":
            return AuthorityDecision(
                blocked=True,
                zone=decision.zone,
                reason=decision.reason,
                command=command,
            )
        if decision.status == "REQUIRE_HUMAN":
            if self.autonomy.is_earned(
                "command", command, enabled=self.earned_autonomy_enabled()
            ):
                return AuthorityDecision(
                    allowed=True,
                    zone=decision.zone,
                    reason="earned autonomy",
                    command=command,
                )
            return AuthorityDecision(
                requires_approval=True,
                zone=decision.zone,
                reason=decision.reason,
                command=command,
            )
        return AuthorityDecision(
            allowed=True, zone=decision.zone, reason=decision.reason, command=command
        )

    def evaluate_approved(self, command: str) -> AuthorityDecision:
        """Re-evaluate a human-approved command (RED still blocked)."""
        max_chars = max(config.MAX_COMMAND_CHARS, 1)
        if len(command) > max_chars:
            return AuthorityDecision(
                blocked=True,
                zone=Zone.RED,
                reason=f"Approved command exceeds {config.MAX_COMMAND_CHARS} character limit",
                command=command,
            )
        result = classify(command)
        if result.zone is Zone.RED:
            return AuthorityDecision(
                blocked=True,
                zone=Zone.RED,
                reason=f"Human approval cannot authorise a RED action: {result.reason}",
                command=command,
            )
        return AuthorityDecision(
            allowed=True, zone=result.zone, reason="approved", command=command
        )

    # ------------------------------------------------------------------ #
    # Deterministic ActionEnvelope -> PolicyDecision authority
    # ------------------------------------------------------------------ #
    def decide(
        self, envelope: ActionEnvelope, *, check_rate_limit: bool = True
    ) -> PolicyDecision:
        """Return a deterministic PolicyDecision for an ActionEnvelope.

        Commands are evaluated through the frozen security gateway (via
        ``evaluate_action``); all other action types are evaluated from the
        route registry. Rate limits are enforced before any classification.
        """
        route = envelope.route
        authority = self.route_authority(route, envelope.http_method)
        audit_event = authority.audit_event or "action_evaluated"

        if authority.action_type is ActionType.UNKNOWN:
            return PolicyDecision(
                envelope_id=envelope.action_id,
                route=route,
                blocked=True,
                zone=Zone.RED,
                reason=f"unknown route {route} is blocked by policy",
                audit_event=audit_event,
            )

        if envelope.action_type is not authority.action_type:
            return PolicyDecision(
                envelope_id=envelope.action_id,
                route=route,
                blocked=True,
                zone=Zone.RED,
                reason=(
                    f"route {route} requires action type "
                    f"{authority.action_type.value}, got {envelope.action_type.value}"
                ),
                audit_event="policy_action_type_mismatch",
            )

        if envelope.policy_version != authority.policy_version:
            return PolicyDecision(
                envelope_id=envelope.action_id,
                route=route,
                blocked=True,
                zone=Zone.RED,
                reason=(
                    f"route {route} requires policy version {authority.policy_version}, "
                    f"got {envelope.policy_version}"
                ),
                audit_event="policy_version_mismatch",
            )

        if check_rate_limit:
            try:
                self.check_endpoint_rate_limit(
                    self.rate_limited_route_path(route) or route,
                    envelope.principal.client_ip,
                )
            except HTTPException as exc:
                return PolicyDecision(
                    envelope_id=envelope.action_id,
                    route=route,
                    blocked=True,
                    zone=Zone.RED,
                    reason=f"rate limited: {exc.detail}",
                    audit_event="rate_limit",
                )

        if envelope.action_type is ActionType.COMMAND:
            command = str(envelope.payload.get("command", ""))
            inner = self.evaluate_action(command, session_id=envelope.session_id)
            return PolicyDecision(
                envelope_id=envelope.action_id,
                route=route,
                allowed=inner.allowed,
                blocked=inner.blocked,
                requires_approval=inner.requires_approval,
                zone=inner.zone,
                reason=inner.reason,
                audit_event=audit_event,
            )

        if authority.authority_class == "RED":
            return PolicyDecision(
                envelope_id=envelope.action_id,
                route=route,
                blocked=True,
                zone=Zone.RED,
                reason=f"route {route} is classified RED by policy",
                audit_event=audit_event,
            )

        if authority.authority_class == "YELLOW":
            return PolicyDecision(
                envelope_id=envelope.action_id,
                route=route,
                requires_approval=True,
                zone=Zone.YELLOW,
                reason=f"route {route} requires human approval",
                audit_event=audit_event,
            )

        return PolicyDecision(
            envelope_id=envelope.action_id,
            route=route,
            allowed=True,
            zone=Zone.GREEN,
            reason=f"route {route} is GREEN",
            audit_event=audit_event,
        )

    def reset_sensitive_actions(self, session_id: Optional[str]) -> None:
        """Reset a session's sensitive-action budget after human re-authorisation."""
        from aios.security.gateway import reset_sensitive_actions as _reset

        _reset(session_id, self.rate_limiter)

    def feature_enabled(self, name: str) -> bool:
        """Return a feature flag value from config."""
        return bool(getattr(config, f"{name.upper()}_ENABLED", False))

    def constitution_snapshot(self) -> Constitution:
        """Return the current constitutional snapshot."""
        return self.constitution

    # ------------------------------------------------------------------ #
    # Runtime profile authority
    # ------------------------------------------------------------------ #
    def active_runtime_profile(self) -> profiles.RuntimeProfile:
        """Return the active runtime profile, resolving env var and persisted state.

        The active profile is cached on the kernel. Unknown names fall back to
        the built-in ``local-first`` profile so the process never starts without
        a valid operating mode.
        """
        if self._active_profile is not None:
            return self._active_profile
        with self._active_profile_lock:
            if self._active_profile is not None:
                return self._active_profile
            env_name = (
                os.environ.get("AIOS_RUNTIME_PROFILE", profiles.default_profile_name())
                .strip()
                .lower()
            )
            persisted = profiles.load_active_profile_name()
            name = persisted or env_name
            profile = profiles.get_profile(name)
            if profile is None:
                profile = profiles.get_profile(profiles.default_profile_name())
            if profile is None and profiles.RUNTIME_PROFILES:
                profile = next(iter(profiles.RUNTIME_PROFILES.values()))
            self._active_profile = profile
            return self._active_profile

    def load_runtime_profile(self, name: str) -> profiles.RuntimeProfile:
        """Look up a built-in runtime profile by name.

        Raises ``ValueError`` if the profile is unknown.
        """
        profile = profiles.get_profile(name)
        if profile is None:
            raise ValueError(f"Unknown runtime profile: {name!r}")
        return profile

    def list_runtime_profiles(self) -> list[str]:
        """Return the names of all built-in runtime profiles."""
        return profiles.list_profile_names()

    def save_runtime_profile(self, profile: profiles.RuntimeProfile) -> None:
        """Persist *profile* as the active profile and invalidate the cache."""
        profiles.save_active_profile(profile)
        with self._active_profile_lock:
            self._active_profile = profile

    def cloud_tasks_allowed(self, task: str) -> bool:
        """Return True if *task* may be routed to a cloud provider."""
        return self.active_runtime_profile().cloud_task_allowed(task)

    def earned_autonomy_enabled(self) -> bool:
        """Return whether earned autonomy is enabled in the active profile."""
        return self.active_runtime_profile().earned_autonomy

    def execution_backend(self) -> str:
        """Return the execution backend configured by the active profile."""
        return self.active_runtime_profile().execution_backend

    def offline_mode(self) -> bool:
        """Return whether the active profile forces offline operation."""
        return self.active_runtime_profile().offline_mode

    def router_policy(self) -> router.Policy:
        """Build the cross-provider routing policy from the active profile."""
        profile = self.active_runtime_profile()
        return router.Policy(
            cloud_tasks=frozenset(profile.router_cloud_tasks),
            max_cost=profile.router_max_cost,
            prefer_local=profile.router_prefer_local,
        )

    def runtime_profile_decisions(self) -> dict[str, Any]:
        """Return a read-only summary of the active profile and resolved decisions."""
        profile = self.active_runtime_profile()
        return {
            "name": profile.name,
            "description": profile.description,
            "execution_backend": profile.execution_backend,
            "earned_autonomy": profile.earned_autonomy,
            "router_cloud_tasks": list(profile.router_cloud_tasks),
            "router_prefer_local": profile.router_prefer_local,
            "router_max_cost": profile.router_max_cost,
            "swarm_cloud_burst": profile.swarm_cloud_burst,
            "offline_mode": profile.offline_mode,
            "resource_mode": profile.resource_mode,
            "plan_stage": profile.plan_stage,
            "narrative_self": profile.narrative_self,
            "facts_auto_extract": profile.facts_auto_extract,
            "pheromone_enabled": profile.pheromone_enabled,
            "queen_enabled": profile.queen_enabled,
            "live_surface": profile.live_surface,
            "cloud_tasks_allowed": {
                task: profile.cloud_task_allowed(task)
                for task in ("reasoning", "coding", "browse", "swarm")
            },
        }

    def execution_policy(self, approved: bool) -> ExecutionPolicy:
        """Return the execution backend and isolation level for an action.

        GREEN (non-approved) actions always run in the host scope. Approved
        actions follow ``AIOS_APPROVED_EXECUTION_BACKEND``; an unsupported
        backend is reported as non-isolated and fail-closed at runtime.
        """
        backend = config.APPROVED_EXECUTION_BACKEND
        if not approved:
            return ExecutionPolicy(
                backend="host",
                isolated=False,
                reason="GREEN action runs in the configured host scope.",
            )
        if backend == "container":
            return ExecutionPolicy(
                backend="container",
                isolated=True,
                reason="Approved action runs in an isolated container.",
            )
        if backend == "host":
            return ExecutionPolicy(
                backend="host",
                isolated=False,
                reason="Approved action runs on the host (development only).",
            )
        # Treat an unsupported backend as fail-closed: the runner built for it
        # is ``UnavailableIsolationRunner``, so mark it isolated so the executor
        # dispatches through that runner and surfaces an ERROR instead of the
        # host runner.
        return ExecutionPolicy(
            backend=backend,
            isolated=True,
            reason=f"Unsupported execution backend '{backend}'; approved execution will fail closed.",
        )

    def build_approved_runner(self) -> Optional[Any]:
        """Build the configured runner for human-approved arbitrary commands.

        Production and demo profiles cross the private Executor Service.  The
        legacy local Docker/host adapter remains available only to development
        and test profiles; it is never constructed by a production control
        plane.
        """
        profile = os.environ.get("AIOS_PROFILE", "development").strip().lower()
        if profile in {"production", "demo"}:
            from aios.application.executor.service import (
                private_executor_runner_from_config,
            )

            return private_executor_runner_from_config()
        from aios.core.executor import approved_runner_from_config

        return approved_runner_from_config()

    def validate_execution_backend(self) -> Optional[str]:
        """Validate the configured execution backend at startup.

        Returns a warning string (host mode / unavailable container) or ``None``
        when the container backend is ready. Raises for an unknown backend.
        """
        profile = os.environ.get("AIOS_PROFILE", "development").strip().lower()
        if profile in {"production", "demo"}:
            if not config.EXECUTOR_URL or not config.EXECUTOR_TOKEN:
                return (
                    "private Executor Service is not configured; approved and "
                    "worker execution will FAIL CLOSED"
                )
            return None
        from aios.core.executor import validate_approved_execution_backend

        return validate_approved_execution_backend()


_KERNEL: Optional[PolicyKernel] = None
_KERNEL_LOCK = threading.Lock()


def get_policy_kernel(
    rate_limiter: RateLimiter | None = None,
    autonomy_ledger: AutonomyLedger | None = None,
    constitution: Constitution | None = None,
) -> PolicyKernel:
    """Return the process-wide ``PolicyKernel`` singleton.

    The first caller sets the concrete dependencies; subsequent callers receive
    the same instance. The default rate limiter is multi-process safe via the
    shared approvals database path.
    """
    global _KERNEL
    if _KERNEL is None:
        with _KERNEL_LOCK:
            if _KERNEL is None:
                _KERNEL = PolicyKernel(
                    rate_limiter=rate_limiter
                    or RateLimiter(db_path=config.APPROVAL_DB_PATH),
                    autonomy_ledger=autonomy_ledger or AutonomyLedger(),
                    constitution=constitution,
                )
    return _KERNEL


__all__ = [
    "AuthorityDecision",
    "ExecutionPolicy",
    "PolicyKernel",
    "RouteAuthority",
    "get_policy_kernel",
]
