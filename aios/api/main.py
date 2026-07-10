"""FastAPI orchestration layer for GAGOS.

Exposes the subsystems behind versioned HTTP endpoints. Phase 3a + 3b are live:

    POST /api/v1/memory/search     hybrid BM25+FAISS+decay retrieval
    POST /api/v1/security/classify deterministic, fail-closed zone classifier
    GET  /api/v1/audit/verify      tamper-evident hash-chain verification
    POST /api/v1/reflect           structured failure post-mortem -> Mistake DB
    POST /api/v1/plan              chain-of-thought planner + confidence gate
    POST /api/v1/execute           gateway-guarded, scope-locked execution
    POST /api/v1/approval/req      human approval of an escalated action
    POST /api/v1/rollback          restore the sandbox to a prior snapshot
    GET  /api/v1/alignment/evaluation diagnostic human-alignment evidence
    POST /api/v1/alignment/feedback explicit human label for a visible frame
    POST /api/v1/projects/passport/scan local-only project evidence scan

Collaborators (LLM client, executor, rollback engine) are supplied via
dependency injection so tests can override them with fakes/sandboxes and avoid
any network, model, or host side effects.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional, Any, Sequence, cast

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.routing import Match

import aios
from aios import config
from aios.logging_config import configure_logging, get_logger, session_log_key
from aios.core.metrics import MetricsMiddleware
from aios.agents.reflection_agent import ReflectionAgent
from aios.agents.role_pass import run_role_pass
from aios.agents.swarm import run_swarm
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.agents.tool_agent import ToolAgent
from aios.core.autonomy import AutonomyLedger
from aios.core.cerebellum import Cerebellum
from aios.core.executor import (
    Executor,
    validate_approved_execution_backend,
)
from aios.core.confidence_filter import gate as confidence_gate
from aios.core.planner import Planner, PlannerError, plan_to_prompt_block, serialize_plan
from aios.core.events import event_for_sse
from aios.api.deps import (  # noqa: F401 — re-exported: tests + route modules import these from main
    get_alignment_evaluation_store,
    get_alignment_interpreter,
    get_anthropic_client,
    get_autonomy,
    get_bedrock_client,
    get_cerebellum,
    get_conversation_state_store,
    get_curriculum_manager,
    get_development_tracker,
    get_gemini_client,
    get_llm_client,
    get_memory_consolidator,
    get_mistake_memory,
    get_native_planner,
    get_ollama_client,
    get_openai_client,
    get_reflection_agent,
    get_semantic_facts,
    get_semantic_indexer,
    get_skill_memory,
    get_swarm_pattern_memory,
    get_session_manager,
    get_executor,
    get_approval_store,
    get_rollback_engine,
    get_self_apply_engine,
    get_edit_snapshot,
    _session_id_from_request,
    _APPROVALS,
    _RATE_LIMITER,
    _SESSION_MANAGER,
)
from aios.core import catalog, router, telemetry
from aios.core.bedrock import BedrockClient
from aios.core.gemini import CURATED_MODELS as GEMINI_CURATED_MODELS
from aios.core.gemini import GeminiClient
from aios.core.llm import LLMClient, LLMError, OllamaClient
from aios.core.model_selector import TASK_FAST, infer_task
from aios.core.router_wiring import (
    _AUTO_IDS,
    _active_route,
    _build_providers,
    _client_for,
    _maybe_llm_picker,
    _provider_name,
    _resolve_local_model,
    _route_metrics,
    _router_policy,
    _select_chat_client,
)
from aios.core.approvals import ApprovalError, ApprovalStore
from aios.core.alignment import (
    AlignmentInterpreter,
    apply_user_corrections,
    frame_from_state,
)
from aios.core.native_planner import NativePlanner
from aios.memory.db import get_connection, init_memory_db
from aios.memory.alignment_evaluation import AlignmentEvaluationStore
from aios.memory.compaction import MemoryCompactor
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.conversation import ConversationStateStore
from aios.memory.curriculum import CurriculumManager
from aios.memory.development import DevelopmentTracker
from aios.memory.mistake import MistakeMemory
from aios.memory.relevance import signature as task_signature
from aios.memory.embeddings import VectorIndex
from aios.memory.episodic import EpisodicMemory
from aios.memory.fact_extraction import extract_candidates
from aios.memory.facts import SemanticFacts
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory
from aios.memory.working import WorkingMemory
from aios.runtime.contracts import KingReport, RunLedger
from aios.runtime.cortex_bus import CortexBus
from aios.runtime.cortex_bus_dispatcher import CortexBusDispatcher
from aios.runtime.self_model_handler import SelfModelHandler
from aios.runtime.king_report import KingReportStore
from aios.runtime.run_ledger import RunLedgerStore
from aios.runtime.snapshots import SnapshotManager
from aios.runtime import turn_state
from aios.council import CouncilMissionRequest, CouncilOrchestrator
from aios.council.council_state import CouncilState
from aios.council.queen_verdict import has_blocking_verdict
from aios.core.verification_strength import (
    VerificationStrength,
    meets_promotion_floor,
    strength_from_text,
)
from aios.security.audit_logger import init_audit_db, log_action
from aios.security.gateway import Zone, classify
from aios.security.secret_scanner import scan_and_redact

# Approval/rate-limit/session singletons moved to aios.api.deps (tranche 2).

#: Cloud chat-client singletons. Built lazily and reused across requests so we do
#: not re-run boto3/gcloud credential discovery on every turn. Enablement is still
#: checked per request so setting changes take effect without editing this module.
# Lazy cloud-client singletons moved to aios.api.deps (monolith split).

# ── Cortex bus W2 — singletons (None when CORTEX_BUS is off) ─────────────────
# The bus and its dispatcher are module-level so the lifespan can start/stop
# them and the generate endpoint can append to them without FastAPI Depends.
# Both are None when config.CORTEX_BUS is False (the default) — zero overhead
# on the hot path when the feature is off.
_cortex_bus: Optional[CortexBus] = None
_cortex_dispatcher: Optional[CortexBusDispatcher] = None
_self_model_handler: Optional[SelfModelHandler] = None

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure both databases exist before the app serves traffic."""
    configure_logging()
    logger.info("aios_startup_banner", **config.startup_banner())
    host_is_loopback = config.API_HOST in {"127.0.0.1", "localhost", "::1"}
    if not host_is_loopback or config.TRUST_PROXY_HEADERS:
        if not config.API_TOKEN:
            raise RuntimeError(
                "AIOS_API_TOKEN is required when AIOS_API_HOST is non-loopback "
                "or when AIOS_TRUST_PROXY_HEADERS is enabled"
            )
        if len(config.API_TOKEN) < 32:
            raise RuntimeError("AIOS_API_TOKEN must be at least 32 characters for non-loopback use")
    backend_warning = validate_approved_execution_backend()
    if backend_warning:
        logger.warning("approved_execution_backend", detail=backend_warning)
    init_memory_db()
    init_audit_db()
    # Opt-in second injection layer: install the vector blocklist when enabled.
    # Best-effort — a model/load failure must never block startup, since the
    # regex layer remains the active defence.
    if config.INJECTION_VECTOR_SHIELD:
        try:
            from aios.security.injection_shield import VectorInjectionShield
            from aios.security.gateway import set_injection_shield

            set_injection_shield(VectorInjectionShield())
        except Exception as exc:  # noqa: BLE001 - enhancement; never block startup
            logger.warning(
                "Vector injection shield failed to load; regex layer remains active",
                exc_info=exc,
            )
    # Cortex bus W2: start the drainer ONLY when opted in.  The bus default is
    # OFF (config.CORTEX_BUS=False) — this block is completely skipped in the
    # common case, so behavior is byte-identical to W1 when the flag is unset.
    global _cortex_bus, _cortex_dispatcher, _self_model_handler
    if config.CORTEX_BUS:
        try:
            _cortex_bus = CortexBus()
            # The first observer: the self-model rebuild subscribed BEFORE the
            # dispatcher starts, so no early event dispatches into a void. The
            # per-turn recall path reads this handler's cache (falling back to
            # inline synthesis until the first event lands) — that is what
            # actually takes the synthesis off the hot path.
            _self_model_handler = SelfModelHandler(DevelopmentTracker(), MistakeMemory())
            _cortex_bus.subscribe(_self_model_handler)
            _cortex_dispatcher = _build_cortex_dispatcher(_cortex_bus)
            _cortex_dispatcher.start()
            logger.info("cortex_bus_started")
        except Exception as exc:  # noqa: BLE001 - enhancement; never block startup
            logger.warning("cortex_bus_failed_to_start", exc_info=exc)
            _cortex_bus = None
            _cortex_dispatcher = None
            _self_model_handler = None
    # Boot attestation: hash the security spine and log integrity.
    try:
        from aios.boot_attestation import attest_boot
        attestation = attest_boot(Path(config.PROJECT_ROOT))
        logger.info("boot_attestation", integrity=attestation["integrity"],
                    spine_hash=attestation["hash"][:16])
    except Exception as exc:  # noqa: BLE001 - never block startup
        logger.warning("boot_attestation_failed", exc_info=exc)
    yield
    # Shutdown: stop the dispatcher cleanly if it was started.
    if _cortex_dispatcher is not None:
        try:
            _cortex_dispatcher.stop()
        except Exception:  # noqa: BLE001
            pass
        _cortex_dispatcher = None
        _cortex_bus = None
        _self_model_handler = None


app = FastAPI(
    title="GAGOS",
    version=aios.__version__,
    summary="Local-first, memory-driven, security-gated, human-supervised AI operating system.",
    lifespan=lifespan,
)


# ── Cortex bus W2 helpers ─────────────────────────────────────────────────────

def _build_cortex_dispatcher(bus: CortexBus) -> CortexBusDispatcher:
    """Factory for the dispatcher (isolated so tests can call it directly)."""
    return CortexBusDispatcher(bus, poll_interval=0.25)


def _get_cortex_dispatcher() -> Optional[CortexBusDispatcher]:
    """Return the live dispatcher, or None when the bus is off (default)."""
    return _cortex_dispatcher if config.CORTEX_BUS else None


def _append_turn_completed(
    bus: Optional[CortexBus], session_id: str
) -> None:
    """Best-effort: append a 'turn.completed' OBSERVATION to the cortex bus.

    Called immediately after the 'done' SSE frame is emitted. Carries a
    NON-AUTHORITY payload (observation metadata only — no skill promotion,
    autonomy credit, or approval decision). Silently no-ops when bus is None
    (i.e. when CORTEX_BUS is off) so the common path is completely unaffected.
    """
    if bus is None:
        return
    try:
        bus.append(
            "turn.completed",
            session_id,
            {"ts": datetime.now(timezone.utc).isoformat()},
        )
    except Exception:  # noqa: BLE001 — best-effort; never break a turn
        logger.warning("cortex_bus_append_failed", exc_info=True)

