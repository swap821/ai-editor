"""Policy Kernel -- single authority facade for request, action, and feature policy."""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from aios import config
from aios.core.autonomy import AutonomyLedger
from aios.interfaces.http import edge_security
from aios.policy.constitution import Constitution, build_constitution
from aios.security.gateway import GatewayDecision, RateLimiter, Zone, classify, validate_command


@dataclass(frozen=True)
class RouteAuthority:
    authority_class: str
    rate_limit_per_minute: int
    actor_source: str
    confirm_required: bool = False
    audit_event: str = ""
    body_limit_bytes: int | None = None


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
    "/api/v1/approval/req": RouteAuthority("YELLOW", 10, "session", audit_event="approval_decision"),
    "/api/v1/execute": RouteAuthority("YELLOW", 30, "session", audit_event="approved_execute"),
    "/api/terminal": RouteAuthority("YELLOW", 20, "session", audit_event="terminal_command"),
    "/api/v1/council/missions": RouteAuthority("YELLOW", 20, "session", audit_event="council_mission"),
    "/api/v1/council/approve": RouteAuthority("YELLOW", 30, "session", audit_event="council_approve"),
    "/api/v1/council/reject": RouteAuthority("YELLOW", 30, "session", audit_event="council_reject"),
    "/api/v1/voice/transcribe": RouteAuthority("YELLOW", 30, "session", audit_event="voice_transcribe"),
    "/api/v1/voice/speak": RouteAuthority("YELLOW", 60, "session", audit_event="voice_speak"),
    "/api/v1/policy/propose": RouteAuthority("YELLOW", 10, "server-session", audit_event="policy_propose"),
    "/api/v1/policy/{policy_id}/vote": RouteAuthority("YELLOW", 20, "server-session", audit_event="policy_vote"),
    "/api/v1/policy/{policy_id}/enact": RouteAuthority("YELLOW", 10, "server-session", audit_event="policy_enact"),
    "/api/v1/policy/{policy_id}/suspend": RouteAuthority("YELLOW", 10, "server-session", audit_event="policy_suspend"),
    "/api/v1/audit/anchor/verify": RouteAuthority("YELLOW", 20, "server-session", audit_event="audit_anchor_verify"),
    "/api/v1/pheromones/deposit": RouteAuthority("YELLOW", 60, "server-session", audit_event="pheromone_deposit"),
    "/api/v1/pheromones/reinforce": RouteAuthority("YELLOW", 60, "server-session", audit_event="pheromone_reinforce"),
    "/api/v1/pheromones/decay": RouteAuthority("YELLOW", 5, "server-session", audit_event="pheromone_decay"),
    "/api/v1/runtime/surface/emit": RouteAuthority("YELLOW", 60, "server-session", audit_event="surface_emit"),
    "/api/v1/runtime/surface/{signal_id}": RouteAuthority("YELLOW", 30, "server-session", audit_event="surface_revoke"),
    "/api/v1/runtime/surface/sweep": RouteAuthority("YELLOW", 5, "server-session", audit_event="surface_sweep"),
    "/api/v1/runtime/rollbacks/register": RouteAuthority("YELLOW", 30, "server-session", audit_event="rollback_register"),
    "/api/v1/runtime/rollbacks/prune": RouteAuthority("YELLOW", 5, "server-session", audit_event="rollback_prune"),
    "/api/v1/v10/vulture/scan": RouteAuthority(
        "YELLOW", 5, "server-session", audit_event="v10_vulture_scan", body_limit_bytes=128_000
    ),
    "/api/v1/v10/ecosystem/scan": RouteAuthority(
        "YELLOW", 5, "server-session", audit_event="v10_ecosystem_scan", body_limit_bytes=32_000
    ),
    "/api/v1/system/restart": RouteAuthority(
        "RED", 3, "server-session", confirm_required=True, audit_event="system_restart"
    ),
    "/api/v1/security/tokens/rotate": RouteAuthority(
        "YELLOW", 3, "server-session", confirm_required=True, audit_event="audit_key_rotate"
    ),
    "/api/v1/security/sandbox/clear": RouteAuthority(
        "RED", 10, "server-session", confirm_required=True, audit_event="sandbox_clear"
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
        self._fallback = RouteAuthority("GREEN", 120, "public", audit_event="")
        self._endpoint_hits: dict[str, list[tuple[str, float]]] = {}
        self._endpoint_hits_lock = threading.Lock()
        self._window_s = 60.0

    @property
    def route_table(self) -> dict[str, RouteAuthority]:
        return self._route_table

    @property
    def rate_limit_endpoints(self) -> dict[str, int]:
        return {path: meta.rate_limit_per_minute for path, meta in self._route_table.items()}

    @property
    def endpoint_hits(self) -> dict[str, list[tuple[str, float]]]:
        return self._endpoint_hits

    def route_authority(self, path: str) -> RouteAuthority:
        """Return authority metadata for a route path (GREEN default)."""
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
            if "{" in route_path and "}" in route_path and _route_match(route_path, path):
                return route_path
        return None

    def check_api_token_or_loopback(self, request: Request) -> Optional[JSONResponse]:
        """Delegate to the HTTP edge token/origin check."""
        return edge_security.check_api_token_or_loopback(request)

    def check_mutation_origin_or_token(self, request: Request) -> Optional[JSONResponse]:
        """Delegate to the HTTP edge CSRF/mutation check."""
        return edge_security.check_mutation_origin_or_token(request)

    def request_authority(self, request: Request) -> dict[str, Any]:
        """Run request-level checks and return an authority summary.

        Raises HTTPException when the edge checks deny the request.
        """
        auth_error = self.check_api_token_or_loopback(request)
        if auth_error is not None:
            body = auth_error.body if hasattr(auth_error, "body") else {"detail": "unauthorised"}
            raise HTTPException(status_code=auth_error.status_code, detail=body)
        mutation_error = self.check_mutation_origin_or_token(request)
        if mutation_error is not None:
            body = mutation_error.body if hasattr(mutation_error, "body") else {"detail": "forbidden"}
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

    def evaluate_action(self, command: str, *, session_id: Optional[str] = None) -> AuthorityDecision:
        """Evaluate a single command for zone, approval, and earned autonomy."""
        max_chars = max(config.MAX_COMMAND_CHARS, 1)
        if len(command) > max_chars:
            return AuthorityDecision(
                blocked=True,
                zone=Zone.RED,
                reason=f"command exceeds {config.MAX_COMMAND_CHARS} character limit",
                command=command,
            )
        decision = validate_command(command, session_id=session_id, rate_limiter=self.rate_limiter)
        if decision.status == "BLOCK":
            return AuthorityDecision(blocked=True, zone=decision.zone, reason=decision.reason, command=command)
        if decision.status == "REQUIRE_HUMAN":
            if self.autonomy.is_earned("command", command):
                return AuthorityDecision(allowed=True, zone=decision.zone, reason="earned autonomy", command=command)
            return AuthorityDecision(requires_approval=True, zone=decision.zone, reason=decision.reason, command=command)
        return AuthorityDecision(allowed=True, zone=decision.zone, reason=decision.reason, command=command)

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
        return AuthorityDecision(allowed=True, zone=result.zone, reason="approved", command=command)

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

        Imported lazily so the policy kernel does not depend on the execution
        surface at module-load time.
        """
        from aios.core.executor import approved_runner_from_config

        return approved_runner_from_config()

    def validate_execution_backend(self) -> Optional[str]:
        """Validate the configured execution backend at startup.

        Returns a warning string (host mode / unavailable container) or ``None``
        when the container backend is ready. Raises for an unknown backend.
        """
        from aios.core.executor import validate_approved_execution_backend

        return validate_approved_execution_backend()


__all__ = [
    "AuthorityDecision",
    "ExecutionPolicy",
    "PolicyKernel",
    "RouteAuthority",
]