# Browser clients (the Vite front-end) run on a different origin, so the API
# must opt them in explicitly. Origins come from config (env-overridable).
#
# P0 guard: with allow_credentials=True the CORS spec forbids a wildcard origin,
# and a "*" or host-less/malformed entry in AIOS_CORS_ORIGINS would silently
# widen credentialed cross-origin access. Validate at import/startup and FAIL
# CLOSED (refuse to serve) rather than ship a dangerous config. Methods and
# headers are also narrowed from "*" to the surface the front-end actually uses.
def _validate_cors_origins(origins: tuple[str, ...]) -> list[str]:
    """Reject wildcard/host-less origins so credentialed CORS can't widen silently."""
    from urllib.parse import urlparse

    validated: list[str] = []
    for origin in origins:
        if origin == "*":
            raise RuntimeError(
                "AIOS_CORS_ORIGINS may not contain '*' while credentials are "
                "allowed (the CORS spec forbids it; it would widen credentialed "
                "cross-origin access). List explicit scheme://host[:port] origins."
            )
        parsed = urlparse(origin)
        if not parsed.scheme or not parsed.netloc:
            raise RuntimeError(
                f"AIOS_CORS_ORIGINS entry {origin!r} is not a valid origin "
                "(expected scheme://host[:port])."
            )
        validated.append(origin)
    return validated


app.add_middleware(
    CORSMiddleware,
    allow_origins=_validate_cors_origins(config.API_CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(MetricsMiddleware)

# ── Sub-routers extracted from this module ────────────────────────────────────
from aios.api.routes.memory import (  # noqa: E402 — mounted after app + deps exist
    ConversationSessionRequest,  # noqa: F401 — used by the conversation/session route below
    get_doc_ingestor,  # noqa: F401 — re-exported: tests import this from main
    router as _memory_router,
)
from aios.api.routes.development import router as _development_router  # noqa: E402
from aios.api.routes.models import router as _models_router  # noqa: E402
from aios.api.routes.system import router as _system_router  # noqa: E402
from aios.api.routes.auth import router as _auth_router  # noqa: E402
from aios.api.routes.actions import router as _actions_router  # noqa: E402
from aios.api.routes.voice import router as _voice_router
from aios.api.routes.sovereignty import router as _sovereignty_router
from aios.api.routes.council import router as _council_router
from aios.api.routes.projects import router as _projects_router
from aios.api.routes.files import router as _files_router
from aios.api.routes.security import router as _security_router
from aios.api.routes.execution_debugger import router as _execution_debugger_router
from aios.api.routes.v10 import router as _v10_router

app.include_router(_system_router)
app.include_router(_auth_router)
app.include_router(_actions_router)
app.include_router(_memory_router)
app.include_router(_development_router)
app.include_router(_models_router)
app.include_router(_voice_router)
app.include_router(_sovereignty_router)
app.include_router(_council_router)
app.include_router(_projects_router)
app.include_router(_files_router)
app.include_router(_security_router)
app.include_router(_execution_debugger_router)
app.include_router(_v10_router)


@app.middleware("http")
async def bind_request_context(request: Request, call_next):
    """Stamp every request with a correlation id and bind a hashed session id."""
    from structlog.contextvars import bind_contextvars, clear_contextvars

    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    clear_contextvars()
    bind_contextvars(request_id=request_id, method=request.method, path=request.url.path)
    try:
        session_id: Optional[str] = None
        # P0 SECURITY: prefer session from httpOnly cookie (not accessible to JS/XSS)
        # Fall back to body field for clients that haven't migrated yet.
        cookie_hash = request.cookies.get("session_id")
        if cookie_hash:
            manager = get_session_manager()
            session = manager.validate_session(cookie_hash)
            if session is not None:
                # Use the session hash as the log key (raw ID never leaves memory)
                session_id = session.session_hash
        if not session_id and request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = await request.body()
                    payload = json.loads(body.decode("utf-8")) if body else None
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    body_sid = payload.get("sessionId") or payload.get("session_id")
                    if body_sid:
                        session_id = str(body_sid)
        if session_id:
            bind_contextvars(session_id_hash=session_log_key(session_id))
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
    finally:
        clear_contextvars()


#: Hosts that are allowed to call the API without a token. Starlette's
#: "testclient" is deliberately NOT included — it must never be a production
#: backdoor. Tests that need unauthenticated access should use an explicit
#: loopback client address.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
def _is_private_ip(ip: str) -> bool:
    """Return True if *ip* is a loopback, link-local, or RFC 1918/4193 address.

    Uses the standard-library ``ipaddress`` module so IPv4 and IPv6 are both
    handled correctly (e.g. ``::1``, ``fc00::``, ``fe80::``).
    """
    ip = ip.strip()
    if not ip:
        return True  # empty = unsafe, treat as private
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved
    except ValueError:
        # Not a valid IP — could be a Unix socket path or empty string.
        # Fail closed: treat unparseable as private (untrusted).
        return True


def _real_client_ip(request: Request) -> str:
    """Return the best-effort real client IP for auth decisions.

    When TRUST_PROXY_HEADERS is enabled, parse X-Forwarded-For as a
    comma-separated chain and take the **rightmost** non-private IP (the one
    closest to the server that is still a public/resolvable address). If every
    IP in the chain is private, fall back to the direct peer — in that case
    the deployment MUST set AIOS_API_TOKEN because loopback exemption is
    unsafe behind a proxy.

    When TRUST_PROXY_HEADERS is disabled, use the direct peer IP.
    """
    direct = request.client.host if request.client else ""
    if not config.TRUST_PROXY_HEADERS:
        return direct
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return direct
    # X-Forwarded-For is a comma-separated chain: left = original client,
    # right = closest to server. Take the rightmost non-private IP.
    chain = [h.strip() for h in forwarded.split(",") if h.strip()]
    # If TRUSTED_PROXIES is configured, only trust entries from those proxies.
    if config.TRUSTED_PROXIES:
        # Walk from rightmost to leftmost, stop at first IP that is NOT a
        # trusted proxy (that IP made the request through the proxy chain).
        for ip in reversed(chain):
            if ip not in config.TRUSTED_PROXIES:
                return ip
        # Every IP in the chain is a trusted proxy — use direct peer.
        return direct
    # No trusted proxy whitelist: take the rightmost non-private IP.
    for ip in reversed(chain):
        if not _is_private_ip(ip):
            return ip
    # All IPs in the chain are private — possible spoofing attempt.
    return direct


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    """Protect API and schema surfaces; keep unauthenticated use loopback-only.

    When the operator has configured a trusted reverse proxy, the loopback
    exemption is disabled entirely: the direct peer may be the proxy, so only
    a bearer token can authenticate the real client.

    Protected paths:
      * All ``/api/*`` routes
      * ``/docs``, ``/redoc``, ``/openapi.json`` schema/docs surfaces

    ``/health`` remains public for liveness probes. ``/metrics`` is also kept
    outside this token middleware so the existing single-box observability
    contract stays stable; deployments that expose it beyond loopback must
    protect it at the reverse proxy.
    """
    path = request.url.path
    docs_paths = {"/docs", "/redoc", "/openapi.json"}
    if path in docs_paths and not config.ENABLE_DOCS:
        if request.method != "OPTIONS":
            client_ip = _real_client_ip(request)
            if config.TRUST_PROXY_HEADERS or client_ip not in _LOOPBACK_HOSTS:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "unauthenticated API access is loopback-only"},
                )
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    protected = path.startswith("/api/") or path in docs_paths
    if protected and request.method != "OPTIONS":
        if config.API_TOKEN:
            auth = request.headers.get("authorization", "")
            expected = f"Bearer {config.API_TOKEN}"
            if not secrets.compare_digest(auth, expected):
                return JSONResponse(status_code=401, content={"detail": "invalid or missing API token"})
        else:
            # No API token configured — ONLY loopback is permitted, and NEVER
            # when behind a proxy (the peer IP is the proxy, not the client).
            client_ip = _real_client_ip(request)
            if config.TRUST_PROXY_HEADERS or client_ip not in _LOOPBACK_HOSTS:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "unauthenticated API access is loopback-only"},
                )
    return await call_next(request)


# --------------------------------------------------------------------------- #
# In-memory sliding-window rate limiter for sensitive API endpoints.
# Protects against brute-force on approval tokens, noisy control routes, and
# expensive evidence scans. Best-effort, per-process; the durable RateLimiter
# governs RED actions. The route authority map is metadata only here: it
# centralizes API-surface posture without becoming a new security authority.
# --------------------------------------------------------------------------- #
_RATE_LIMIT_WINDOW_S = 60.0


@dataclass(frozen=True)
class RouteAuthority:
    authority_class: str
    rate_limit_per_minute: int
    actor_source: str
    confirm_required: bool = False
    audit_event: str = ""
    body_limit_bytes: int | None = None


_ROUTE_AUTHORITY: dict[str, RouteAuthority] = {
    "/api/v1/approval/req": RouteAuthority("YELLOW", 10, "session", audit_event="approval_decision"),
    "/api/v1/execute": RouteAuthority("YELLOW", 30, "session", audit_event="approved_execute"),
    "/api/terminal": RouteAuthority("YELLOW", 20, "session", audit_event="terminal_command"),
    # Council origination/decisions: IP-keyed cap (the per-session throttle is
    # spoofable by varying sessionId) - bounds mission/worker spawn floods.
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
        "YELLOW",
        5,
        "server-session",
        audit_event="v10_vulture_scan",
        body_limit_bytes=128_000,
    ),
    "/api/v1/v10/ecosystem/scan": RouteAuthority(
        "YELLOW",
        5,
        "server-session",
        audit_event="v10_ecosystem_scan",
        body_limit_bytes=32_000,
    ),
    "/api/v1/system/restart": RouteAuthority(
        "RED",
        3,
        "server-session",
        confirm_required=True,
        audit_event="system_restart",
    ),
    "/api/v1/security/tokens/rotate": RouteAuthority(
        "YELLOW",
        3,
        "server-session",
        confirm_required=True,
        audit_event="audit_key_rotate",
    ),
    "/api/v1/security/sandbox/clear": RouteAuthority(
        "RED",
        10,
        "server-session",
        confirm_required=True,
        audit_event="sandbox_clear",
    ),
}
_RATE_LIMIT_ENDPOINTS: dict[str, int] = {
    path: meta.rate_limit_per_minute for path, meta in _ROUTE_AUTHORITY.items()
}
_RATE_LIMIT_HITS: dict[str, list[tuple[str, float]]] = {}
_RATE_LIMIT_LOCK = threading.Lock()


def _rate_limited_route_path(request: Request) -> str | None:
    """Return the literal or templated route key used by the rate limiter."""
    path = request.url.path
    if path in _RATE_LIMIT_ENDPOINTS:
        return path

    for route in app.router.routes:
        matches = getattr(route, "matches", None)
        if matches is None:
            continue
        match, _child_scope = matches(request.scope)
        if match == Match.FULL:
            route_path = getattr(route, "path", None)
            if route_path in _RATE_LIMIT_ENDPOINTS:
                return route_path
    return None


def _check_endpoint_rate_limit(path: str, client_ip: str) -> None:
    """Raise HTTP 429 if *client_ip* exceeds the per-minute cap for *path*.

    A simple monotonic sliding window keyed by ``path|ip``. Best-effort and
    in-process; intended to slow brute-force on approval tokens and noisy
    execute/terminal endpoints.
    """
    cap = _RATE_LIMIT_ENDPOINTS.get(path)
    if cap is None:
        return
    key = f"{path}|{client_ip}"
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_S
    with _RATE_LIMIT_LOCK:
        hits = [t for t in _RATE_LIMIT_HITS.get(key, []) if t[1] > cutoff]
        if len(hits) >= cap:
            _RATE_LIMIT_HITS[key] = hits
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded for {path}. "
                    f"Limit is {cap} per {int(_RATE_LIMIT_WINDOW_S)}s."
                ),
            )
        hits.append((key, now))
        _RATE_LIMIT_HITS[key] = hits


@app.middleware("http")
async def endpoint_rate_limit(request: Request, call_next):
    """Apply per-endpoint, per-IP rate limits before the request reaches handlers."""
    if request.method != "OPTIONS":
        path = _rate_limited_route_path(request)
        if path is not None:
            # Use the same IP extraction logic as the auth middleware.
            client_ip = _real_client_ip(request)
            try:
                _check_endpoint_rate_limit(path, client_ip)
            except HTTPException:
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Rate limit exceeded for {path}"},
                )
    return await call_next(request)




def get_compactor() -> MemoryCompactor:
    """Provide the audited memory-forgetting service backed by live stores.

    Returns a process-wide singleton so that working-session touch timestamps
    from ``/api/generate`` and ``/api/v1/chat`` survive into later compaction
    requests.
    """
    global _COMPACTOR
    if _COMPACTOR is None:
        with _COMPACTOR_LOCK:
            if _COMPACTOR is None:
                _COMPACTOR = MemoryCompactor(
                    working=_WORKING,
                    semantic=_SEMANTIC,
                    episodic=_EPISODIC,
                    index=_VECTOR_INDEX,
                )
    return _COMPACTOR


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class MemoryCompactRequest(BaseModel):
    """Body for ``/memory/compact``."""

    dry_run: bool = Field(
        True,
        description="When True, preview what would be removed. False performs the sweep.",
    )


class GenerateRequest(BaseModel):
    """Body for ``/api/generate`` — the conversational chat endpoint.

    ``messages`` is the front-end's running history in the shape
    ``[{"role": "user"|"assistant", "content": [{"text": "..."}]}]``.
    ``model_id`` is the UI's selected model id (e.g. ``ollama.llama3.2:3b``);
    the ``ollama.`` prefix is stripped, while an explicit non-local id requires
    configured Bedrock and never silently changes providers.
    """

    messages: list[dict[str, Any]] = Field(default_factory=lambda: cast(list[dict[str, Any]], []))
    model_id: Optional[str] = Field(None, alias="modelId")
    session_id: str = Field("ui-session", alias="sessionId")
    approval_tokens: list[str] = Field(default_factory=list, alias="approvalTokens")
    #: Commands the human has authorised for this turn. When the agent pauses on
    #: a YELLOW command, the frontend re-sends the turn with that command added
    #: here so it actually runs (resumable in-chat approval — blueprint Q5).
    approved_commands: list[str] = Field(default_factory=list, alias="approvedCommands")
    #: File edits the human has authorised this turn (the edit analog of
    #: ``approvedCommands``), each ``{filepath, old_string, new_string}``.
    approved_edits: list[dict[str, Any]] = Field(default_factory=list, alias="approvedEdits")
    #: New files the human has authorised this turn (the create analog of
    #: ``approvedEdits``), each ``{filepath, content}``.
    approved_creations: list[dict[str, Any]] = Field(default_factory=list, alias="approvedCreations")
    #: Opt-in sequential role-pass castes (planner -> coder -> reviewer over
    #: the one supervised loop). Absent/false -> the endpoint behaves
    #: byte-identically to the single-agent loop.
    role_pass: bool = Field(False, alias="rolePass")
    #: Opt-in ephemeral worker swarm: decompose -> N gated workers -> synthesize
    #: (ant-colony stigmergy over the same supervised loop). Absent/false ->
    #: unchanged. Takes precedence over rolePass when both are set.
    swarm: bool = Field(False, alias="swarm")

    model_config = {"populate_by_name": True}


class ChatRequest(BaseModel):
    """Body for ``/api/v1/chat`` — the lean Hinglish conversational endpoint.

    Conversation only (the GAGOS voice mind): a single ``transcript``
    line from the operator + an optional ``sessionId``. It reuses the multi-LLM
    router (privacy gate intact), memory recall, and REAL personalization facts,
    then streams one reply. NO file-write or coding tools run here — this is talk,
    not the agentic forge.
    """

    transcript: str = Field(
        ...,
        max_length=2000,
        description="The operator's spoken/typed turn (input-shielded: capped length).",
    )
    session_id: str = Field("voice-session", alias="sessionId")
    model_id: Optional[str] = Field(None, alias="modelId")

    model_config = {"populate_by_name": True}


class TerminalRequest(BaseModel):
    """Body for ``/api/terminal`` — a single shell command from the UI terminal."""

    command: str = Field(..., description="Command typed into the UI terminal.")
    session_id: Optional[str] = Field(None, alias="sessionId")

    model_config = {"populate_by_name": True}



    model_config = {"populate_by_name": True}


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #




@app.post("/api/v1/memory/compact")
def memory_compact(
    req: MemoryCompactRequest,
    compactor: MemoryCompactor = Depends(get_compactor),
) -> JSONResponse:
    """Operator-triggered memory compaction (audited "sleep" sweep).

    Defaults to ``dry_run=True`` so the caller MUST explicitly set
    ``dry_run=false`` to mutate stores. Returns a preview of what would be
    removed when dry-run is enabled; when disabled, performs the sweep and
    writes one audit entry under actor ``sleep-consolidation``.
    """
    result = compactor.compact(dry_run=req.dry_run)
    status_code = 200 if req.dry_run else 202
    return JSONResponse(content=result, status_code=status_code)











# --------------------------------------------------------------------------- #
# Front-end bridge: model discovery, conversational chat, UI terminal
# These three endpoints back the React UI's main surfaces. The ``/api/v1/*``
# routes above expose individual subsystems; these compose them for the UI.
# --------------------------------------------------------------------------- #
def _to_chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten the UI history (``content`` arrays) into Ollama chat messages."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            content_list: list[Any] = cast(list[Any], content)
            text_parts: list[str] = [
                cast(dict[str, Any], c).get("text", "")
                for c in content_list
                if isinstance(c, dict)
            ]
            text = " ".join(text_parts).strip()
        else:
            text = ""
        if text:
            out.append({"role": role, "content": text})
    return out


def _sse(
    event: str,
    data: dict[str, Any],
    *,
    turn_id: Optional[str] = None,
    seq: Optional[int] = None,
) -> str:
    """Format one Server-Sent Event frame.

    All newline characters (\\n, \\r) in the JSON payload are escaped to \\n
    and \\r so that an LLM output cannot inject fake SSE events by embedding
    ``\\n\\nevent: approve\\ndata: {...}`` inside a data field.
    """
    if turn_id is not None and seq is not None:
        data = event_for_sse(event, data, turn_id=turn_id, seq=seq).to_sse_payload()
    payload = json.dumps(data, ensure_ascii=False)
    # Defensive: escape any literal newlines that would break the SSE frame.
    payload = payload.replace("\r", "\\r").replace("\n", "\\n")
    return f"event: {event}\ndata: {payload}\n\n"


def _sse_writer(turn_id: str) -> Callable[[str, dict[str, Any]], str]:
    seq = 0

    def write(event: str, data: dict[str, Any]) -> str:
        nonlocal seq
        seq += 1
        return _sse(event, data, turn_id=turn_id, seq=seq)

    return write

#: Agent event type -> SSE event name the front-end's stream reader understands.
_STEP_EVENTS = {"tool_call", "tool_result", "tool_blocked"}

#: Episodic (L2) memory facade — the durable, chronological record of every turn.
_EPISODIC = EpisodicMemory()

#: Working (L1) memory facade — session-scoped RAM-only state.
_WORKING = WorkingMemory()

#: Semantic (L3) memory facade — durable knowledge chunks + vectors.
_SEMANTIC = SemanticMemory()

#: FAISS vector index shared with semantic memory.
_VECTOR_INDEX = _SEMANTIC.index

#: Process-wide audited memory compactor so working-session touch timestamps are
#: preserved across independent FastAPI dependency injections.
_COMPACTOR: Optional[MemoryCompactor] = None
_COMPACTOR_LOCK = threading.Lock()


#: System prompt for the lean conversational endpoint (the GAGOS voice mind,
#: Slice 1). It is CONVERSATION, not the coding forge: no file edits, no tool
#: loop — just a warm, technically deep Hinglish chat. The operator-facts context
#: block (REAL approved facts only; absent when none) is appended at request time,
#: and the honesty law is stated inline so the model never invents personal facts.
CHAT_SYSTEM_PROMPT = (
    "Tu GAGOS hai — operator ka personal AI-OS, 'the voyaging mind'. Tera naam HAMESHA "
    "GAGOS hai; tu KABHI khud ko 'Jarvis' ya kisi aur naam se nahi bulata. Tu ek saathi ki "
    "tarah baat karta hai: natural HINGLISH mein (English aur Hindi ka fluid mix), "
    "jaise operator khud likhta/bolta hai — uske tone aur mix ko match kar. "
    "Concise reh, warm reh, lekin technically deep — code, architecture, ya kuch "
    "bhi discuss kar sakta hai gehrai se. "
    "Yeh sirf baat-cheet hai, coding forge NAHI: tu koi file edit/create nahi karta, "
    "koi tool ya terminal nahi chalata, sirf jawaab deta hai. Agar operator ko "
    "actual code likhwana/chalwana ho, use politely batao ki woh main forge "
    "(generate) flow se kare. "
    "Personalization: neeche diye gaye operator ke REAL facts hi use kar; agar koi "
    "fact nahi diya gaya to koi personal baat invent mat kar — honest reh, "
    "generic reh."
)


from aios.api.turn_pipeline import (
    FactRecallResult,
    _calibrate_default_confidence,
    _crag_cloud_source,
    _crag_document_source,
    _crag_external_sources,
    _crag_llm_judge,
    _crag_web_source,
    _index_turn,
    _latest_user,
    _make_confirm_hook,
    _make_failure_hook,
    _operator_facts_block,
    _recall_facts,
    _recall_lessons,
    _recall_memory,
    _recall_pending_commands,
    _recall_self_model,
    _recall_skills,
    _record_episode,
    _verify_target_key,
    _verify_target_keys,
    _workflow_step,
)


@app.post("/api/generate")
def generate(
    req: GenerateRequest,
    request: Request,
    client: OllamaClient = Depends(get_ollama_client),
    bedrock: Optional[BedrockClient] = Depends(get_bedrock_client),
    gemini: Optional[GeminiClient] = Depends(get_gemini_client),
    openai_client: Optional[Any] = Depends(get_openai_client),
    anthropic_client: Optional[Any] = Depends(get_anthropic_client),
    executor: Executor = Depends(get_executor),
    indexer: Optional[SemanticMemory] = Depends(get_semantic_indexer),
    reflector: Optional[ReflectionAgent] = Depends(get_reflection_agent),
    snapshot: Callable[..., object] = Depends(get_edit_snapshot),
    planner_llm: LLMClient = Depends(get_llm_client),
    approvals: ApprovalStore = Depends(get_approval_store),
    mistakes: MistakeMemory = Depends(get_mistake_memory),
    development: DevelopmentTracker = Depends(get_development_tracker),
    skills: SkillMemory = Depends(get_skill_memory),
    swarm_patterns: SwarmPatternMemory = Depends(get_swarm_pattern_memory),
    autonomy: AutonomyLedger = Depends(get_autonomy),
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
    cerebellum: Cerebellum = Depends(get_cerebellum),
    native_planner: NativePlanner = Depends(get_native_planner),
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
    conversation_state: ConversationStateStore = Depends(get_conversation_state_store),
    alignment_evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
    alignment_interpreter: Optional[AlignmentInterpreter] = Depends(get_alignment_interpreter),
    facts: SemanticFacts = Depends(get_semantic_facts),
    compactor: MemoryCompactor = Depends(get_compactor),
) -> StreamingResponse:
    """Run the agentic tool loop with memory, streaming it to the UI as SSE.

    Pipeline per turn (blueprint stages 4 -> ... -> consolidation):
      1. Recall relevant semantic memories and inject them into the agent's
         context (surfaced as a ``query_knowledge`` step when anything is found).
      2. Persist the user turn to L2 episodic memory.
      3. Run the agentic tool loop (``read_file``/``read_directory``/
         ``execute_terminal``, all gated + audited), forwarding tool activity as
         ``step`` frames, the validated advisory interpretation as an
         ``alignment`` frame, the answer as ``text_chunk`` frames, any code as
         a ``code`` frame, and finishing with ``done`` (or ``error``).
      4. Persist the assistant's final answer to L2 episodic memory and embed the
         completed turn into L3 semantic memory (self-reinforcing recall).
    """
    chat_messages = _to_chat_messages(req.messages)
    user_text = _latest_user(chat_messages)
    session_id = _session_id_from_request(request, req.session_id)
    _enforce_conversation_rate_limit(session_id)
    if len(user_text) > 2000:
        raise HTTPException(
            status_code=422, detail="Input exceeds 2000 characters."
        )
    if (injection_reason := _check_prompt_injection(user_text)):
        raise HTTPException(status_code=400, detail=f"[SECURITY BLOCK] {injection_reason}")
    # The agent routes by PURPOSE: infer the task from the user's message so 'auto'
    # picks a coder for code, a reasoner for analysis, etc. (require_tools still
    # keeps the loop on a tool-capable model regardless of the inferred task).
    task = infer_task(user_text)
    chat_client, model = _select_chat_client(
        req.model_id, client, bedrock, gemini=gemini,
        openai=openai_client, anthropic=anthropic_client, task=task,
        metrics=_route_metrics(development, req.model_id),
        calibration_weight=config.ROUTER_CALIBRATION_WEIGHT,
    )
    # The serving model is announced lazily from inside the stream (see
    # `_route_frame`); here we only normalise `model` to the route's view of it.
    _, model = _active_route(chat_client, bedrock, gemini, model,
                             openai=openai_client, anthropic=anthropic_client)

    def _route_meta() -> dict[str, Any]:
        """Development metadata for the model that ACTUALLY served (post-failover)."""
        p, m = _active_route(chat_client, bedrock, gemini, model,
                             openai=openai_client, anthropic=anthropic_client)
        return {"provider": p, "model": m, "task": task}

    compactor.touch_working_session(session_id)
    if req.approved_commands or req.approved_edits or req.approved_creations:
        raise HTTPException(
            status_code=400,
            detail="raw approved payloads are not accepted; use server-issued approvalTokens",
        )
    approved_commands: list[str] = []
    approved_edits: list[dict[str, Any]] = []
    approved_creations: list[dict[str, Any]] = []
    try:
        if not req.approval_tokens:
            approvals.clear_session(session_id)
        for token in req.approval_tokens:
            action = approvals.redeem(token, session_id)
            if action.action_type == "command":
                executor.reset_sensitive_actions(session_id)
        for action in approvals.grants(session_id):
            if action.action_type == "command":
                approved_commands.append(str(action.payload["command"]))
            elif action.action_type == "edit":
                approved_edits.append(action.payload)
            elif action.action_type == "create":
                approved_creations.append(action.payload)
    except (ApprovalError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid approval token: {exc}") from exc
    # Approval-resume continuation (ratified option A, S3): a resume (tokens
    # present) replays the convo tail this session stashed at its last pause.
    # A token-LESS fresh directive on the same session must NOT inherit a
    # stale tail from an abandoned pause -- clear it instead, mirroring the
    # approvals.clear_session() sibling call just above.
    resume_tail = (
        turn_state.take(session_id)
        if req.approval_tokens
        else (turn_state.clear(session_id) or None)
    )

    def event_stream() -> Iterator[str]:
        sse = _sse_writer(session_id)
        if not user_text:
            yield sse("error", {"text": "No user message provided."})
            return

        # Telemetry (Phase 1 lap-counter, roadmap SS1): observation-only, never
        # gates or blocks a turn (record_run fails open). `_dispatch_path` starts
        # at the worst-case honest default and is only ever UPGRADED to a more
        # specific value once a real event proves it (playbook/native-plan
        # replay) -- so a turn that never emits one of those events is
        # correctly counted as `llm` (or `refused_offline` under the offline
        # guard). `_max_zone` is a coarse approximation (see scoping notes):
        # it starts GREEN and is only ever raised, never lowered, toward the
        # worst zone actually observed this turn.
        _turn_started = time.perf_counter()
        _dispatch_path = (
            telemetry.DISPATCH_REFUSED_OFFLINE if config.OFFLINE_MODE else telemetry.DISPATCH_LLM
        )
        _max_zone = Zone.GREEN.value
        _ZONE_RANK = {Zone.GREEN.value: 0, Zone.YELLOW.value: 1, Zone.RED.value: 2}

        def _bump_zone(new_zone: str) -> None:
            nonlocal _max_zone
            if _ZONE_RANK.get(new_zone, 0) > _ZONE_RANK.get(_max_zone, 0):
                _max_zone = new_zone

        def _record_telemetry(verified_outcome: str) -> None:
            provider, served_model = _active_route(
                chat_client, bedrock, gemini, model,
                openai=openai_client, anthropic=anthropic_client,
            )
            telemetry.record_run(
                session_id=session_id,
                task_signature=task_signature(user_text),
                dispatch_path=_dispatch_path,
                provider=provider,
                model=served_model,
                verified_outcome=verified_outcome,
                latency_ms=round((time.perf_counter() - _turn_started) * 1000),
                max_zone=_max_zone,
            )

        # The ACTIVE BRAIN for this turn: which provider/model served it + a privacy
        # indicator, so the UI can show the voyaging mind's current brain. Emitted
        # LAZILY — only once a model has actually served (the first text/tool_call/
        # code), and again whenever a mid-loop failover switches the serving model —
        # so the badge names the model that did the work, never a ranked-but-
        # uninvocable primary that silently failed over. A `FailoverChatClient` only
        # knows which candidate served AFTER its first `chat()` returns; announcing
        # before that would advertise the cascade head, which may not be invocable.
        # Purely informational; the cage decides regardless.
        announced_route: Optional[tuple[str, str]] = None

        def _route_frame() -> Optional[str]:
            nonlocal announced_route
            p, m = _active_route(chat_client, bedrock, gemini, model,
                                 openai=openai_client, anthropic=anthropic_client)
            if (p, m) == announced_route:
                return None  # unchanged since the last announcement — don't repeat
            announced_route = (p, m)
            return sse(
                "route",
                {
                    "provider": p,
                    "model": m,
                    "privacy": "local" if p == router.PROVIDER_OLLAMA else "cloud",
                    "task": task,
                    "auto": req.model_id in _AUTO_IDS,
                },
            )

        # 1. Understand + apply the deterministic communication policy + recall.
        #    The alignment frame is advisory. Its communication policy may pause
        #    a context-free request to ask a question, but it has no execution or
        #    approval authority and is never treated as evidence. When the
        #    interpreter is disabled (AIOS_INTERPRET_ALIGNMENT=false) the turn
        #    skips interpretation entirely: no frame, observation, or ask-pause.
        context_parts: list[str] = []
        alignment = None
        # Hoisted above the (conditional) alignment block: the plan stage below
        # must be able to read it even when AIOS_INTERPRET_ALIGNMENT is off.
        _cerebellum_matched = False
        if alignment_interpreter is not None:
            base_alignment = alignment_interpreter.understand(chat_messages)
            alignment = base_alignment
            active_correction = conversation_state.active_correction(session_id)
            if active_correction is not None:
                try:
                    alignment = apply_user_corrections(
                        alignment,
                        active_correction["corrections"],
                        revision=int(active_correction["revision"]),
                    )
                except (TypeError, ValueError) as exc:
                    # Corrupt optional continuity state must never break chat or
                    # silently gain authority.
                    logger.warning("Failed to apply active user correction", exc_info=exc)
            context_parts.append(alignment.to_prompt_block())
            alignment_payload = alignment.as_dict()
            base_alignment_payload = base_alignment.as_dict()
            try:
                observation_id = (
                    alignment_evaluation.latest_observation_id(session_id)
                    if req.approval_tokens
                    else alignment_evaluation.record(session_id, alignment_payload)
                )
                if observation_id is not None:
                    alignment_payload["evaluation"] = {
                        "observation_id": observation_id,
                        "automatic_policy_updates": False,
                    }
                    base_alignment_payload["evaluation"] = alignment_payload["evaluation"]
            except Exception as exc:  # noqa: BLE001 - evaluation must never break the chat
                logger.warning("Failed to record alignment evaluation", exc_info=exc)
            try:
                if active_correction is not None and alignment.correction.active:
                    conversation_state.refresh_active_correction(
                        session_id,
                        base_frame=base_alignment_payload,
                        corrected_frame=alignment_payload,
                    )
                else:
                    conversation_state.save(session_id, alignment_payload)
            except Exception as exc:  # noqa: BLE001 - continuity must never break the chat
                logger.warning("Failed to persist alignment frame", exc_info=exc)
            yield sse("alignment", alignment_payload)
            if alignment.communication.ambiguity_action == "ask":
                question = alignment.communication.clarifying_question
                _record_episode(session_id, "user", user_text)
                _record_episode(session_id, "assistant", question)
                approvals.clear_session(session_id)
                yield sse("text_chunk", {"text": question})
                # An advisory early exit is still a real turn -- count it
                # (aborted), or every clarification-asked turn silently
                # vanishes from telemetry.
                _record_telemetry(telemetry.OUTCOME_ABORTED)
                yield sse("done", {})
                return

        # ── Sovereignty S1: cerebellum pre-check ──────────────────
        # If a compiled playbook matches the user message, skip the
        # confidence gate — the actual replay happens inside
        # ToolAgent.run() (below), which dispatches every step through
        # self._dispatch (the FULL security pipeline: classify(),
        # scope_lock, audit_logger, verifier). This pre-check only
        # matches and announces; it never dispatches a tool call
        # itself, so there is no parallel security path. Deliberately
        # OUTSIDE the alignment block: ToolAgent replays a matched
        # playbook regardless of AIOS_INTERPRET_ALIGNMENT, so the match
        # announcement — and the plan stage's reflex-skip below — must
        # not depend on the interpreter being enabled.
        if user_text:
            try:
                _cb_match = cerebellum.match(user_text)
            except Exception as exc:  # noqa: BLE001 - cerebellum is advisory, never fatal
                logger.warning("Cerebellum match failed", exc_info=exc)
                _cb_match = None
            if _cb_match is not None:
                _cerebellum_matched = True
                yield sse("cerebellum_match", {
                    "goal": _cb_match.goal_pattern,
                    "playbook_id": _cb_match.id,
                    "step_count": len(_cb_match.steps),
                })

        if alignment is not None and not _cerebellum_matched:
            confidence, confidence_calibration = _calibrate_default_confidence(
                " ".join(part for part in (user_text, alignment.goal, alignment.intent) if part),
                alignment.confidence,
                reflector=reflector,
                development=development,
                skills=skills,
            )
            confidence_result = confidence_gate(confidence)
            if not confidence_result.passed:
                question = (
                    "I am not confident enough in my understanding to proceed. "
                    "What should I clarify before continuing?"
                )
                if alignment.unknowns:
                    question = (
                        "I am not confident enough in my understanding to proceed. "
                        f"Please clarify: {alignment.unknowns[0]}"
                    )
                payload = {
                    "confidence": confidence,
                    "threshold": config.CONFIDENCE_THRESHOLD,
                    "reason": confidence_result.reason,
                    "goal": alignment.goal,
                    "intent": alignment.intent,
                    "question": question,
                    "calibration": confidence_calibration,
                }
                _record_episode(session_id, "user", user_text)
                _record_episode(session_id, "assistant", question)
                approvals.clear_session(session_id)
                yield sse("confidence.gated", payload)
                yield sse("text_chunk", {"text": question})
                # A confidence-gated turn is still a real turn -- count it.
                _record_telemetry(telemetry.OUTCOME_ABORTED)
                yield sse("done", {})
                return

        # ── Mandatory plan stage (Product-Phase-1 close-out; AIOS_PLAN_STAGE) ──
        # The SAME deterministic Planner behind POST /api/v1/plan, run
        # unconditionally on every non-reflex FIRST turn: native-first
        # (verified experience templates), LLM fallback. The plan is ADVISORY
        # context — it has no execution or approval authority; escalated
        # steps still pause at the gateway's per-action approval surface when
        # they actually execute, and telemetry's dispatch_path is NOT
        # upgraded here (the plan advises the turn; it does not serve it —
        # see the invariant where _dispatch_path is initialized). Fail-open
        # by design: any planner failure (including offline-mode native
        # misses) logs, emits nothing, and the turn proceeds — the confidence
        # gate and approval surface remain the safety layer. Skipped on
        # reflex turns (a matched playbook exists precisely to avoid this
        # consultation) and on approval-resume turns (the goal was already
        # planned when the turn first ran; re-planning mid-approved-action
        # would inject a second, possibly different plan).
        if (
            config.PLAN_STAGE_ENABLED
            and user_text
            and not _cerebellum_matched
            and not req.approval_tokens
        ):
            # Announce BEFORE the (blocking) planner consultation so the
            # stream is never silent for a full LLM completion — time-to-
            # first-byte stays bounded and the UI can show the phase.
            yield sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "plan",
                    "output": "Plan stage: decomposing the goal into confidence-gated steps…",
                    "id": "plan-stage",
                },
            )
            try:
                _stage_planner = Planner(
                    planner_llm,
                    native=native_planner,
                    mistakes=mistakes,
                    development=development,
                    skills=skills,
                )
                _stage_plan = _stage_planner.plan(user_text)
            except PlannerError as exc:
                logger.warning("Plan stage failed open: %s", exc)
            except Exception as exc:  # noqa: BLE001 - planning is advisory, never fatal
                logger.warning("Plan stage failed open", exc_info=exc)
            else:
                yield sse("plan", serialize_plan(_stage_plan))
                context_parts.append(plan_to_prompt_block(_stage_plan))

        semantic = _recall_memory(user_text)
        if semantic:
            context_parts.append(semantic)
            yield sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "query_knowledge",
                    "output": semantic[:400],
                    "id": "memory-recall",
                },
            )

        lessons = _recall_lessons(reflector, session_id, user_text)
        if lessons:
            block = "RELEVANT LESSONS (verified cross-task or pending from this task):\n" + "\n".join(
                f"- [{le.get('verification_status', 'pending')}; {le['error_type']}] "
                f"{le['lesson_text']}"
                for le in lessons
            )
            context_parts.append(block)
            yield sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "reflect",
                    "output": f"Recalled {len(lessons)} past lesson(s); filtered for relevance.",
                    "id": "lesson-recall",
                },
            )

        recalled_skills = _recall_skills(skills, user_text)
        if recalled_skills:
            skill_block = "VERIFIED REUSABLE WORKFLOWS:\n" + "\n".join(
                f"- For {skill['goal_pattern']}: {' -> '.join(skill['steps'])} "
                f"(verified success rate {skill['success_rate']:.0%})"
                for skill in recalled_skills
            )
            context_parts.append(skill_block)
            yield sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "query_skills",
                    "output": f"Recalled {len(recalled_skills)} verified workflow(s).",
                    "id": "skill-recall",
                },
            )

        facts_result = _recall_facts(facts, user_text)
        if facts_result:
            context_parts.append(facts_result.text)
            yield sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "query_facts",
                    "output": facts_result.text[:400],
                    "id": "fact-recall",
                },
            )
            for inf in facts_result.inferences:
                yield sse("graph_inference", inf)
                if inf.get("reached_horizon"):
                    yield sse("graph_horizon", {
                        "entity": inf.get("entity", "?"),
                        "confidence": inf.get("combined_confidence", 0),
                    })

        # Narrative self (opt-in): a grounded, verified-only autobiographical
        # self-model joins the recalled context — the organism reasoning with an
        # honest sense of what it's actually reliable at. Fail-closed: empty when
        # there's too little verified evidence.
        if config.NARRATIVE_SELF_ENABLED:
            # W2: when the cortex bus is on, the self-model was synthesized OFF
            # the hot path by SelfModelHandler (turn.completed observer) — read
            # its cache. Fall back to inline synthesis when the bus is off
            # (default: identical to pre-W2 behavior) or before the first
            # observation has been processed.
            cached_self_model = (
                _self_model_handler.recall()
                if config.CORTEX_BUS and _self_model_handler is not None
                else None
            )
            self_model_block = (
                cached_self_model
                if cached_self_model is not None
                else _recall_self_model(development, MistakeMemory())
            )
            if self_model_block:
                context_parts.append(self_model_block)
                yield sse(
                    "step",
                    {
                        "type": "tool_result",
                        "tool": "self_model",
                        "output": self_model_block[:400],
                        "id": "self-model-recall",
                    },
                )

        memory_context = "\n\n".join(context_parts) or None

        # Seed for the fail->confirm tracker (see _recall_pending_commands): this
        # session's still-pending lessons + their failed commands, so a lesson
        # recorded before an approval pause is promoted when its exact command
        # finally succeeds in the replayed continuation of the turn.
        recalled_pending = _recall_pending_commands(reflector, session_id)

        # 2. Persist the user turn.
        _record_episode(session_id, "user", user_text)

        # 3. Agentic loop with recalled context + lessons + reflection + confirmation.
        #    `chat_client` is local Ollama or cloud Bedrock per the selected model.
        #    The factory exists so the role-pass castes can stamp out per-role
        #    views (system prompt + tool subset) over the SAME gated wiring.
        # C4: streaming function for real-time cloud token delivery.
        _stream_fn = getattr(chat_client, "stream_chat_with_tools", None)

        def make_agent(**overrides: Any) -> ToolAgent:
            return ToolAgent(
                chat_client,
                executor,
                model=model,
                session_id=session_id,
                memory_context=memory_context,
                on_failure=_make_failure_hook(reflector, session_id),
                confirm_lesson=_make_confirm_hook(reflector, consolidator),
                # Confirm-across-approval-boundary: seed the fail->confirm tracker
                # so a lesson recorded before an approval pause is still promoted
                # when its exact command later succeeds in the replayed turn.
                recalled_pending=recalled_pending,
                approved_commands=approved_commands,
                approved_edits=approved_edits,
                approved_creations=approved_creations,
                snapshot=snapshot,
                # The Planner needs a COMPLETION client (.complete()); pass the local
                # get_llm_client one — never `chat_client`, which may be cloud Bedrock —
                # so planning always uses the local completion model.
                planner_llm=planner_llm,
                # Self-Analysis T2 (propose_fixes) drafts diffs with the SAME completion
                # client (not chat_client). It only writes proposals to the report —
                # never edits or applies source.
                self_analysis_llm=planner_llm,
                # Earned-autonomy bridge: opt-in, off by default. When enabled and
                # a write class has earned it, the turn applies it without pausing
                # (still gated, audited, and revoked instantly on a verified fail).
                autonomy=autonomy,
                # Approval-resume continuation (ratified option A, S3): the prior
                # pause's convo tail for this session, or None. Model context
                # only -- carries no authority of its own.
                resume_tail=resume_tail,
                # Sovereignty S1: compiled-experience engine. Matches verified
                # skill arcs and replays them through _dispatch without an LLM.
                cerebellum=cerebellum,
                # Sovereignty S3: native symbolic planner. Plans known task
                # shapes from verified experience without an LLM call.
                native_planner=native_planner,
                # C4: stream tokens in real-time when the cloud client supports it.
                stream_fn=_stream_fn if callable(_stream_fn) else None,
                **overrides,
            )

        # Cloud-burst factory: when the ant-colony's CLOUD_BROKER labels a subtask
        # as cloud-eligible, it runs through a dedicated cloud chat client. The
        # provider is surfaced in `cloud_route` SSE frames so the UI can mark the
        # leg as having left the local machine.
        cloud_client: Optional[Any] = None
        cloud_provider: Optional[str] = None
        cloud_model: Optional[str] = None
        if req.swarm and config.SWARM_CLOUD_BURST_ENABLED:
            if config.BEDROCK_ENABLED:
                cloud_client = BedrockClient()
                cloud_provider = "bedrock"
                cloud_model = config.BEDROCK_MODEL
            elif config.GEMINI_ENABLED:
                cloud_client = GeminiClient()
                cloud_provider = "gemini"
                cloud_model = config.GEMINI_MODEL

        def make_cloud_agent(**overrides: Any) -> ToolAgent:
            if cloud_client is None:
                raise RuntimeError("Cloud burst requested but no cloud provider is configured")
            return ToolAgent(
                cloud_client,
                executor,
                model=cloud_model,
                session_id=session_id,
                memory_context=memory_context,
                on_failure=_make_failure_hook(reflector, session_id),
                confirm_lesson=_make_confirm_hook(reflector, consolidator),
                # Confirm-across-approval-boundary: seed the fail->confirm tracker
                # so a lesson recorded before an approval pause is still promoted
                # when its exact command later succeeds in the replayed turn.
                recalled_pending=recalled_pending,
                approved_commands=approved_commands,
                approved_edits=approved_edits,
                approved_creations=approved_creations,
                snapshot=snapshot,
                planner_llm=planner_llm,
                self_analysis_llm=planner_llm,
                autonomy=autonomy,
                resume_tail=resume_tail,
                **overrides,
            )
        answer_parts: list[str] = []
        workflow_steps: list[str] = []
        blocked_actions = 0
        verification_evidence: list[str] = []
        verify_verdicts: dict[str, str] = {}
        #: Per-target verification strength (parallel to the verdict dicts), so the
        #: turn's calibration strength is the WEAKEST authoritative PASS — a strong
        #: verify on one target can never launder a weak one, and a model's advisory
        #: verify can never raise the authoritative strength (see ``record_outcome``).
        verify_strengths: dict[str, VerificationStrength] = {}
        #: Verdicts from the FORCED auto-verify only (id ``autoverify-*``). This is
        #: the authoritative evidence for the turn's outcome; the model's own
        #: ``verify`` tool calls are advisory and must not override it.
        auto_verdicts: dict[str, str] = {}
        auto_strengths: dict[str, VerificationStrength] = {}
        communication_notice = (
            alignment.communication_notice() if alignment is not None else ""
        )
        if communication_notice:
            answer_parts.append(communication_notice)
            yield sse("text_chunk", {"text": communication_notice})

        mastered_levels: list[tuple[str, int]] = []

        def record_outcome(outcome: str) -> None:
            """Best-effort development, skill, and curriculum evidence write."""
            # The strength of this turn's authoritative verification gates ALL
            # calibration (roadmap Phase 1): a below-floor (weak) green must not
            # calibrate the router/planner, promote a swarm pattern, or advance
            # curriculum mastery. Strength is the WEAKEST authoritative target
            # strength (auto-verify if any ran, else the model's own verify) — not
            # the last PASS across all evidence. This defeats laundering: a model
            # cannot append a STRONG advisory verify to raise a turn whose forced
            # auto-verify was weak, and one strong target cannot mask a weak one.
            authoritative_strengths = auto_strengths or verify_strengths
            turn_strength = (
                min(authoritative_strengths.values())
                if authoritative_strengths
                else VerificationStrength.NONE
            )
            # A weak verified_success is recorded as 'unverified' so it is excluded
            # from router/planner calibration (reuses the existing exclusion).
            dev_outcome = (
                "unverified"
                if outcome == "verified_success" and not meets_promotion_floor(turn_strength)
                else outcome
            )
            try:
                development.record(
                    user_text,
                    dev_outcome,
                    tool_calls=len(workflow_steps),
                    human_interventions=len(req.approval_tokens),
                    blocked_actions=blocked_actions,
                    metadata=_route_meta(),
                )
            except Exception as exc:  # noqa: BLE001 - metrics must never break chat
                logger.warning("Development metrics recording failed", exc_info=exc)
            if config.FACTS_AUTO_EXTRACT:
                try:
                    proposed_count = 0
                    for fact_subject, fact_predicate, fact_object in extract_candidates(
                        user_text,
                        max_candidates=config.FACTS_AUTO_EXTRACT_MAX_PER_TURN,
                    ):
                        r = facts.strengthen_or_propose(
                            fact_subject, fact_predicate, fact_object,
                        )
                        if r.proposed or r.reason == "strengthened":
                            proposed_count += 1
                    if proposed_count and _cortex_bus:
                        _cortex_bus.append(
                            "facts.proposed", session_id,
                            {"count": proposed_count, "source": "generate"},
                        )
                except Exception as exc:  # noqa: BLE001 - proposal formation is best-effort
                    logger.warning("Failed to propose auto-extracted facts", exc_info=exc)
            if outcome not in {"verified_success", "verified_failure"}:
                return
            passed = outcome == "verified_success"
            if passed:
                evidence = next(
                    (
                        item
                        for item in reversed(verification_evidence)
                        if item.startswith("[VERIFY PASS]")
                    ),
                    "",
                )
            else:
                evidence = next(
                    (
                        item
                        for item in reversed(verification_evidence)
                        if item.startswith("[VERIFY FAIL]")
                    ),
                    "",
                )
            direct_id: Optional[int] = None
            if workflow_steps:
                try:
                    # Gate promotion on verification strength (roadmap Phase 1): the
                    # strength token is stamped into the [VERIFY ...] evidence by the
                    # Verifier (command-aware), so a weak green cannot mint a
                    # verified skill. On a fail, success=False makes strength moot.
                    direct_id = skills.record_attempt(
                        user_text,
                        workflow_steps,
                        success=passed,
                        strength=turn_strength,
                    )
                except Exception as exc:  # noqa: BLE001 - skill learning is best-effort
                    logger.warning("Failed to record skill attempt", exc_info=exc)
            # Reuse pheromone: trails that were recalled into this turn's
            # context share its verifier verdict — minus the trail the agent
            # re-walked directly, which record_attempt already credited.
            # Exclude ONLY the trail the agent re-walked directly (already credited
            # by record_attempt) so it isn't double-credited. When direct_id is
            # None (no direct walk, or record_attempt failed) there is nothing to
            # exclude, so every recalled trail correctly earns reuse credit. The
            # explicit None check documents that intent (the old `!= direct_id` was
            # an always-true int-vs-None compare — same behavior, but a smell).
            reused_ids = [
                int(s["skill_id"])
                for s in recalled_skills
                if direct_id is None or int(s["skill_id"]) != direct_id
            ]
            if reused_ids:
                try:
                    skills.record_reuse(reused_ids, success=passed)
                except Exception as exc:  # noqa: BLE001 - reuse credit is best-effort
                    logger.warning("Failed to record skill reuse credit", exc_info=exc)
            if swarm_plan:
                try:
                    swarm_patterns.record_attempt(
                        user_text, swarm_plan, success=passed, strength=turn_strength
                    )
                except Exception as exc:  # noqa: BLE001 - pattern learning is best-effort
                    logger.warning("Failed to record swarm pattern attempt", exc_info=exc)
            try:
                curriculum.record_matching(
                    user_text,
                    passed=passed,
                    evidence=evidence,
                    strength=turn_strength,
                    on_mastered=lambda skill, level: mastered_levels.append((skill, level)),
                )
            except Exception as exc:  # noqa: BLE001 - unmatched/invalid curriculum is harmless
                logger.warning("Failed to record curriculum match", exc_info=exc)

        try:
            if req.swarm:
                event_source = run_swarm(
                    make_agent,
                    chat_messages,
                    pattern_memory=swarm_patterns,
                    make_cloud_agent=make_cloud_agent if cloud_client is not None else None,
                    cloud_provider=cloud_provider,
                )
            elif req.role_pass:
                event_source = run_role_pass(make_agent, chat_messages)
            else:
                event_source = make_agent().run(chat_messages)
        except Exception as exc:  # noqa: BLE001 - agent construction must not kill SSE
            logger.error("Tool-loop construction failed", exc_info=exc)
            yield sse("error", {"text": f"Internal error: {exc}"})
            # A turn killed by construction failure is still a real turn -- count it.
            _record_telemetry(telemetry.OUTCOME_ABORTED)
            yield sse("done", {})
            return
        def _safe_iter(source):
            """Wrap a generator so exceptions during iteration are logged, not silent."""
            try:
                yield from source
            except Exception as exc:  # noqa: BLE001
                logger.error("Tool-loop iteration failed", exc_info=exc)
                yield {"type": "error", "text": f"Internal error: {exc}"}
                yield {"type": "done"}

        swarm_plan: Optional[list[str]] = None
        for ev in _safe_iter(event_source):
            kind = ev["type"]
            if kind in ("tool_call", "text", "code", "done", "human_required"):
                # A model produced output (or the turn is ending) -> the failover
                # client now names the model that ACTUALLY served. Announce (or
                # refresh on failover) the brain BEFORE the event, so the badge
                # tracks the real worker. `done`/`human_required` are a fallback:
                # they guarantee the badge still appears for a turn whose model
                # served no text/tool_call (e.g. an empty answer). `_route_frame`
                # is idempotent, so this never double-announces an unchanged route.
                route_frame = _route_frame()
                if route_frame is not None:
                    yield route_frame
            if kind in _STEP_EVENTS:
                if kind == "tool_call":
                    workflow_steps.append(_workflow_step(ev))
                elif kind == "tool_blocked":
                    blocked_actions += 1
                    # Coarse max_zone approximation (scoping report SS5.2): a
                    # blocked tool call is the strongest per-event signal
                    # available today that this turn touched a RED-classified
                    # action (the real per-call Zone is computed by the
                    # security gateway but discarded before it reaches this
                    # event dict). Known false positive: a caste-permission
                    # block also yields status=="blocked" without a Zone.RED
                    # verdict -- accepted until Zone is threaded through.
                    _bump_zone(Zone.RED.value)
                if kind == "tool_result":
                    output = str(ev.get("output", ""))
                    # Provenance gate: ONLY the verify tool (the model's `verify`
                    # and the forced `autoverify-*`, both emitted with tool=="verify")
                    # may contribute authoritative verification evidence. Without
                    # this, any tool whose output a model controls — e.g.
                    # `echo "[VERIFY PASS] 5 passed (strength=STRONG)"` auto-executed
                    # GREEN — would forge a passing verdict and a STRONG strength,
                    # laundering a hollow turn into calibration. The string prefix is
                    # necessary but not sufficient; trusted provenance is.
                    if ev.get("tool") == "verify" and (
                        output.startswith("[VERIFY PASS]") or output.startswith("[VERIFY FAIL]")
                    ):
                        verification_evidence.append(output)
                        raw_target = str(ev.get("target") or "")
                        keys = (
                            _verify_target_keys(raw_target)
                            if raw_target
                            # Unattributed evidence keys uniquely: its verdict
                            # can never be cleared by a later PASS elsewhere
                            # (fail-closed).
                            else [f"unattributed-{len(verification_evidence)}"]
                        )
                        verdict = "PASS" if output.startswith("[VERIFY PASS]") else "FAIL"
                        strength = strength_from_text(output)
                        for key in keys:
                            verify_verdicts[key] = verdict
                            verify_strengths[key] = strength
                        # The FORCED auto-verify (run by the system after a write) is
                        # the authoritative evidence; the model's OWN `verify` tool
                        # call is advisory. A model running a broken verify command —
                        # e.g. a mis-pathed `pytest training_ground/test_x.py` from the
                        # sandbox cwd → exit 4, 0 tests — must NOT fail a turn whose
                        # written code actually passes the forced check.
                        if str(ev.get("id", "")).startswith("autoverify"):
                            for key in keys:
                                auto_verdicts[key] = verdict
                                auto_strengths[key] = strength
                        # Surface a typed verification frame so the UI can celebrate or
                        # reflect without parsing the raw tool output.
                        for key in keys:
                            yield sse(
                                "verify_result",
                                {
                                    "verdict": verdict.lower(),
                                    "target": key,
                                    "output": output[:320],
                                },
                            )
                yield sse("step", ev)
            elif kind == "native_plan":
                if _dispatch_path != telemetry.DISPATCH_PLAYBOOK:
                    _dispatch_path = telemetry.DISPATCH_NATIVE_PLAN
                yield sse("native_plan", ev)
            elif kind == "text":
                answer_parts.append(ev["text"])
                yield sse("text_chunk", {"text": ev["text"]})
            elif kind == "code_chunk":
                # Incremental reveal of the final code block (the model is
                # non-streaming, so this is emit-time chunking, not raw tokens).
                yield sse("code_chunk", {"code": ev["code"], "language": ev["language"]})
            elif kind == "code":
                yield sse("code", {"code": ev["code"], "language": ev["language"]})
            elif kind == "error":
                yield sse("error", {"text": ev["text"]})
            elif kind == "earned_autonomy":
                # The earned-autonomy bridge auto-applied a write with NO human
                # pause — the write class earned it by verified-success evidence.
                # Surface it so the brain can show itself acting on its own
                # earned trust (still gated, audited, and revocable).
                yield sse("earned_autonomy", ev)
            elif kind.startswith("cerebellum_"):
                # Sovereignty S1: the cerebellum replayed a compiled playbook.
                # Forward all cerebellum events to the SSE stream so the
                # organism body renders the reflex phase (orange, low
                # metabolism, no brain churn).
                if kind == "cerebellum_step_done":
                    workflow_steps.append(
                        f"{ev.get('tool', '?')}: cerebellum replay"
                    )
                elif kind == "cerebellum_done":
                    _dispatch_path = telemetry.DISPATCH_PLAYBOOK
                yield sse(kind, ev)
            elif kind == "swarm_plan":
                # Plan event from the ant-colony; used internally for pattern
                # recording and also surfaced to the UI so the HUD can render it.
                swarm_plan = ev.get("plan")
                yield sse(kind, ev)
            elif kind in ("caste_start", "caste_end", "cloud_route"):
                # Observational swarm lifecycle frames for the 3D HUD.
                if kind == "cloud_route" and cloud_provider:
                    try:
                        log_action(
                            "cloud-route",
                            json.dumps({"provider": cloud_provider, "model": cloud_model}),
                            Zone.GREEN,
                        )
                    except Exception as exc:  # noqa: BLE001 - audit must never break the stream
                        logger.warning("Failed to record cloud-route audit entry", exc_info=exc)
                yield sse(kind, ev)
            elif kind == "human_required":
                # The agent paused on a YELLOW command. Ask the UI for approval;
                # the turn ends here (no answer recorded) and is replayed once the
                # human authorises the command. Surface the *command* in plain
                # language — never the raw classifier reason, which embeds the
                # matched regex pattern (e.g. "\\bpip\\s+install\\b") and belongs
                # in the audit log, not in a human approval prompt. Shape matches
                # the frontend's pendingAction handler ({commands, explanation}).
                _bump_zone(Zone.YELLOW.value)
                cmd = ev["command"]
                edit = ev.get("edit")
                creation = ev.get("creation")
                # Approval-resume continuation (ratified option A, S2): pop the
                # convo tail off the event BEFORE any payload is built below --
                # it must never reach `payload`/the SSE wire. Stashed under this
                # session id so a later resume (token redeemed above) can pop it
                # back out and splice it into the next ToolAgent.run's convo.
                # The token itself lives only in `payload` (issued just below),
                # never in the tail -- the tail carries no authority.
                _convo_tail = ev.pop("_convo_tail", None)
                if _convo_tail:
                    turn_state.stash(session_id, _convo_tail)
                try:
                    if edit is not None:
                        token = approvals.issue("edit", edit, session_id)
                        # An edit_file approval: surface the unified diff + the edit
                        # triple so the UI shows the diff and re-sends it as an
                        # approved edit on resume (a snapshot is taken before writing).
                        payload = {
                            "input": {
                                "edits": [edit],
                                "approvalToken": token,
                                "diff": ev.get("diff", ""),
                                "explanation": (
                                    "The agent wants to edit a file. Review the diff "
                                    "and approve to apply it. A snapshot is taken first, "
                                    "then an available sibling test runs automatically."
                                ),
                            },
                            "text": f"Approval required to apply an edit to {ev.get('filepath', '')}",
                            "requiresApproval": True,
                        }
                    elif creation is not None:
                        token = approvals.issue("create", creation, session_id)
                        # A create_file approval: surface the all-additions diff + the
                        # {filepath, content} pair so the UI shows the new file and
                        # re-sends it as an approved creation on resume (a snapshot is
                        # taken before writing, so the new file stays revertible).
                        payload = {
                            "input": {
                                "creations": [creation],
                                "approvalToken": token,
                                "diff": ev.get("diff", ""),
                                "explanation": (
                                    "The agent wants to create a new file. Review the "
                                    "contents and approve to write it. A snapshot is "
                                    "taken first, then an available sibling test runs "
                                    "automatically."
                                ),
                            },
                            "text": f"Approval required to create {ev.get('filepath', '')}",
                            "requiresApproval": True,
                        }
                    else:
                        token = approvals.issue("command", {"command": cmd}, session_id)
                        payload = {
                            "input": {
                                "commands": [cmd],
                                "approvalToken": token,
                                "explanation": (
                                    "The agent wants to run a caution-level command "
                                    "(e.g. a package install, git write, or file "
                                    "change). Review it and approve to let it run."
                                ),
                            },
                            "text": f"Approval required to run: {cmd}",
                            "requiresApproval": True,
                        }
                except ApprovalError as exc:
                    logger.warning("Approval payload refused before token issue", exc_info=exc)
                    approvals.clear_session(session_id)
                    yield sse("error", {"text": f"Approval request refused: {exc}"})
                    return
                try:
                    development.record(
                        user_text,
                        "paused",
                        tool_calls=len(workflow_steps),
                        human_interventions=len(req.approval_tokens),
                        blocked_actions=blocked_actions,
                        metadata=_route_meta(),
                    )
                except Exception as exc:  # noqa: BLE001 - metrics must never break approval
                    logger.warning("Development metrics recording failed for paused turn", exc_info=exc)
                # A turn that pauses for approval and is never resumed must still
                # be counted -- otherwise every YELLOW-gated turn (a large share
                # of real traffic) silently vanishes from telemetry entirely.
                _record_telemetry(telemetry.OUTCOME_ABORTED)
                yield sse("human_required", payload)
            elif kind == "done":
                # 4. Persist the answer (L2) and consolidate the turn into L3.
                answer = "".join(answer_parts)
                _record_episode(session_id, "assistant", answer)
                _index_turn(indexer, user_text, answer)
                # The turn's outcome is the PER-TARGET final verdict: for every
                # target that was verified this turn, its LAST verdict must be
                # PASS. A turn that fails, self-corrects, and re-verifies the
                # same target green IS a verified success — the loop's whole
                # design is verify -> reflect -> fix (operator decision
                # 2026-06-11, refined the same day from global last-evidence-
                # wins) — but a final PASS on one target can no longer mask an
                # unresolved FAIL on another.
                if not verification_evidence:
                    record_outcome("unverified")
                    _record_telemetry(telemetry.OUTCOME_UNVERIFIED)
                else:
                    # The FORCED auto-verify is authoritative; fall back to the
                    # model's own verify only when nothing was auto-verified.
                    authoritative = auto_verdicts or verify_verdicts
                    if any(v == "FAIL" for v in authoritative.values()):
                        record_outcome("verified_failure")
                        _record_telemetry(telemetry.OUTCOME_FAIL)
                    else:
                        record_outcome("verified_success")
                        _record_telemetry(telemetry.OUTCOME_PASS)
                # B5 growth: announce curriculum mastery so the body's lattice
                # can harden. Additive frame; fires only on the transition and
                # only under the STRONG promotion floor (gated inside
                # record_matching), so a weak green can never make the body
                # celebrate growth that did not happen.
                for mastered_skill, mastered_level in mastered_levels:
                    yield sse(
                        "skill.mastered",
                        {
                            "skill": mastered_skill,
                            "level": mastered_level,
                            "source": "curriculum",
                        },
                    )
                approvals.clear_session(session_id)
                turn_state.clear(session_id)
                yield sse("done", {})
                # Cortex bus W2: emit a cold-path observation AFTER the done
                # frame so the hot path is never delayed. Best-effort and
                # completely skipped when CORTEX_BUS is off (the default).
                _append_turn_completed(_cortex_bus, session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- /api/v1/chat input-shield: per-session sliding-window flood throttle ----
# The voice/chat path is the one endpoint that takes free-form operator text and
# fans it straight at a (possibly cloud) provider with the operator's recalled
# facts attached. The Pydantic ``max_length`` cap bounds a single turn; this
# bounds the RATE so a stuck client (or a tab left auto-sending) cannot flood the
# router. It is deliberately lightweight and in-process (best-effort, per-worker),
# distinct from the durable security RateLimiter that governs RED actions.
_CONVERSATION_RATE_WINDOW_S = 60.0
_CONVERSATION_RATE_MAX = 30
_CONVERSATION_HITS: dict[str, list[float]] = {}


def _enforce_conversation_rate_limit(session_id: str) -> None:
    """Raise HTTP 429 if a session exceeds ``_CONVERSATION_RATE_MAX`` turns per window.

    A simple monotonic sliding window keyed by session id. Best-effort and
    in-process; the deterministic security cage (gateway, scope lock, audit) is
    unaffected — this only protects the conversational fan-out from flooding.
    """
    now = time.monotonic()
    cutoff = now - _CONVERSATION_RATE_WINDOW_S
    # BUG-F fix: evict fully-expired sessions so the map can't grow without bound
    # as fresh session ids keep arriving (each browser session mints a new one).
    # Previously every session left a key forever. This bounds the map to
    # sessions active within the window.
    for sid in [
        s for s, ts in _CONVERSATION_HITS.items() if not any(t > cutoff for t in ts)
    ]:
        del _CONVERSATION_HITS[sid]
    hits = [t for t in _CONVERSATION_HITS.get(session_id, ()) if t > cutoff]
    if len(hits) >= _CONVERSATION_RATE_MAX:
        _CONVERSATION_HITS[session_id] = hits
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many conversation turns; slow down. "
                f"Limit is {_CONVERSATION_RATE_MAX} per {int(_CONVERSATION_RATE_WINDOW_S)}s."
            ),
        )
    hits.append(now)
    _CONVERSATION_HITS[session_id] = hits


def _check_prompt_injection(text: str) -> Optional[str]:
    """Return the gateway reason if *text* is a prompt injection, else None.

    Uses the public ``classify()`` API so the regex list and optional vector
    shield are reused without editing frozen-core gateway code. Non-injection
    RED results (e.g. ``unknown command``) are ignored — normal conversation
    must not be blocked.
    """
    if not text or not isinstance(text, str):
        return None
    result = classify(text)
    if result.zone is Zone.RED and (
        "prompt-injection" in result.reason.lower()
        or "semantic prompt-injection" in result.reason.lower()
    ):
        return result.reason
    return None


def _stream_chat_chunks(
    chat_client: Any,
    messages: list[dict[str, Any]],
    *,
    model: str,
) -> Iterator[str]:
    """Yield real chat chunks when available, else preserve word streaming."""
    stream_fn = getattr(chat_client, "stream_chat", None)
    if callable(stream_fn):
        for chunk in stream_fn(messages, tools=None, model=model):
            text = str(chunk)
            if text:
                yield text
        return

    reply = chat_client.chat(messages, tools=None, model=model)
    text = str((reply or {}).get("content", "")).strip() or "(no answer)"
    for word in re.findall(r"\S+\s*", text):
        yield word


@app.post("/api/v1/chat")
def chat(
    req: ChatRequest,
    request: Request,
    client: OllamaClient = Depends(get_ollama_client),
    bedrock: Optional[BedrockClient] = Depends(get_bedrock_client),
    gemini: Optional[GeminiClient] = Depends(get_gemini_client),
    openai_client: Optional[Any] = Depends(get_openai_client),
    anthropic_client: Optional[Any] = Depends(get_anthropic_client),
    indexer: Optional[SemanticMemory] = Depends(get_semantic_indexer),
    facts: SemanticFacts = Depends(get_semantic_facts),
    compactor: MemoryCompactor = Depends(get_compactor),
) -> StreamingResponse:
    """Stream a lean Hinglish conversational reply (the GAGOS voice mind).

    This is CONVERSATION, not the agentic forge: it reuses the cross-provider
    router (so the operator's local-first privacy gate is fully intact), recalls
    relevant memory, and injects REAL personalization facts, then calls the chat
    client ONCE for a single reply — NO ``ToolAgent`` loop, NO file-write/coding
    tools. Providers with streaming support forward real chunks; non-streaming
    clients fall back to word-by-word chunks so every route keeps one wire shape.
    Frames, in order:

      * ``route``       — the provider/model that served + a privacy indicator.
      * ``text_chunk``  — the reply, as a sequence of ``{"text": ...}`` frames.
      * ``done``        — terminal frame (``{}``), or ``error`` on transport failure.

    The user + assistant turns are persisted to L2 episodic memory and the
    completed turn is embedded into L3 (self-reinforcing recall), exactly like
    ``/api/generate``. Best-effort persistence never breaks the chat.
    """
    session_id = _session_id_from_request(request, req.session_id)
    compactor.touch_working_session(session_id)
    _enforce_conversation_rate_limit(session_id)
    user_text = req.transcript.strip()
    if (injection_reason := _check_prompt_injection(user_text)):
        raise HTTPException(status_code=400, detail=f"[SECURITY BLOCK] {injection_reason}")
    # Route by purpose (general for chitchat, coding for code talk, etc.). The
    # privacy gate lives inside _select_chat_client via _router_policy(): with the
    # default empty ROUTER_CLOUD_TASKS, `auto` stays local-only. Never force cloud.
    task = infer_task(user_text)
    chat_client, model = _select_chat_client(
        req.model_id, client, bedrock, gemini=gemini,
        openai=openai_client, anthropic=anthropic_client, task=task,
    )
    _, model = _active_route(chat_client, bedrock, gemini, model,
                             openai=openai_client, anthropic=anthropic_client)

    def event_stream() -> Iterator[str]:
        sse = _sse_writer(session_id)
        # Telemetry (Phase 1 lap-counter, roadmap SS1): this endpoint has no tool
        # loop and never verifies anything, so dispatch_path is always `llm` and
        # verified_outcome is always `unverified` -- except a turn that never
        # reached the model (empty transcript / a transport failure), which is
        # honestly counted as `aborted` rather than silently producing zero rows.
        _turn_started = time.perf_counter()

        def _record_chat_telemetry(verified_outcome: str) -> None:
            provider, served_model = _active_route(
                chat_client, bedrock, gemini, model,
                openai=openai_client, anthropic=anthropic_client,
            )
            telemetry.record_run(
                session_id=session_id,
                task_signature=task_signature(user_text) if user_text else None,
                dispatch_path=telemetry.DISPATCH_LLM,
                provider=provider,
                model=served_model,
                verified_outcome=verified_outcome,
                latency_ms=round((time.perf_counter() - _turn_started) * 1000),
            )

        if not user_text:
            _record_chat_telemetry(telemetry.OUTCOME_ABORTED)
            yield sse("error", {"text": "No transcript provided."})
            return

        # Build the conversational system prompt via PromptWriter: prioritized,
        # budgeted sections assembled declaratively.
        from aios.core.prompt_writer import PromptSection, PromptWriter

        prompt_sections = [
            PromptSection(
                name="operator_facts",
                priority=90,
                render=lambda: _operator_facts_block(facts),
                max_tokens=800,
            ),
            PromptSection(
                name="recall",
                priority=70,
                render=lambda: _recall_memory(user_text),
                max_tokens=1500,
            ),
        ]
        system_prompt = PromptWriter(
            CHAT_SYSTEM_PROMPT, prompt_sections, total_budget=4000
        ).assemble(user_text)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

        _record_episode(session_id, "user", user_text)

        # The ACTIVE BRAIN for this turn (the UI 'voyaging mind' badge): provider/
        # model that actually served + privacy indicator. For streaming clients,
        # the first chunk proves which failover candidate won; route is still the
        # first frame emitted, but it is not guessed before the provider answers.
        route_sent = False
        text_parts: list[str] = []

        def route_payload() -> dict[str, Any]:
            active_provider, active_model = _active_route(
                chat_client, bedrock, gemini, model,
                openai=openai_client, anthropic=anthropic_client,
            )
            return {
                "provider": active_provider,
                "model": active_model,
                "privacy": "local" if active_provider == router.PROVIDER_OLLAMA else "cloud",
                "task": task,
                "auto": req.model_id in _AUTO_IDS,
            }

        # ONE no-tool chat stream => pure text, no tool loop, no file writes.
        try:
            for chunk in _stream_chat_chunks(chat_client, messages, model=model):
                if not route_sent:
                    yield sse("route", route_payload())
                    route_sent = True
                text_parts.append(chunk)
                yield sse("text_chunk", {"text": chunk})
        except LLMError as exc:
            _record_chat_telemetry(telemetry.OUTCOME_ABORTED)
            yield sse("error", {"text": str(exc)})
            return

        if not route_sent:
            yield sse("route", route_payload())
        text = "".join(text_parts).strip()
        if not text:
            text = "(no answer)"
            yield sse("text_chunk", {"text": text})

        _record_episode(session_id, "assistant", text)
        _index_turn(indexer, user_text, text)
        if config.FACTS_AUTO_EXTRACT:
            try:
                proposed_count = 0
                for s, p, o in extract_candidates(
                    user_text,
                    max_candidates=config.FACTS_AUTO_EXTRACT_MAX_PER_TURN,
                ):
                    result = facts.strengthen_or_propose(s, p, o)
                    if result.proposed or result.reason == "strengthened":
                        proposed_count += 1
                if proposed_count and _cortex_bus:
                    _cortex_bus.append(
                        "facts.proposed", session_id,
                        {"count": proposed_count, "source": "chat"},
                    )
            except Exception:
                logger.warning("Chat fact extraction failed", exc_info=True)
        _record_chat_telemetry(telemetry.OUTCOME_UNVERIFIED)
        yield sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/terminal")
def terminal(
    req: TerminalRequest,
    executor: Executor = Depends(get_executor),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Run a UI-terminal command through the security gateway + sandbox.

    Returns the front-end terminal's ``{output, isError}`` shape. The command is
    classified and gated exactly like an agent action: RED is blocked, YELLOW is
    reported as needing approval, and only GREEN runs in the scope-locked
    sandbox. Every outcome is audited by the executor.
    """
    result = executor.execute(req.command, session_id=req.session_id)

    if result.status == "OK":
        output = (result.stdout or "") + (result.stderr or "")
        return {
            "output": output.strip() or "(no output)",
            "isError": bool(result.exit_code),
        }
    if result.status == "REQUIRE_APPROVAL":
        if not req.session_id:
            raise HTTPException(
                status_code=400,
                detail="sessionId is required to approve a YELLOW command",
            )
        token = approvals.issue("command", {"command": req.command}, req.session_id)
        return {
            "output": f"[APPROVAL REQUIRED] {result.reason}",
            "isError": False,
            "requiresApproval": True,
            "approvalToken": token,
            "command": req.command,
        }
    # BLOCKED / TIMEOUT / ERROR
    return {"output": f"[{result.status}] {result.reason}", "isError": True}


# Re-exports for backward compat — tests import these from aios.api.main
from aios.api.routes.voice import _get_stt_service, _get_tts_service  # noqa: F401, E402
from aios.api.routes.council import get_council_runtime_root  # noqa: F401, E402
