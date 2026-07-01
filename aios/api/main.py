"""FastAPI orchestration layer for the AI OS.

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
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional, Any, Sequence, cast

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import aios
from aios import config
from aios.logging_config import configure_logging, get_logger, session_log_key
from aios.core.metrics import CONTENT_TYPE_LATEST, MetricsCollector, MetricsMiddleware, generate_latest, get_collector
from aios.agents.reflection_agent import ReflectionAgent, ReflectionError
from aios.agents.rollback_engine import RollbackEngine, RollbackError
from aios.agents.role_pass import run_role_pass
from aios.agents.swarm import run_swarm
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.agents.tool_agent import ToolAgent
from aios.core.autonomy import AutonomyLedger
from aios.core.executor import (
    Executor,
    approved_runner_from_config,
    validate_approved_execution_backend,
)
from aios.core.events import event_for_sse
from aios.core import catalog, router
from aios.core.bedrock import BedrockClient
from aios.core.gemini import CURATED_MODELS as GEMINI_CURATED_MODELS
from aios.core.gemini import GeminiClient
from aios.core.llm import LLMClient, LLMError, OllamaClient
from aios.core.websearch import web_search
from aios.core.model_selector import (
    TASK_FAST,
    TASKS,
    describe_choice,
    infer_task,
    select_model,
    supports_tool_protocol,
)
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
    validate_user_corrections,
)
from aios.core.planner import Planner, PlannerError
from aios.core.self_apply import DEFAULT_VERIFY_COMMAND, SelfApplyEngine
from aios.core.session_manager import SessionManager
from aios.core.verifier import Verifier
from aios.memory.db import get_connection, init_memory_db
from aios.memory.alignment_evaluation import AlignmentEvaluationStore
from aios.memory.compaction import MemoryCompactor
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.conversation import ConversationStateStore
from aios.memory.curriculum import CurriculumManager
from aios.memory.development import DevelopmentTracker
from aios.memory.mistake import MistakeMemory
from aios.memory.self_model import render as render_self_model, synthesize_self_model
from aios.memory.embeddings import VectorIndex
from aios.memory.episodic import EpisodicMemory
from aios.memory.facts import SemanticFacts
from aios.memory.crag import (
    CragAction,
    evaluate_retrieval,
    external_retrieve,
    refine_context,
)
from aios.memory.retrieval import hybrid_search
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory
from aios.memory.working import WorkingMemory
from aios.runtime.contracts import KingReport, RunLedger
from aios.runtime.king_report import KingReportStore
from aios.runtime.run_ledger import RunLedgerStore
from aios.runtime.snapshots import SnapshotManager
from aios.council import CouncilMissionRequest, CouncilOrchestrator
from aios.council.council_state import CouncilState
from aios.council.queen_verdict import has_blocking_verdict
from aios.core.verification_strength import (
    VerificationStrength,
    meets_promotion_floor,
    strength_from_text,
)
from aios.security.audit_logger import init_audit_db, log_action, verify_chain
from aios.security.gateway import RateLimiter, Zone, classify
from aios.security.secret_scanner import scan_and_redact

_APPROVALS = ApprovalStore(db_path=config.APPROVAL_DB_PATH)
_RATE_LIMITER = RateLimiter(db_path=config.APPROVAL_DB_PATH)

#: Server-side session manager with httpOnly cookie support.
#: Sessions are stored by SHA-256 hash only; the raw ID never leaves the server
#: except inside the httpOnly cookie response, and is never persisted.
_SESSION_MANAGER = SessionManager(
    max_age=3600,
    cleanup_interval=300,
    store_path=config.SESSION_DB_PATH,
)

#: Cloud chat-client singletons. Built lazily and reused across requests so we do
#: not re-run boto3/gcloud credential discovery on every turn. Enablement is still
#: checked per request so setting changes take effect without editing this module.
_bedrock_client: Optional[BedrockClient] = None
_gemini_client: Optional[GeminiClient] = None
_bedrock_lock = threading.Lock()
_gemini_lock = threading.Lock()

logger = get_logger(__name__)
_METRICS = get_collector()


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
    yield


app = FastAPI(
    title="GAGOS - AI OS",
    version=aios.__version__,
    summary="Local-first, memory-driven, security-gated, human-supervised AI OS.",
    lifespan=lifespan,
)

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
# Protects against brute-force on approval tokens and DoS on execute/reflect.
# Best-effort, per-process; the durable RateLimiter governs RED actions.
# --------------------------------------------------------------------------- #
_RATE_LIMIT_WINDOW_S = 60.0
_RATE_LIMIT_ENDPOINTS: dict[str, int] = {
    "/api/v1/approval/req": 10,
    "/api/v1/execute": 30,
    "/api/terminal": 20,
    # Council origination/decisions: IP-keyed cap (the per-session throttle is
    # spoofable by varying sessionId) — bounds mission/worker spawn floods.
    "/api/v1/council/missions": 20,
    "/api/v1/council/approve": 30,
    "/api/v1/council/reject": 30,
}
_RATE_LIMIT_HITS: dict[str, list[tuple[str, float]]] = {}
_RATE_LIMIT_LOCK = threading.Lock()


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
        path = request.url.path
        if path in _RATE_LIMIT_ENDPOINTS:
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


def get_session_manager() -> SessionManager:
    """Provide the server-side session manager singleton."""
    return _SESSION_MANAGER


def _session_id_from_request(request: Request, fallback: Optional[str] = None) -> str:
    """Prefer the validated httpOnly session cookie, then body fallback.

    Cookie-based browser clients should not expose a session id in JavaScript.
    The fallback keeps older local callers working when cookies are unavailable.
    """
    cookie_hash = request.cookies.get("session_id")
    if cookie_hash:
        session = get_session_manager().validate_session(cookie_hash)
        if session is not None:
            return session.session_hash
    return fallback or ""


def _effective_rollback_snapshot(
    engine: RollbackEngine, requested: Optional[str]
) -> str:
    """Resolve the rollback target before approval so the token binds a SHA."""
    if requested:
        return requested
    snapshots = engine.list_snapshots(limit=2)
    if len(snapshots) < 2:
        raise HTTPException(
            status_code=409,
            detail="No previous snapshot to roll back to.",
        )
    return snapshots[1].sha


def get_llm_client() -> LLMClient:
    """Provide the default local LLM client. Overridden in tests."""
    return OllamaClient()


def get_ollama_client() -> OllamaClient:
    """Provide a concrete Ollama client for streaming + model discovery.

    Distinct from :func:`get_llm_client` (which yields the minimal protocol) so
    the chat/discovery endpoints can use streaming and ``/api/tags`` while
    remaining overridable in tests.
    """
    return OllamaClient()


def get_bedrock_client() -> Optional[BedrockClient]:
    """Provide the AWS Bedrock cloud chat client, or ``None`` when unconfigured.

    Returns ``None`` unless Bedrock is opted in (region + model set) *and* boto3
    is importable — so the agent transparently stays on local inference when the
    cloud isn't set up. Overridden in tests with a fake.

    The client is built lazily and reused across requests; enablement is checked
    fresh each call (mirrors :func:`_router_policy`).
    """
    global _bedrock_client
    if not (config.BEDROCK_REGION and config.BEDROCK_MODEL):
        return None
    if _bedrock_client is not None:
        return _bedrock_client
    with _bedrock_lock:
        if _bedrock_client is not None:
            return _bedrock_client
        try:
            _bedrock_client = BedrockClient()
        except LLMError:
            return None
    return _bedrock_client


def get_gemini_client() -> Optional[GeminiClient]:
    """Provide the Google Gemini (Vertex AI) chat client, or ``None`` when unset.

    Returns ``None`` unless Gemini is opted in (a GCP project is set) *and* the
    ``google-genai`` SDK is importable — so the agent transparently stays on
    local/Bedrock inference when Gemini isn't configured. Auth is the laptop's
    ``gcloud`` ADC; this never touches a key on disk. Overridden in tests.

    The client is built lazily and reused across requests; enablement is checked
    fresh each call (mirrors :func:`_router_policy`).
    """
    global _gemini_client
    if not (config.GEMINI_PROJECT and config.GEMINI_MODEL):
        return None
    if _gemini_client is not None:
        return _gemini_client
    with _gemini_lock:
        if _gemini_client is not None:
            return _gemini_client
        try:
            _gemini_client = GeminiClient()
        except LLMError:
            return None
    return _gemini_client


def get_executor() -> Executor:
    """Provide the default scope-constrained executor. Overridden in tests."""
    return Executor(
        approved_runner=approved_runner_from_config(),
        rate_limiter=_RATE_LIMITER,
    )

def get_approval_store() -> ApprovalStore:
    """Provide the durable local multi-worker approval capability store."""
    return _APPROVALS


def get_rollback_engine() -> RollbackEngine:
    """Provide the default sandbox rollback engine. Overridden in tests."""
    return RollbackEngine()


def get_self_apply_engine(
    executor: Executor = Depends(get_executor),
) -> SelfApplyEngine:
    """Provide the Self-Analysis T3 apply engine (verifies via the gated Executor).

    The engine is the ONLY way an approved proposal reaches the real ``aios/`` source
    — there is deliberately no agent tool that applies. Overridden in tests with a
    fake verifier + temp project root so no real shell/suite runs.
    """
    isolated_runner = approved_runner_from_config()

    def project_root_runner(
        command: str, *, cwd: str, env: dict[str, str], timeout_s: int
    ) -> tuple[str, str, int]:
        """Run self-apply verification from the project root, after gateway approval.

        ``SelfApplyEngine`` verifies changes to ``aios/`` with ``pytest tests/``.
        The ordinary agent executor intentionally runs in ``training_ground/``;
        using that cwd would look for ``training_ground/tests`` and roll back good
        proposals. The command still passes through the same Executor gateway and
        audit path before this runner is invoked.

        Phase 2 — self-apply is CONTAINER-ONLY. It is the single path by which an
        approved proposal reaches real ``aios/`` source, so it must never verify (and
        thus never apply) on the bare host. In host mode (``isolated_runner is None``)
        it REFUSES; the proposal is rolled back. The verify suite runs INSIDE the
        container with a container-appropriate interpreter (the host ``.venv`` path
        in ``DEFAULT_VERIFY_COMMAND`` does not exist in the image), with the real
        project root bind-mounted so it tests the proposed change.
        """
        if command != DEFAULT_VERIFY_COMMAND:
            raise ValueError("self-apply verifier accepts only the fixed project test command")
        if isolated_runner is None:
            raise RuntimeError(
                "self-apply requires the container execution boundary; host mode "
                "refuses (set AIOS_APPROVED_EXECUTION_BACKEND=container and start the "
                "container runtime to apply proposals)"
            )
        return isolated_runner(
            "python -m pytest tests/ -q",
            cwd=str(config.PROJECT_ROOT),
            env=env,
            timeout_s=timeout_s,
        )

    verify_executor = Executor(
        runner=project_root_runner,
        timeout_s=120,
        actor="self-apply-verifier",
    )
    return SelfApplyEngine(verifier=Verifier(verify_executor))


def get_edit_snapshot() -> Callable[..., object]:
    """Provide the pre-edit snapshot hook for the agent's ``edit_file`` tool.

    Returns a callable that lazily constructs a sandbox :class:`RollbackEngine`
    and snapshots it — only when an approved edit is actually applied, so read /
    command turns pay nothing. Fail-closed: a snapshot failure propagates so the
    agent refuses the edit (no unprotected write). Overridden in tests with a recorder.
    """
    def snapshot(message: str = "pre-edit snapshot") -> None:
        # Let failures propagate: the agent treats a snapshot error as fail-closed
        # and refuses the edit, so a write is never applied without a captured
        # pre-edit state to roll back to.
        RollbackEngine().create_snapshot(message)

    return snapshot


def get_semantic_indexer() -> Optional[SemanticMemory]:
    """Provide the L3 semantic writer used to index completed chat turns.

    Returns ``None`` when :data:`aios.config.INDEX_CHAT` is disabled (so no
    embedding model is loaded). Overridden in tests with a fake recorder so the
    suite never loads the real embedder or mutates the on-disk vector index.
    """
    return SemanticMemory() if config.INDEX_CHAT else None


def get_reflection_agent(
    llm: LLMClient = Depends(get_llm_client),
) -> Optional[ReflectionAgent]:
    """Provide the reflection agent that turns a command failure into a lesson.

    Returns ``None`` when :data:`aios.config.REFLECT_ON_FAILURE` is disabled.
    Reuses the injected LLM client so it is fully overridable in tests.
    """
    return ReflectionAgent(llm) if config.REFLECT_ON_FAILURE else None


def get_development_tracker() -> DevelopmentTracker:
    """Provide the evidence-backed developmental metrics store."""
    return DevelopmentTracker()


def get_skill_memory() -> SkillMemory:
    """Provide verification-backed procedural skill memory."""
    return SkillMemory()


def get_swarm_pattern_memory() -> SwarmPatternMemory:
    """Provide the ant-colony swarm's decomposition-pattern memory."""
    return SwarmPatternMemory()


def get_semantic_facts() -> SemanticFacts:
    """Provide the human-approved personalization facts store (REAL only).

    Reads the ``semantic_facts`` table (human-gated writes); returns an empty
    list when no facts exist, so the conversational endpoint stays honest —
    personalization is dormant, never fabricated, when nothing is known. Cheap
    and stateless (opens a fresh connection per call). Overridden in tests.
    """
    return SemanticFacts()


def get_autonomy() -> AutonomyLedger:
    """Provide the earned-autonomy ledger (opt-in; off => never grants autonomy)."""
    return AutonomyLedger()


def get_curriculum_manager() -> CurriculumManager:
    """Provide the non-autonomous curriculum evidence store."""
    return CurriculumManager()


def get_memory_consolidator() -> MemoryConsolidator:
    """Provide the evidence-gated trusted-memory promotion service."""
    return MemoryConsolidator()


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


def get_conversation_state_store() -> ConversationStateStore:
    """Provide durable, unverified shared-understanding state."""
    return ConversationStateStore()


def get_alignment_evaluation_store() -> AlignmentEvaluationStore:
    """Provide diagnostic human-alignment evidence; it never changes policy."""
    return AlignmentEvaluationStore()


def get_council_runtime_root() -> Path:
    """Runtime artifact root for Council missions."""
    config.COUNCIL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return config.COUNCIL_RUNTIME_DIR


def get_alignment_interpreter(
    llm: LLMClient = Depends(get_llm_client),
) -> Optional[AlignmentInterpreter]:
    """Provide the advisory per-turn alignment interpreter.

    Returns ``None`` when :data:`aios.config.INTERPRET_ALIGNMENT` is disabled,
    so a generated turn costs no extra local completion. Reuses the injected
    LLM client so tests override it with fakes.
    """
    return AlignmentInterpreter(llm) if config.INTERPRET_ALIGNMENT else None


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class MemorySearchRequest(BaseModel):
    """Body for ``/memory/search``."""

    query: str = Field(..., description="Natural-language search query.")
    top_k: int = Field(3, ge=1, le=50, description="Number of results to return.")


class MemoryCompactRequest(BaseModel):
    """Body for ``/memory/compact``."""

    dry_run: bool = Field(
        True,
        description="When True, preview what would be removed. False performs the sweep.",
    )


class ClassifyRequest(BaseModel):
    """Body for ``/security/classify``."""

    command: str = Field(..., description="Action payload to classify.")


class ReflectRequest(BaseModel):
    """Body for ``/reflect``."""

    command: str = Field(..., description="The action/command that failed.")
    error_output: str = Field(..., description="Captured error text.")
    task_id: Optional[str] = Field(None, description="Stable id for recurrence detection.")


class PlanRequest(BaseModel):
    """Body for ``/plan``."""

    goal: str = Field(..., description="High-level goal to decompose into steps.")


class ExecuteRequest(BaseModel):
    """Body for ``/execute``."""

    command: str = Field(..., description="Command to classify, gate, and run.")
    session_id: Optional[str] = Field(
        None,
        alias="sessionId",
        description="Required for a YELLOW command's server-issued approval capability.",
    )

    model_config = {"populate_by_name": True}


class ApprovalRequest(BaseModel):
    """Body for ``/approval/req`` — a human's decision on an escalated action."""

    approval_token: str = Field(..., alias="approvalToken")
    session_id: Optional[str] = Field(
        None,
        alias="sessionId",
        description="Fallback session id when the httpOnly session cookie is unavailable.",
    )
    approve: bool = Field(..., description="True to authorise execution, False to reject.")

    model_config = {"populate_by_name": True}


class RollbackRequest(BaseModel):
    """Body for ``/rollback``."""

    snapshot_id: Optional[str] = Field(
        None, description="Target snapshot SHA; defaults to the previous snapshot."
    )
    approval_token: Optional[str] = Field(
        None, alias="approvalToken",
        description="Server-issued approval token authorising this destructive operation.",
    )
    session_id: Optional[str] = Field(
        None, alias="sessionId", description="Session that requested rollback."
    )

    model_config = {"populate_by_name": True}


class ApplyProposalRequest(BaseModel):
    """Body for the Self-Analysis T3 apply endpoint — the HUMAN approver's id."""

    approved_by: str = Field("", alias="approvedBy")

    model_config = {"populate_by_name": True}


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

    Conversation only (the Jarvis voice mind, Slice 1): a single ``transcript``
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


class FactPromotionRequest(BaseModel):
    """Body for human-approved contradiction-aware fact promotion."""

    subject: str
    predicate: str
    object: str
    approved_by: str = Field(..., alias="approvedBy")

    model_config = {"populate_by_name": True}


class CurriculumTaskRequest(BaseModel):
    """Body for defining a safe curriculum task; definitions never auto-run."""

    skill_name: str = Field(..., alias="skillName")
    level: int = Field(..., ge=1)
    prompt: str
    held_out: bool = Field(False, alias="heldOut")

    model_config = {"populate_by_name": True}


class CouncilDecisionRequest(BaseModel):
    """King decision for a Council mission or pending worker approval request."""

    mission_id: str = Field(..., alias="missionId")
    request_id: str | None = Field(None, alias="requestId")
    reason: str = ""

    model_config = {"populate_by_name": True}


class CouncilRollbackRequest(BaseModel):
    """Approval-gated restore of a Council mission workspace."""

    snapshot_id: Optional[str] = Field(None, alias="snapshotId")
    approval_token: Optional[str] = Field(None, alias="approvalToken")
    session_id: Optional[str] = Field(None, alias="sessionId")

    model_config = {"populate_by_name": True}


class CouncilMissionOriginationRequest(BaseModel):
    """Body for ``POST /api/v1/council/missions`` — originate a council mission.

    Scope is EXPLICIT and operator-provided (never LLM-inferred): allowedFiles is
    required and validated to stay inside the council workspace.
    """

    goal: str = Field(..., min_length=1, max_length=2000)
    allowed_files: list[str] = Field(..., alias="allowedFiles", min_length=1)
    workspace_root: Optional[str] = Field(None, alias="workspaceRoot")
    forbidden_files: list[str] = Field(
        default_factory=lambda: ["backend/", ".env", "aios/security/"],
        alias="forbiddenFiles",
    )
    verification_commands: list[str] = Field(
        default_factory=list, alias="verificationCommands"
    )
    risk_level: str = Field("YELLOW", alias="riskLevel")
    session_id: str = Field("council-session", alias="sessionId")

    model_config = {"populate_by_name": True}


class ConversationSessionRequest(BaseModel):
    """Request restoration of one durable conversation session."""

    session_id: str = Field(..., min_length=1, alias="sessionId")
    limit: int = Field(50, ge=1, le=100)

    model_config = {"populate_by_name": True}


class ConversationCorrectionRequest(BaseModel):
    """User-authored corrections to the current advisory interpretation."""

    session_id: str = Field(..., min_length=1, alias="sessionId")
    corrections: dict[str, Any]

    model_config = {"populate_by_name": True}


class AlignmentFeedbackRequest(BaseModel):
    """Explicit human evaluation of the latest visible understanding frame."""

    session_id: str = Field(..., min_length=1, alias="sessionId")
    observation_id: Optional[int] = Field(None, ge=1, alias="observationId")
    outcome: str
    issues: list[str] = Field(default_factory=list)
    notes: str = Field("", max_length=2000)

    model_config = {"populate_by_name": True}


class IntentPreviewRequest(BaseModel):
    """Body for ``/api/v1/intent/preview`` — a lightweight rule-based prediction
    of what the operator is about to ask, so the UI can hint the dock before the
    turn is even sent. No LLM call; deterministic and cheap."""

    text: str = Field(..., max_length=2000, description="Operator's current draft.")


class IntentPreviewResponse(BaseModel):
    """Predicted intent class for the command dock."""

    intent: str = Field(..., description="chat | code | browse | swarm | command")
    confidence: float = Field(..., ge=0, le=1)
    tool: Optional[str] = Field(None, description="Primary tool if intent is actionable.")


class OnboardingStateResponse(BaseModel):
    """Read-only view of which product milestones the operator has reached."""

    firstDirective: bool
    firstApproval: bool
    firstVerify: bool
    firstCloudRoute: bool
    firstAutonomy: bool


class SessionCreateResponse(BaseModel):
    """Response from POST /api/v1/auth/session — session created."""

    authenticated: bool = Field(
        ..., description="True when the session is authenticated."
    )
    session_id: str = Field(
        ..., alias="sessionId", description="The session identifier (for cookie-based clients)."
    )
    cookie_based: bool = Field(
        True, alias="cookieBased",
        description="True when session travels via httpOnly cookie.",
    )
    warning: Optional[str] = Field(
        None,
        description="Security warning when cookie-less fallback is in use.",
    )

    model_config = {"populate_by_name": True}


class SessionStatusResponse(BaseModel):
    """Response from GET /api/v1/auth/session — current session status."""

    authenticated: bool = Field(
        ..., description="True when a valid session exists."
    )
    cookie_based: bool = Field(
        True, alias="cookieBased",
        description="True when session travels via httpOnly cookie.",
    )
    session_id: Optional[str] = Field(
        None, alias="sessionId",
        description="The session identifier (only when not cookie-based).",
    )

    model_config = {"populate_by_name": True}


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe."""
    return {"status": "ok", "version": aios.__version__}


@app.get("/metrics")
def metrics(
    tracker: DevelopmentTracker = Depends(get_development_tracker),
    approvals: ApprovalStore = Depends(get_approval_store),
    autonomy: AutonomyLedger = Depends(get_autonomy),
) -> Response:
    """Prometheus scrapable operational metrics."""
    _METRICS.update(
        tracker.summary(),
        approvals.grant_count(),
        autonomy.earned_count(),
        audit_db_path=config.AUDIT_DB_PATH,
    )
    return Response(
        content=generate_latest(_METRICS.registry),
        media_type=CONTENT_TYPE_LATEST,
    )


def _classify_intent(text: str) -> IntentPreviewResponse:
    """Rule-based intent preview for the command dock."""
    t = text.lower().strip()
    if not t:
        return IntentPreviewResponse(intent="chat", confidence=1.0, tool=None)
    if re.search(r"https?://|^(browse|search|look\s+up)\b", t):
        return IntentPreviewResponse(intent="browse", confidence=0.92, tool="browse")
    if re.search(r"\b(swarm|workers|plan\s+(out|it)|decompose|multi-agent)\b", t):
        return IntentPreviewResponse(intent="swarm", confidence=0.9, tool="swarm")
    if re.match(r"^(run|execute|install|pip|npm|git|python|bash|sh)\b", t):
        return IntentPreviewResponse(intent="command", confidence=0.85, tool="execute")
    if re.match(r"^(write|build|create|make|code|implement|fix|add|generate)\b", t):
        return IntentPreviewResponse(intent="code", confidence=0.9, tool="edit_file")
    return IntentPreviewResponse(intent="chat", confidence=0.8, tool=None)


@app.post("/api/v1/intent/preview")
def intent_preview(req: IntentPreviewRequest) -> IntentPreviewResponse:
    """Return a cheap, deterministic intent preview for the current draft."""
    return _classify_intent(req.text)


def _has_any_approval_grant(store: ApprovalStore) -> bool:
    """True if any approval has ever been redeemed (cross-session)."""
    if store.db_path is not None:
        with store._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM approval_grants").fetchone()
            return int(row["n"]) > 0
    with store._lock:
        return any(store._grants.values())


def _has_verified_success() -> bool:
    """True if any development event has outcome verified_success."""
    with get_connection(config.MEMORY_DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM development_events WHERE outcome = ?",
            ("verified_success",),
        ).fetchone()
        return int(row["n"]) > 0


def _has_cloud_route() -> bool:
    """True if a cloud-route audit entry has been recorded."""
    init_audit_db(config.AUDIT_DB_PATH)
    conn = sqlite3.connect(str(config.AUDIT_DB_PATH), timeout=30.0)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM tamper_audit_trail WHERE actor = ?",
            ("cloud-route",),
        ).fetchone()
        return int(row["n"]) > 0
    finally:
        conn.close()


@app.get("/api/v1/onboarding/state")
def onboarding_state(
    approvals: ApprovalStore = Depends(get_approval_store),
    autonomy: AutonomyLedger = Depends(get_autonomy),
) -> OnboardingStateResponse:
    """Return which first-run milestones have been reached."""
    ledger = autonomy.ledger_map()
    return OnboardingStateResponse(
        firstDirective=_EPISODIC.count(None) > 0,
        firstApproval=_has_any_approval_grant(approvals),
        firstVerify=_has_verified_success(),
        firstCloudRoute=_has_cloud_route(),
        firstAutonomy=ledger["summary"]["earned"] > 0,
    )


# --------------------------------------------------------------------------- #
# Session management — httpOnly Secure SameSite=Strict cookies (H2 hardening)
# --------------------------------------------------------------------------- #
# SECURITY: Session IDs are managed server-side and travel in httpOnly cookies
# that are completely inaccessible to JavaScript. This prevents XSS-based
# session theft (OWASP A07:2021). The raw session ID is never logged or exposed.
# --------------------------------------------------------------------------- #

def _set_session_cookie(response: Response, raw_session_id: str) -> str:
    """Set the session_id cookie with httpOnly, Secure, SameSite=Strict flags.

    Returns the cookie value (the SHA-256 hash) so it can be used as a
    session identifier in logs (the raw ID is never logged).
    """
    cookie_value = hashlib.sha256(raw_session_id.encode()).hexdigest()
    # In development (loopback) Secure=False so the cookie works over HTTP.
    # In production behind HTTPS, Secure=True is enforced by config check.
    secure = config.API_HOST not in {"127.0.0.1", "localhost", "::1"}
    response.set_cookie(
        key="session_id",
        value=cookie_value,
        httponly=True,          # NOT accessible to JavaScript — prevents XSS theft
        secure=secure,          # HTTPS only in production; loopback allows HTTP
        samesite="strict",      # NOT sent cross-origin — prevents CSRF
        max_age=3600,           # 1 hour
        path="/",             # Sent for all API paths
    )
    return cookie_value


@app.post("/api/v1/auth/session")
def create_session(
    response: Response,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionCreateResponse:
    """Create a new server-side session and set the httpOnly session cookie.

    The session ID is stored in an httpOnly, Secure, SameSite=Strict cookie.
    JavaScript cannot read this cookie, preventing XSS-based session theft.

    If cookies are blocked (e.g., privacy mode), the session ID is returned
    in the response body with a security warning — the client should fall
    back to sending it in the ``sessionId`` field of subsequent requests.
    """
    raw_id = manager.create_session()
    cookie_hash = _set_session_cookie(response, raw_id)
    return SessionCreateResponse(
        authenticated=True,
        session_id=cookie_hash,
        cookie_based=True,
    )


@app.get("/api/v1/auth/session")
def get_session_status(
    request: Request,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionStatusResponse:
    """Check whether the current session is valid.

    Returns ``authenticated: true`` when the request carries a valid
    session cookie. The frontend calls this on load to determine whether
    a session exists without needing to read the cookie directly
    (httpOnly cookies are invisible to JavaScript).
    """
    cookie_hash = request.cookies.get("session_id")
    session = manager.validate_session(cookie_hash)
    if session is not None:
        return SessionStatusResponse(
            authenticated=True,
            cookie_based=True,
        )
    return SessionStatusResponse(
        authenticated=False,
        cookie_based=True,
    )


@app.delete("/api/v1/auth/session")
def destroy_session(
    request: Request,
    response: Response,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    """Invalidate the current session (logout).

    Removes the session from server-side storage AND clears the cookie
    so the browser stops sending it.
    """
    cookie_hash = request.cookies.get("session_id")
    manager.invalidate_session(cookie_hash)
    response.delete_cookie(
        key="session_id",
        path="/",
        httponly=True,
        secure=config.API_HOST not in {"127.0.0.1", "localhost", "::1"},
        samesite="strict",
    )
    return {"authenticated": False}


@app.post("/api/v1/memory/search")
def memory_search(req: MemorySearchRequest) -> dict[str, Any]:
    """Hybrid BM25 + FAISS + temporal-decay retrieval over semantic memory."""
    results = hybrid_search(req.query, top_k=req.top_k)
    return {"query": req.query, "results": [asdict(r) for r in results]}


@app.post("/api/v1/memory/consolidate")
def memory_consolidate(
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
) -> dict[str, Any]:
    """Idempotently index current verified lessons and active approved facts."""
    return consolidator.run()


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


@app.post("/api/v1/conversation/session")
def restore_conversation_session(
    req: ConversationSessionRequest,
    state: ConversationStateStore = Depends(get_conversation_state_store),
) -> dict[str, Any]:
    """Restore recent dialogue and the latest unverified alignment frame."""
    rows = _EPISODIC.recent(req.session_id, req.limit)
    messages = [
        {"role": str(row["role"]), "content": [{"text": str(row["content"])}]}
        for row in rows
        if row["role"] in {"user", "assistant"}
    ]
    return {
        "alignment": state.get(req.session_id),
        "activeCorrection": state.active_correction(req.session_id),
        "correctionHistory": state.correction_history(req.session_id),
        "messages": messages,
    }


@app.post("/api/v1/conversation/correction")
def correct_conversation_alignment(
    req: ConversationCorrectionRequest,
    state: ConversationStateStore = Depends(get_conversation_state_store),
    evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
) -> dict[str, Any]:
    """Apply user-authored interpretation overrides; never grant authority."""
    current_payload = state.get(req.session_id)
    if current_payload is None:
        raise HTTPException(status_code=404, detail="no alignment frame exists for session")
    try:
        incoming = validate_user_corrections(req.corrections)
        active = state.active_correction(req.session_id)
        merged = dict(active["corrections"]) if active is not None else {}
        merged.update(incoming)
        current = frame_from_state(current_payload)
        corrected = apply_user_corrections(current, merged, revision=1)
        corrected_payload = corrected.as_dict()
        evaluation_payload = current_payload.get("evaluation")
        if isinstance(evaluation_payload, dict):
            corrected_payload["evaluation"] = evaluation_payload
        revision, persisted = state.record_correction(
            req.session_id,
            before_frame=current_payload,
            after_frame=corrected_payload,
            corrections=merged,
            corrected_fields=sorted(merged),
            expected_revision=(int(active["revision"]) if active is not None else None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        observation_id = (
            evaluation_payload.get("observation_id")
            if isinstance(evaluation_payload, dict)
            else None
        )
        evaluation.mark_latest_corrected(
            req.session_id,
            sorted(merged),
            observation_id=int(observation_id) if observation_id else None,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic evidence must never break correction
        logger.warning("Failed to mark alignment observation as corrected", exc_info=exc)
    return {
        "alignment": persisted,
        "activeCorrection": {
            "revision": revision,
            "corrections": merged,
            "fields": sorted(merged),
        },
        "correctionHistory": state.correction_history(req.session_id),
    }


@app.get("/api/v1/alignment/evaluation")
def alignment_evaluation_summary(
    evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
) -> dict[str, Any]:
    """Return diagnostic alignment evidence without changing policy."""
    return evaluation.summary()


@app.post("/api/v1/alignment/feedback")
def record_alignment_feedback(
    req: AlignmentFeedbackRequest,
    evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
) -> dict[str, Any]:
    """Record explicit operator feedback on the latest session observation."""
    try:
        observation_id = evaluation.record_feedback(
            req.session_id,
            outcome=req.outcome,
            issues=req.issues,
            notes=req.notes,
            observation_id=req.observation_id,
        )
    except ValueError as exc:
        status = 404 if "no alignment observation" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {
        "observationId": observation_id,
        "automaticPolicyUpdates": False,
    }


@app.post("/api/v1/conversation/correction/clear")
def clear_conversation_alignment_correction(
    req: ConversationSessionRequest,
    state: ConversationStateStore = Depends(get_conversation_state_store),
) -> dict[str, Any]:
    """Clear active user corrections and restore the superseded base frame."""
    try:
        restored = state.clear_correction(req.session_id)
        alignment = frame_from_state(restored).as_dict()
        evaluation_payload = restored.get("evaluation")
        if isinstance(evaluation_payload, dict):
            alignment["evaluation"] = evaluation_payload
        state.save(req.session_id, alignment)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "alignment": alignment,
        "activeCorrection": None,
        "correctionHistory": state.correction_history(req.session_id),
    }


@app.post("/api/v1/memory/facts")
def promote_fact(
    req: FactPromotionRequest,
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
) -> dict[str, Any]:
    """Promote one human-approved fact, refusing unresolved contradictions."""
    result = consolidator.promote_fact(
        req.subject, req.predicate, req.object, approved_by=req.approved_by
    )
    if result.reason == "contradiction":
        raise HTTPException(
            status_code=409,
            detail={
                "reason": result.reason,
                "conflictId": result.conflict_id,
                "conflictObject": result.conflict_object,
            },
        )
    if not result.committed:
        raise HTTPException(status_code=422, detail=result.reason)
    return asdict(result)


@app.post("/api/v1/memory/facts/reconcile")
def reconcile_fact(
    req: FactPromotionRequest,
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
) -> dict[str, Any]:
    """Human-approved replacement of a contradictory fact and its vector."""
    result = consolidator.reconcile_fact(
        req.subject, req.predicate, req.object, approved_by=req.approved_by
    )
    if not result.committed:
        raise HTTPException(status_code=422, detail=result.reason)
    return asdict(result)


@app.get("/api/v1/memory/facts/graph")
def memory_facts_graph(
    start: str,
    depth: int = 2,
    facts: SemanticFacts = Depends(get_semantic_facts),
) -> dict[str, Any]:
    """Multi-hop fact-graph traversal from *start* — the transitive reasoning
    single-hop ``facts_for`` cannot do (G1). Read-only: returns the active-fact
    edges reachable within *depth* hops, each with its hop ``depth`` and a
    ``path``, so the planner (or the lattice's fact view) can reason over
    transitive knowledge. ``depth`` is clamped to [1, 4] in ``traverse``."""
    if not start.strip():
        raise HTTPException(status_code=422, detail="start is required")
    rows = facts.traverse(start, max_depth=depth)
    edges = [
        {
            "subject": r["subject"],
            "predicate": r["predicate"],
            "object": r["object"],
            "depth": r["depth"],
            "path": r["path"],
        }
        for r in rows
    ]
    return {"start": start.strip(), "depth": max(1, min(int(depth), 4)), "edges": edges}


@app.get("/api/v1/development/metrics")
def development_metrics(
    tracker: DevelopmentTracker = Depends(get_development_tracker),
) -> dict[str, Any]:
    """Return measured behavior-change and verification coverage metrics."""
    return tracker.summary()


@app.get("/api/v1/development/skills")
def development_skills(
    status: Optional[str] = None,
    skills: SkillMemory = Depends(get_skill_memory),
) -> dict[str, Any]:
    """List candidate and verified procedural skills."""
    return {"skills": skills.list(status=status)}


@app.get("/api/v1/development/trails")
def development_trails(
    skills: SkillMemory = Depends(get_skill_memory),
) -> dict[str, Any]:
    """The pheromone map: every trail's computed strength, decay, and reuse
    evidence as of now, plus superseded-fragment lineage and the constants in
    effect — read-only observability and the tuning evidence base."""
    return skills.trail_map()


@app.get("/api/v1/development/workspace")
def development_workspace() -> dict[str, Any]:
    """The agent's manufacturing workspace: the text files currently in
    ``training_ground/`` (the agent's writable sandbox), most-recent first, with
    contents. Read-only observability so a UI (the forge editor) can show the
    mind's ACTUAL written files — independent of how the write landed (approval,
    earned-autonomy, or edit). Strictly confined to ``training_ground/`` (no path
    parameter, no traversal); skips caches/binaries and caps file count + size so
    the response stays small."""
    from pathlib import Path

    root = Path(config.PROJECT_ROOT) / "training_ground"
    text_exts = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json",
        ".md", ".txt", ".sh", ".yml", ".yaml", ".toml",
    }
    files: list[dict[str, str]] = []
    if root.is_dir():
        def _mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        candidates = [
            p for p in root.rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix.lower() in text_exts
        ]
        candidates.sort(key=_mtime, reverse=True)  # newest write first
        for p in candidates:
            try:
                if p.stat().st_size > 200_000:
                    continue
                content = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files.append({"path": p.relative_to(root).as_posix(), "content": content})
            if len(files) >= 16:
                break
    return {"root": "training_ground", "files": files}


@app.get("/api/v1/development/autonomy")
def development_autonomy(
    autonomy: AutonomyLedger = Depends(get_autonomy),
) -> dict[str, Any]:
    """The earned-autonomy ledger: which YELLOW action classes have graduated to
    autonomous execution by verified-success evidence, which are revoked, and the
    threshold + master switch in effect — read-only observability for the operator."""
    return autonomy.ledger_map()


@app.post("/api/v1/development/autonomy/revoke")
def development_autonomy_revoke(
    signature: str,
    autonomy: AutonomyLedger = Depends(get_autonomy),
) -> dict[str, Any]:
    """Operator force-revoke of an earned signature — human authority over the
    bridge stays absolute: any earned class can be pulled back to YELLOW at will."""
    return {"revoked": autonomy.revoke(signature)}


@app.get("/api/v1/development/curriculum")
def development_curriculum(
    skill_name: Optional[str] = None,
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
) -> dict[str, Any]:
    """List safe curriculum definitions and evidence state."""
    return {"tasks": curriculum.list(skill_name)}


@app.post("/api/v1/development/curriculum")
def add_curriculum_task(
    req: CurriculumTaskRequest,
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
) -> dict[str, Any]:
    """Define a curriculum task without executing it."""
    try:
        task_id = curriculum.add_task(
            req.skill_name, req.level, req.prompt, held_out=req.held_out
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": task_id, "executed": False}


def _validate_council_mission_id(mission_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", mission_id):
        raise HTTPException(status_code=422, detail="invalid mission id")
    # The charset above admits "." and "..", which the path layer would treat
    # as traversal out of the missions/ tree. Reject them explicitly.
    if mission_id in {".", ".."} or ".." in mission_id:
        raise HTTPException(status_code=422, detail="invalid mission id")
    return mission_id


def _validate_council_request_id(request_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}", request_id):
        raise HTTPException(status_code=422, detail="invalid approval request id")
    if request_id in {".", ".."} or ".." in request_id:
        raise HTTPException(status_code=422, detail="invalid approval request id")
    return request_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _latest_intelligence_for_dashboard(report: KingReport) -> dict[str, Any]:
    model_routing = report.council_summary.get("model_routing", {})
    return model_routing if isinstance(model_routing, dict) else {}


def _mission_dir(runtime_root: Path, mission_id: str) -> Path:
    # Defense in depth alongside _validate_council_mission_id: resolve the
    # candidate and confirm it stays strictly inside the missions/ tree, so no
    # mission_id can ever address a sibling or parent directory.
    base = (runtime_root / "missions").resolve()
    candidate = (base / mission_id).resolve()
    if base not in candidate.parents:
        raise HTTPException(status_code=422, detail="invalid mission id")
    return candidate


def _read_council_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("council_dashboard_json_skipped", path=str(path), exc_info=exc)
        return None
    return value if isinstance(value, dict) else None


def _king_decision(runtime_root: Path, mission_id: str) -> dict[str, Any] | None:
    return _read_council_json(_mission_dir(runtime_root, mission_id) / "king_decision.json")


def _pending_approvals_for_dashboard(runtime_root: Path, mission_id: str) -> list[dict[str, Any]]:
    approvals_dir = _mission_dir(runtime_root, mission_id) / "approvals"
    if not approvals_dir.is_dir():
        return []
    pending: list[dict[str, Any]] = []
    for request_path in sorted(approvals_dir.glob("*.request.json"), key=lambda path: path.stat().st_mtime):
        request_id = request_path.name.removesuffix(".request.json")
        response_path = approvals_dir / f"{request_id}.response.json"
        if response_path.exists():
            continue
        payload = _read_council_json(request_path)
        if payload is None:
            continue
        pending.append(
            {
                "requestId": request_id,
                "workerId": payload.get("worker_id"),
                "action": payload.get("action"),
                "reason": payload.get("reason"),
                "createdAt": payload.get("created_at"),
            }
        )
    return pending


def _council_summary_from_artifacts(
    *,
    runtime_root: Path,
    mission_id: str,
    report: KingReport,
    ledger: RunLedger | None,
    updated_at: float,
) -> dict[str, Any]:
    verification = report.verification_result if isinstance(report.verification_result, dict) else {}
    commands = []
    raw_commands = verification.get("commands", [])
    if isinstance(raw_commands, list):
        commands = raw_commands
    return {
        # The TYPED verification the King approves on (Slice A1/A2): strength, whether
        # it meets the promotion floor, and the caution when a positive recommendation
        # rests on below-floor evidence. None when no strength was recorded.
        "verificationStrength": verification.get("strength"),
        "verificationMeetsFloor": verification.get("meets_floor"),
        "verificationBelowFloorWarning": verification.get("below_floor_warning"),
        "missionId": mission_id,
        "mission": report.mission,
        "status": report.status,
        "recommendation": report.recommendation,
        "risk": report.risk,
        "approvalNeeded": report.approval_needed,
        "rollbackAvailable": report.rollback_available,
        "rollbackId": report.rollback_id,
        "filesTouched": list(report.files),
        "blockedAttempts": (
            len(ledger.blocked_attempts)
            if ledger is not None
            else int(report.council_summary.get("blocked_attempts", 0) or 0)
        ),
        "verificationPassed": all(
            isinstance(command, dict) and command.get("returncode") == 0
            for command in commands
        ) if commands else None,
        "councilVerdicts": report.council_summary.get("council_verdicts", []),
        "modelRouting": _latest_intelligence_for_dashboard(report),
        "pendingApprovals": _pending_approvals_for_dashboard(runtime_root, mission_id),
        "kingDecision": _king_decision(runtime_root, mission_id),
        "updatedAt": updated_at,
    }


def _write_council_decision(
    *,
    runtime_root: Path,
    req: CouncilDecisionRequest,
    approved: bool,
) -> dict[str, Any]:
    safe_id = _validate_council_mission_id(req.mission_id)
    mission_dir = _mission_dir(runtime_root, safe_id)
    if not mission_dir.is_dir():
        raise HTTPException(status_code=404, detail="council mission not found")

    request_id = _validate_council_request_id(req.request_id) if req.request_id else None
    # One-shot mission-level decision under origination: an atomic mkdir lock makes
    # the King decision final and single. This closes the double-execute race (two
    # concurrent approves: only one wins the lock) and makes reject terminal (a
    # later approve cannot claim the lock, so it cannot execute).
    if config.COUNCIL_ORIGINATION and request_id is None:
        try:
            (mission_dir / "decision.lock").mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise HTTPException(
                status_code=409, detail="council mission already decided"
            ) from exc
    decided_at = _utc_now_iso()
    response_written = False
    if request_id:
        approvals_dir = mission_dir / "approvals"
        request_path = approvals_dir / f"{request_id}.request.json"
        response_path = approvals_dir / f"{request_id}.response.json"
        if not request_path.exists():
            raise HTTPException(status_code=404, detail="approval request not found")
        if response_path.exists():
            raise HTTPException(status_code=409, detail="approval request already decided")
        response_path.write_text(
            json.dumps(
                {
                    "request_id": request_id,
                    "mission_id": safe_id,
                    "approved": approved,
                    "reason": req.reason,
                    "decided_at": decided_at,
                    "decided_by": "king_dashboard",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        response_written = True

    decision = {
        "mission_id": safe_id,
        "request_id": request_id,
        "decision": "approve" if approved else "reject",
        "approved": approved,
        "reason": req.reason,
        "decided_at": decided_at,
        "decided_by": "king_dashboard",
    }
    (mission_dir / "king_decision.json").write_text(
        json.dumps(decision, indent=2),
        encoding="utf-8",
    )
    return {
        "missionId": safe_id,
        "decision": decision,
        "approvalResponseWritten": response_written,
    }


def _resolve_council_workspace(raw: Optional[str]) -> Path:
    """Return a writable workspace confined to config.COUNCIL_WORKSPACE_ROOT."""
    base = config.COUNCIL_WORKSPACE_ROOT.resolve()
    if raw is None:
        base.mkdir(parents=True, exist_ok=True)
        return base
    candidate = Path(raw).resolve()
    if candidate != base and base not in candidate.parents:
        raise HTTPException(status_code=422, detail="workspaceRoot escapes the council workspace")
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _validate_mission_scope(allowed_files: list[str], workspace_root: Path) -> list[str]:
    """Confine allowed_files to workspace_root — explicit, fail-closed, no traversal."""
    base = workspace_root.resolve()
    safe: list[str] = []
    for raw in allowed_files:
        if not isinstance(raw, str) or not raw.strip():
            raise HTTPException(status_code=422, detail="allowedFiles entries must be non-empty")
        if any(ch in raw for ch in "*?[]"):
            # Origination scope must be concrete operator files; a glob like "*"
            # would let the approved worker touch every file under the workspace.
            raise HTTPException(status_code=422, detail=f"glob not allowed in scope: {raw}")
        candidate = Path(raw)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise HTTPException(status_code=422, detail=f"unsafe allowed file: {raw}")
        resolved = (base / candidate).resolve()
        if resolved != base and base not in resolved.parents:
            raise HTTPException(status_code=422, detail=f"allowed file escapes workspace: {raw}")
        safe.append(candidate.as_posix())
    return safe


def _write_failed_council_report(runtime_root: Path, mission_id: str, reason: str) -> None:
    """Persist a minimal failed report so a background failure is visible to the poll."""
    try:
        KingReportStore(runtime_root).write(
            KingReport(
                mission_id=mission_id,
                mission=mission_id,
                status="failed",
                recommendation="revise",
                risk="YELLOW",
                approval_needed=True,
                rollback_available=False,
                human_summary=f"Council mission failed: {reason}",
            )
        )
    except Exception as exc:  # noqa: BLE001 - best-effort failure surface
        logger.warning("council_failed_report_write_failed", mission_id=mission_id, exc_info=exc)


def _run_council_deliberation(runtime_root: Path, request: CouncilMissionRequest) -> None:
    """Background: deliberate only (no worker). Failures surface as a failed report."""
    try:
        CouncilOrchestrator(
            runtime_root=runtime_root,
            council_state=CouncilState(db_path=runtime_root / "council_state.db"),
        ).deliberate(request)
    except Exception as exc:  # noqa: BLE001 - background task must not crash the server
        logger.warning("council_deliberation_failed", mission_id=request.mission_id, exc_info=exc)
        _write_failed_council_report(runtime_root, request.mission_id, str(exc))


def _run_council_execution(runtime_root: Path, mission_id: str) -> None:
    """Background: run the approved worker — reads the deliberated ledger for the
    contract + verdicts, executes (worker acts), and writes the final report."""
    try:
        ledger = RunLedgerStore(runtime_root).read(mission_id)
        # Defense in depth: never execute a ledger that carries a blocking verdict
        # (guards against an on-disk ledger tampered between deliberate and approve).
        if has_blocking_verdict(list(ledger.council_verdicts)):
            raise RuntimeError("ledger carries a blocking verdict; refusing to execute")
        orchestrator = CouncilOrchestrator(
            runtime_root=runtime_root,
            council_state=CouncilState(db_path=runtime_root / "council_state.db"),
        )
        asyncio.run(orchestrator.execute(ledger.contract, list(ledger.council_verdicts)))
    except Exception as exc:  # noqa: BLE001 - background task must not crash the server
        logger.warning("council_execution_failed", mission_id=mission_id, exc_info=exc)
        _write_failed_council_report(runtime_root, mission_id, str(exc))


def _council_rollback_target(ledger: RunLedger, report: KingReport) -> str:
    if report.status == "rolled_back":
        raise HTTPException(status_code=409, detail="council mission already rolled back")
    snapshot_id = ledger.rollback_id or report.rollback_id or ledger.snapshot_id
    if not snapshot_id:
        raise HTTPException(
            status_code=409,
            detail="council mission has no rollback snapshot",
        )
    return snapshot_id


def _write_council_rollback_artifacts(
    *,
    runtime_root: Path,
    ledger: RunLedger,
    report: KingReport,
    snapshot_id: str,
    result: Any,
) -> KingReport:
    restored_at = _utc_now_iso()
    rollback_evidence = {
        "snapshot_id": snapshot_id,
        "restored": bool(result.restored),
        "head_sha": result.head_sha,
        "reason": result.reason,
        "restored_at": restored_at,
    }
    ledger_evidence = dict(ledger.evidence)
    ledger_evidence["rollback"] = rollback_evidence
    updated_ledger = ledger.model_copy(
        update={
            "status": "rolled_back",
            "completed_at": restored_at,
            "evidence": ledger_evidence,
        }
    )
    RunLedgerStore(runtime_root).write(updated_ledger)

    report_evidence = dict(report.evidence)
    report_evidence["rollback"] = rollback_evidence
    updated_report = report.model_copy(
        update={
            "status": "rolled_back",
            "recommendation": "observe",
            "rollback_available": False,
            "rollback_id": snapshot_id,
            "evidence": report_evidence,
            "human_summary": (
                "Council rollback restored the workspace to snapshot "
                f"{snapshot_id[:12]}."
            ),
        }
    )
    KingReportStore(runtime_root).write(updated_report)
    return updated_report


@app.post("/api/v1/council/missions")
def council_originate(
    req: CouncilMissionOriginationRequest,
    background: BackgroundTasks,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Originate a Council mission from a goal: deliberate, then await King approval.

    The worker does NOT act here — origination runs only the Queen deliberation in
    the background and produces an ``awaiting_approval`` (or ``blocked``) report.
    Approving the mission later triggers execution. Scope is explicit + confined.
    """
    if not config.COUNCIL_ORIGINATION:
        raise HTTPException(status_code=404, detail="council origination is disabled")
    _enforce_conversation_rate_limit(req.session_id)
    if (injection_reason := _check_prompt_injection(req.goal)):
        raise HTTPException(status_code=400, detail=f"[SECURITY BLOCK] {injection_reason}")
    workspace_root = _resolve_council_workspace(req.workspace_root)
    safe_allowed = _validate_mission_scope(req.allowed_files, workspace_root)
    mission_id = f"mission-{uuid.uuid4().hex[:12]}"
    allowed_tools = ["read_file", "write_file", "run_command"]
    mission_metadata: dict[str, Any] = {}
    if config.WORKER_REASONING:
        allowed_tools.append("request_change")
        mission_metadata["model_policy"] = {"mode": "local", "allow_cloud": False}
    mission_request = CouncilMissionRequest(
        mission_id=mission_id,
        goal=req.goal,
        workspace_root=str(workspace_root),
        allowed_files=safe_allowed,
        forbidden_files=list(req.forbidden_files),
        # The worker's reasoning is governed by WORKER_REASONING (the LLM worker
        # uses request_change, not request_plan), so the origination default omits
        # request_plan: the deterministic worker needs no model when reasoning is off.
        allowed_tools=allowed_tools,
        verification_commands=list(req.verification_commands),
        risk_level=req.risk_level,  # type: ignore[arg-type]
        metadata=mission_metadata,
    )
    background.add_task(_run_council_deliberation, runtime_root, mission_request)
    return {"missionId": mission_id, "status": "deliberating"}


@app.get("/api/v1/council/missions")
def council_missions(
    limit: int = 20,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """List stored Council mission reports for the operator dashboard."""
    mission_root = runtime_root / "missions"
    if not mission_root.is_dir():
        return {"missions": [], "count": 0}

    reports = KingReportStore(runtime_root)
    ledgers = RunLedgerStore(runtime_root)
    items: list[dict[str, Any]] = []
    for mission_dir in mission_root.iterdir():
        if not mission_dir.is_dir():
            continue
        mission_id = mission_dir.name
        report_path = reports.path_for(mission_id)
        if not report_path.exists():
            continue
        try:
            report = reports.read(mission_id)
            ledger = ledgers.read(mission_id) if ledgers.path_for(mission_id).exists() else None
        except Exception as exc:  # noqa: BLE001 - one corrupt artifact must not kill the dashboard
            logger.warning("council_dashboard_artifact_skipped", mission_id=mission_id, exc_info=exc)
            continue
        items.append(
            _council_summary_from_artifacts(
                runtime_root=runtime_root,
                mission_id=mission_id,
                report=report,
                ledger=ledger,
                updated_at=report_path.stat().st_mtime,
            )
        )

    items.sort(key=lambda item: item["updatedAt"], reverse=True)
    bounded_limit = max(1, min(int(limit), 100))
    return {"missions": items[:bounded_limit], "count": len(items)}


@app.get("/api/v1/council/missions/{mission_id}")
def council_mission_detail(
    mission_id: str,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Return the stored RunLedger and KingReport for one Council mission."""
    safe_id = _validate_council_mission_id(mission_id)
    reports = KingReportStore(runtime_root)
    ledgers = RunLedgerStore(runtime_root)
    report_path = reports.path_for(safe_id)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="council mission not found")
    try:
        report = reports.read(safe_id)
        ledger = ledgers.read(safe_id) if ledgers.path_for(safe_id).exists() else None
    except Exception as exc:  # noqa: BLE001 - a corrupt artifact is a 422, not a 500
        logger.warning("council_dashboard_artifact_corrupt", mission_id=safe_id, exc_info=exc)
        raise HTTPException(status_code=422, detail="council artifact is corrupt") from exc
    return {
        "missionId": safe_id,
        "summary": _council_summary_from_artifacts(
            runtime_root=runtime_root,
            mission_id=safe_id,
            report=report,
            ledger=ledger,
            updated_at=report_path.stat().st_mtime,
        ),
        "report": report.model_dump(),
        "ledger": ledger.model_dump() if ledger is not None else None,
        "pendingApprovals": _pending_approvals_for_dashboard(runtime_root, safe_id),
        "kingDecision": _king_decision(runtime_root, safe_id),
    }


@app.get("/api/v1/council/reports/{mission_id}")
def council_report(
    mission_id: str,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Return only the human-facing KingReport for one Council mission."""
    safe_id = _validate_council_mission_id(mission_id)
    store = KingReportStore(runtime_root)
    if not store.path_for(safe_id).exists():
        raise HTTPException(status_code=404, detail="council report not found")
    try:
        report = store.read(safe_id)
    except Exception as exc:  # noqa: BLE001 - a corrupt artifact is a 422, not a 500
        logger.warning("council_report_artifact_corrupt", mission_id=safe_id, exc_info=exc)
        raise HTTPException(status_code=422, detail="council report is corrupt") from exc
    return {"missionId": safe_id, "report": report.model_dump()}


@app.post("/api/v1/council/missions/{mission_id}/rollback")
def council_mission_rollback(
    mission_id: str,
    req: CouncilRollbackRequest,
    request: Request,
    runtime_root: Path = Depends(get_council_runtime_root),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Restore one Council mission workspace to its pre-worker snapshot."""
    safe_id = _validate_council_mission_id(mission_id)
    reports = KingReportStore(runtime_root)
    ledgers = RunLedgerStore(runtime_root)
    if not reports.path_for(safe_id).exists() or not ledgers.path_for(safe_id).exists():
        raise HTTPException(status_code=404, detail="council mission not found")
    try:
        report = reports.read(safe_id)
        ledger = ledgers.read(safe_id)
    except Exception as exc:  # noqa: BLE001 - corrupt artifacts are caller-visible
        logger.warning("council_rollback_artifact_corrupt", mission_id=safe_id, exc_info=exc)
        raise HTTPException(status_code=422, detail="council artifact is corrupt") from exc

    snapshot_id = _council_rollback_target(ledger, report)
    if req.snapshot_id and req.snapshot_id != snapshot_id:
        raise HTTPException(
            status_code=403,
            detail="requested snapshot does not match council mission rollback target",
        )
    session_id = _session_id_from_request(request, req.session_id)
    if not session_id:
        raise HTTPException(status_code=422, detail="sessionId or session cookie is required")

    payload = {"mission_id": safe_id, "snapshot_id": snapshot_id}
    if not req.approval_token:
        token = approvals.issue("rollback", payload, session_id)
        return {
            "requiresApproval": True,
            "approvalToken": token,
            "actionType": "rollback",
            "missionId": safe_id,
            "snapshotId": snapshot_id,
            "executed": False,
        }
    try:
        action = approvals.consume(req.approval_token, session_id)
    except ApprovalError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if action.action_type != "rollback":
        raise HTTPException(status_code=400, detail="approval token is not for rollback")
    if action.payload != payload:
        raise HTTPException(
            status_code=403,
            detail="approval token does not match council mission rollback target",
        )
    try:
        result = SnapshotManager(runtime_root).rollback_snapshot(
            ledger.contract.workspace_root,
            snapshot_id,
        )
    except RollbackError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not result.restored:
        raise HTTPException(status_code=500, detail=result.reason)
    updated_report = _write_council_rollback_artifacts(
        runtime_root=runtime_root,
        ledger=ledger,
        report=report,
        snapshot_id=snapshot_id,
        result=result,
    )
    return {
        "requiresApproval": False,
        "missionId": safe_id,
        "snapshotId": snapshot_id,
        "executed": True,
        "result": asdict(result),
        "report": updated_report.model_dump(),
    }


@app.post("/api/v1/council/approve")
def council_approve(
    req: CouncilDecisionRequest,
    background: BackgroundTasks,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Record King approval; if the mission is awaiting execution, run the worker.

    A mission-level approval (no requestId) of a mission whose report is
    ``awaiting_approval`` schedules execute() in the background — this is the gate
    where a human authorizes the worker to act.
    """
    result = _write_council_decision(runtime_root=runtime_root, req=req, approved=True)
    if config.COUNCIL_ORIGINATION and req.request_id is None:
        safe_id = result["missionId"]
        store = KingReportStore(runtime_root)
        try:
            awaiting = store.path_for(safe_id).exists() and (
                store.read(safe_id).status == "awaiting_approval"
            )
        except Exception:  # noqa: BLE001 - a read failure simply means "don't execute"
            awaiting = False
        if awaiting:
            background.add_task(_run_council_execution, runtime_root, safe_id)
            result["execution"] = "scheduled"
    return result


@app.post("/api/v1/council/reject")
def council_reject(
    req: CouncilDecisionRequest,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Record King rejection for a Council mission or pending worker request."""
    return _write_council_decision(runtime_root=runtime_root, req=req, approved=False)


@app.post("/api/v1/security/classify")
def security_classify(req: ClassifyRequest) -> dict[str, Any]:
    """Deterministic, fail-closed security-zone classification."""
    result = classify(req.command)
    return {
        "zone": result.zone.value,
        "confidence": result.confidence,
        "reason": result.reason,
    }


@app.get("/api/v1/audit/verify")
def audit_verify(from_entry: int = 1, to_entry: Optional[int] = None) -> dict[str, Any]:
    """Verify the tamper-evident audit hash chain over an optional id range."""
    status = verify_chain(from_id=from_entry, to_id=to_entry)
    if not status.valid:
        logger.critical(
            "Audit hash-chain verification failed",
            broken_at=status.broken_at,
            reason=status.reason,
            total_entries=status.total_entries,
        )
        _METRICS.record_audit_verify_failure()
    return asdict(status)


@app.post("/api/v1/reflect")
def reflect(req: ReflectRequest, llm: LLMClient = Depends(get_llm_client)) -> dict[str, Any]:
    """Run the reflection agent on a failure and store a structured lesson."""
    agent = ReflectionAgent(llm)
    try:
        reflection = agent.reflect(req.command, req.error_output, task_id=req.task_id)
    except ReflectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(reflection)


def _serialize_plan(plan: Any) -> dict[str, Any]:
    """Flatten a Plan (with TaskStep dataclasses) into JSON-safe primitives."""
    return {
        "goal": plan.goal,
        "requires_human": plan.requires_human,
        "steps": [asdict(s) for s in plan.steps],
        "approved": [asdict(s) for s in plan.approved],
        "escalate": [
            {"step": asdict(e["step"]), "reason": e["reason"], "action": e["action"]}
            for e in plan.escalate
        ],
        "calibrations": [asdict(c) for c in plan.calibrations],
    }


@app.post("/api/v1/plan")
def plan(req: PlanRequest, llm: LLMClient = Depends(get_llm_client)) -> dict[str, Any]:
    """Decompose a goal into a confidence-gated task tree."""
    planner = Planner(llm)
    try:
        result = planner.plan(req.goal)
    except PlannerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize_plan(result)


@app.post("/api/v1/execute")
def execute(
    req: ExecuteRequest,
    executor: Executor = Depends(get_executor),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Classify, gate, audit, and (if GREEN) run a command in the sandbox."""
    result = executor.execute(req.command, session_id=req.session_id)
    response = asdict(result)
    if result.status == "REQUIRE_APPROVAL":
        if not req.session_id:
            raise HTTPException(
                status_code=400,
                detail="sessionId is required to approve a YELLOW command",
            )
        response["approvalToken"] = approvals.issue(
            "command", {"command": req.command}, req.session_id
        )
        response["sessionId"] = req.session_id
    return response


@app.post("/api/v1/approval/req")
def approval_req(
    req: ApprovalRequest,
    request: Request,
    executor: Executor = Depends(get_executor),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Resolve a human decision on an escalated (YELLOW) action.

    Approve -> run the command in the sandbox (RED is still refused). Reject ->
    audit the rejection and return without running.
    """
    session_id = _session_id_from_request(request, req.session_id)
    if not session_id:
        raise HTTPException(status_code=422, detail="sessionId or session cookie is required")
    try:
        action = approvals.consume(req.approval_token, session_id)
    except ApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    command = str(action.payload.get("command", ""))
    if not req.approve:
        if action.action_type == "command":
            executor.reset_sensitive_actions(session_id)
        target = command or str(action.payload.get("filepath", action.action_type))
        log_action("human-approval", f"REJECTED {action.action_type}: {target}", Zone.YELLOW)
        return {
            "decision": "rejected",
            "actionType": action.action_type,
            "command": command,
            "executed": False,
        }
    if action.action_type != "command":
        raise HTTPException(status_code=400, detail="approval token is not for a command")
    executor.reset_sensitive_actions(session_id)

    result = executor.execute_approved(command)
    return {
        "decision": "approved",
        "command": command,
        "executed": result.status == "OK",
        "result": asdict(result),
    }


@app.post("/api/v1/rollback")
def rollback(
    req: RollbackRequest,
    request: Request,
    engine: RollbackEngine = Depends(get_rollback_engine),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Restore the sandbox working tree to a prior snapshot.

    Rollback is a DESTRUCTIVE operation that requires a server-issued approval
    token. When called without a token, one is issued and returned so the UI
    can prompt the human approver; when called with a valid token, the token
    is consumed and the rollback executes.
    """
    session_id = _session_id_from_request(request, req.session_id)
    if not session_id:
        raise HTTPException(status_code=422, detail="sessionId or session cookie is required")
    try:
        snapshot_id = _effective_rollback_snapshot(engine, req.snapshot_id)
    except RollbackError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not req.approval_token:
        token = approvals.issue(
            "rollback", {"snapshot_id": snapshot_id}, session_id
        )
        return {
            "requiresApproval": True,
            "approvalToken": token,
            "actionType": "rollback",
            "snapshotId": snapshot_id,
            "executed": False,
        }
    try:
        action = approvals.consume(req.approval_token, session_id)
    except ApprovalError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if action.action_type != "rollback":
        raise HTTPException(status_code=400, detail="approval token is not for rollback")
    if action.payload.get("snapshot_id") != snapshot_id:
        raise HTTPException(status_code=403, detail="approval token snapshot does not match request")
    try:
        result = engine.rollback(snapshot_id)
    except RollbackError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return asdict(result)


# --------------------------------------------------------------------------- #
# Self-Analysis T3 — human-gated review + apply of fix proposals
# The agent has NO tool to apply (see tool_agent); these human-called endpoints
# are the ONLY path from a 'proposed' row to a real write in aios/.
# --------------------------------------------------------------------------- #
@app.get("/api/v1/self-analysis/proposals")
def list_proposals(status: Optional[str] = "proposed") -> dict[str, Any]:
    """List Self-Analysis findings (default the ``proposed`` ones) for the review UI."""
    init_memory_db()
    sql = (
        "SELECT id, target_path, finding_type, evidence, proposed_zone, "
        "proposed_diff, proposed_by, approved_by, status FROM self_analysis_report"
    )
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT 200"
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return {"proposals": rows}


@app.post("/api/v1/self-analysis/proposals/{proposal_id}/apply")
def apply_proposal(
    proposal_id: int,
    req: ApplyProposalRequest,
    engine: SelfApplyEngine = Depends(get_self_apply_engine),
) -> dict[str, Any]:
    """Apply an approved proposal to ``aios/`` — gated, verified, auto-rollback (T3)."""
    result = engine.apply(proposal_id, approved_by=req.approved_by)
    return asdict(result)


@app.post("/api/v1/self-analysis/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int) -> dict[str, Any]:
    """Reject a ``proposed`` finding (status -> ``rejected``); never applies anything."""
    init_memory_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM self_analysis_report WHERE id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"no proposal with id {proposal_id}")
        if row["status"] != "proposed":
            raise HTTPException(
                status_code=409,
                detail=f"proposal {proposal_id} is '{row['status']}', not 'proposed'",
            )
        conn.execute(
            "UPDATE self_analysis_report SET status = 'rejected' WHERE id = ?", (proposal_id,)
        )
    return {"id": proposal_id, "status": "rejected"}


# --------------------------------------------------------------------------- #
# Front-end bridge: model discovery, conversational chat, UI terminal
# These three endpoints back the React UI's main surfaces. The ``/api/v1/*``
# routes above expose individual subsystems; these compose them for the UI.
# --------------------------------------------------------------------------- #
@app.get("/api/v1/models/local")
def models_local(client: OllamaClient = Depends(get_ollama_client)) -> dict[str, Any]:
    """List installed models policy-compatible with this conversational UI."""
    info = client.list_models()
    models = info.get("models") or []
    chat_models = [
        model
        for model in models
        if isinstance(model, str) and supports_tool_protocol(model)
    ]
    return {**info, "models": chat_models}


@app.get("/api/v1/models/bedrock")
def models_bedrock(
    bedrock: Optional[BedrockClient] = Depends(get_bedrock_client),
) -> dict[str, Any]:
    """List invocable AWS Bedrock text models for the picker.

    ``{"available": bool, "models": [{"id","name"}]}`` — empty when Bedrock isn't
    configured or the credentials lack control-plane (discovery) access, in which
    case the UI falls back to a curated cloud list.
    """
    if bedrock is None:
        return {"configured": False, "available": False, "models": []}
    models = bedrock.list_models()
    return {"configured": True, "available": bool(models), "models": models}


@app.get("/api/v1/models/gemini")
def models_gemini(
    gemini: Optional[GeminiClient] = Depends(get_gemini_client),
) -> dict[str, Any]:
    """List invocable Google Gemini models for the picker.

    ``{"configured": bool, "available": bool, "models": [{"id","name"}]}`` — empty
    when Gemini isn't configured (no GCP project). When configured, ``list_models``
    already falls back to the curated Gemini set if live Vertex discovery is
    unavailable, so the picker always has the well-known models to offer.
    """
    if gemini is None:
        return {"configured": False, "available": False, "models": []}
    models = gemini.list_models()
    return {"configured": True, "available": bool(models), "models": models}


@app.get("/api/v1/models/auto")
def models_auto(
    task: str = "coding",
    client: OllamaClient = Depends(get_ollama_client),
) -> dict[str, Any]:
    """What the agent would auto-select, per task (drives the 'Auto' picker entry).

    Choosing the best local model is the agent's job, not the user's. Returns the
    pick for *task* plus a ``by_task`` map (coding/reasoning/general/fast) over the
    LIVE installed set, so the UI can show "Auto · <model>" and surface how the
    agent routes by purpose. Selection applies the live loop's tool-capability
    requirement, so discovery never advertises a different Auto route than runtime.
    """
    models = client.list_models().get("models") or []
    by_task = {t: select_model(models, task=t, require_tools=True) for t in TASKS}
    chosen = select_model(models, task=task, require_tools=True)
    if not chosen:
        return {"available": False, "model": None, "task": task,
                "reason": "no local chat model installed", "by_task": by_task}
    return {"available": True, "model": chosen, "task": task,
            "reason": describe_choice(chosen), "by_task": by_task}


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


def _operator_facts_block(facts: SemanticFacts, subject: str = "operator") -> Optional[str]:
    """Build a REAL-facts-only personalization block, or ``None`` when dormant.

    Reads human-approved active facts for *subject* (newest-first) and renders
    them as ``subject predicate object`` triples. Honesty law: when there are no
    facts the block is ``None`` (personalization stays dormant — never fabricated).
    Best-effort: any store error degrades to ``None`` rather than breaking chat.
    """
    try:
        rows = facts.facts_for(subject)
    except Exception as exc:  # noqa: BLE001 - personalization is an enhancement, never fatal
        logger.warning("Failed to load operator facts block", exc_info=exc)
        return None
    if not rows:
        return None
    triples = "\n".join(
        f"- {row['subject']} {row['predicate']} {row['object']}" for row in rows
    )
    return (
        "KNOWN FACTS ABOUT THE OPERATOR (human-approved; use to personalize, "
        "never invent beyond these):\n" + triples
    )




def _recall_self_model(
    development: DevelopmentTracker, mistakes: MistakeMemory
) -> Optional[str]:
    """Synthesize the grounded, verified-only autobiographical self-model paragraph.

    Deterministic and fail-closed: with too little verified evidence the model is
    empty and nothing is injected (the organism never invents a self). Advisory —
    a failure degrades to ``None`` and never blocks the turn.
    """
    try:
        text = render_self_model(synthesize_self_model(development, mistakes))
    except Exception as exc:  # noqa: BLE001 - the self-model is advisory recall
        logger.warning("Failed to synthesize self-model", exc_info=exc)
        return None
    return text or None


def _recall_facts(facts: SemanticFacts, user_text: str) -> Optional[str]:
    """Recall relevant semantic facts (+ single-hop neighbors) for the forge.

    The agentic loop reasons about code and architecture, so it needs the
    structured, approved facts from the knowledge graph — not just raw chat
    memory. This block searches active facts whose subject/object appears in
    the user message, includes one hop of neighbors for context, and renders
    the result as prompt-ready triples. Empty or failing recall degrades to
    ``None`` so the turn is never blocked by the fact store.
    """
    user_text = (user_text or "").strip()
    if not user_text:
        return None
    try:
        matched = facts.search(user_text)
    except Exception as exc:  # noqa: BLE001 - recall is advisory
        logger.warning("Failed to search semantic facts", exc_info=exc)
        return None
    if not matched:
        return None

    # Collect subjects/objects to expand with single-hop neighbors.
    nodes: set[str] = set()
    for row in matched:
        nodes.add(str(row["subject"]))
        nodes.add(str(row["object"]))

    expanded: set[tuple[str, str, str]] = set()
    for row in matched:
        expanded.add((str(row["subject"]), str(row["predicate"]), str(row["object"])))
    for node in nodes:
        try:
            for row in facts.neighbors(node):
                expanded.add((str(row["subject"]), str(row["predicate"]), str(row["object"])))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load neighbors for %s", node, exc_info=exc)

    if not expanded:
        return None
    triples = "\n".join(
        f"- {s} {p} {o}" for s, p, o in sorted(expanded)
    )
    return (
        "RELEVANT APPROVED FACTS (use these; do not invent beyond this graph):\n"
        + triples
    )
def _latest_user(chat_messages: list[dict[str, Any]]) -> str:
    """Return the most recent user message text (already flattened to a string)."""
    for msg in reversed(chat_messages):
        if msg["role"] == "user":
            return msg["content"]
    return ""


_MEM_TRUSTED_HEADER = (
    "VERIFIED TRUSTED MEMORY (still prefer current tool evidence when available):\n"
)
_MEM_UNVERIFIED_HEADER = (
    "UNVERIFIED PRIOR CHAT MEMORY (may be stale or wrong; use only as a lead, "
    "never as evidence, and verify against tools/files before acting):\n"
)
_MEM_EXTERNAL_HEADER = (
    "EXTERNAL KNOWLEDGE (fetched on demand because local memory was insufficient; "
    "GENERATED/UNVERIFIED — treat as a lead only, verify against tools/files before "
    "acting):\n"
)


def _crag_cloud_source(query: str) -> list[str]:
    """CRAG external source A — the configured cloud model as a broader knowledge
    base. Returns ``[]`` when no cloud provider is configured. The cloud client
    secret-scrubs the message internally before transmission (PrivacyFilter)."""
    client = get_gemini_client() or get_bedrock_client()
    if client is None:
        return []
    prompt = (
        "Answer the question concisely and factually using only what you are "
        "confident about. If you do not know, say so rather than guessing.\n\n"
        f"Question: {query}"
    )
    try:
        response = client.chat([{"role": "user", "content": prompt}], tools=None)
    except Exception as exc:  # noqa: BLE001 - a cloud miss must not break recall
        logger.warning("CRAG cloud source failed", exc_info=exc)
        return []
    text = str((response or {}).get("content", "")).strip()
    return [text] if text else []


def _crag_web_source(query: str) -> list[str]:
    """CRAG external source B — a configurable web-search provider. Inert (``[]``)
    until AIOS_CRAG_SEARCH_ENDPOINT + AIOS_CRAG_SEARCH_API_KEY are set."""
    return web_search(
        query,
        endpoint=config.CRAG_SEARCH_ENDPOINT,
        api_key=config.CRAG_SEARCH_API_KEY,
    )


def _crag_external_sources() -> list:
    """The enabled external corrective sources (each independently opt-in)."""
    sources: list = []
    if config.CRAG_CLOUD:
        sources.append(_crag_cloud_source)
    if config.CRAG_WEBSEARCH:
        sources.append(_crag_web_source)
    return sources


_CRAG_JUDGE_NUMBER = re.compile(r"\d*\.?\d+")


def _crag_llm_judge(query: str, passage: str) -> float:
    """A local-model relevance score in [0,1] for one (query, passage) pair.

    Used as the evaluator's optional caution-only clamp (it can only *lower* a hit's
    deterministic confidence — see ``evaluate_retrieval``). Raises on an unparseable
    reply or a model error so the evaluator ignores it and the deterministic score
    stands (never silently fabricates caution)."""
    response = get_ollama_client().chat(
        [
            {
                "role": "user",
                "content": (
                    "Rate how RELEVANT the passage is to answering the query, from "
                    "0.0 (irrelevant) to 1.0 (directly answers it). Reply with ONLY "
                    f"the number.\n\nQuery: {query}\nPassage: {passage}"
                ),
            }
        ],
        tools=None,
        model=config.LLM_MODEL,
    )
    text = str((response or {}).get("content", ""))
    match = _CRAG_JUDGE_NUMBER.search(text)
    if not match:
        raise ValueError(f"CRAG judge returned no score: {text!r}")
    return max(0.0, min(1.0, float(match.group(0))))


def _recall_memory(query: str, top_k: int = 3) -> Optional[str]:
    """Best-effort hybrid recall of relevant semantic memories for *query*.

    Returns a prompt-ready knowledge block, or ``None`` when there is nothing
    relevant (or the memory subsystem is unavailable). ``hybrid_search``
    short-circuits to empty without loading the embedding model when the
    semantic index is empty, so this is a cheap no-op on a fresh system.

    When Corrective-RAG is enabled (``AIOS_CRAG``, default off) the retrieval is
    gated and refined before it reaches the prompt: a low-confidence (INCORRECT)
    recall is DROPPED rather than injected — the core anti-hallucination win — and
    the surviving hits are decompose-then-recomposed down to their golden strips.
    Trust labels are preserved (CRAG judges *relevance*; verified/unverified judges
    *trust*). CRAG fails soft to the unrefined block on any error.
    """
    try:
        hits = hybrid_search(query, top_k=top_k)
    except Exception as exc:  # noqa: BLE001 - recall is an enhancement, never fatal
        logger.warning("Memory recall failed; continuing without context", exc_info=exc)
        return None
    if not hits:
        return None
    trusted = [
        hit for hit in hits if getattr(hit, "verification_status", "unverified") == "verified"
    ]
    unverified = [hit for hit in hits if hit not in trusted]

    if config.CRAG:
        try:
            verdict = evaluate_retrieval(
                query,
                hits,
                upper=config.CRAG_UPPER,
                lower=config.CRAG_LOWER,
                judge=_crag_llm_judge if config.CRAG_LLM_JUDGE else None,
            )
            # Slice 3: on a low-confidence local recall, gather refined external
            # knowledge (privacy-gated, default off, only when a source is enabled).
            external_body = ""
            if config.CRAG_EXTERNAL and verdict.action in (
                CragAction.INCORRECT,
                CragAction.AMBIGUOUS,
            ):
                try:
                    ext_docs = external_retrieve(query, _crag_external_sources())
                    external_body = refine_context(query, ext_docs) if ext_docs else ""
                except Exception as exc:  # noqa: BLE001 - external is additive
                    logger.warning("CRAG external retrieval failed", exc_info=exc)
                    external_body = ""

            if verdict.action is CragAction.INCORRECT:
                # Local retrieval is junk — never inject it. Use external if we got
                # any; otherwise no memory context (the anti-hallucination win).
                return (_MEM_EXTERNAL_HEADER + external_body) if external_body else None

            trusted_body = refine_context(query, [h.text for h in trusted]) if trusted else ""
            unverified_body = (
                refine_context(query, [h.text for h in unverified]) if unverified else ""
            )
            crag_blocks: list[str] = []
            if trusted_body:
                crag_blocks.append(_MEM_TRUSTED_HEADER + trusted_body)
            if unverified_body:
                crag_blocks.append(_MEM_UNVERIFIED_HEADER + unverified_body)
            if external_body:  # AMBIGUOUS supplemented with external knowledge
                crag_blocks.append(_MEM_EXTERNAL_HEADER + external_body)
            if crag_blocks:
                return "\n\n".join(crag_blocks)
            # Refinement emptied everything → fall through to the legacy block so a
            # non-empty retrieval is never silently blanked.
        except Exception as exc:  # noqa: BLE001 - CRAG is additive; never break recall
            logger.warning("CRAG recall failed; using unrefined memory", exc_info=exc)

    blocks: list[str] = []
    if trusted:
        blocks.append(_MEM_TRUSTED_HEADER + "\n".join(f"- {hit.text}" for hit in trusted))
    if unverified:
        blocks.append(
            _MEM_UNVERIFIED_HEADER + "\n".join(f"- {hit.text}" for hit in unverified)
        )
    return "\n\n".join(blocks)


def _record_episode(session_id: str, role: str, content: str) -> None:
    """Persist one turn to L2 episodic memory. Best-effort; never fatal."""
    if not content or not content.strip():
        return
    try:
        _EPISODIC.record(session_id, role, scan_and_redact(content).scrubbed)
    except Exception as exc:  # noqa: BLE001 - persistence must not break the chat
        logger.warning("Failed to record episodic memory", exc_info=exc)


def _recall_lessons(
    reflector: Optional[ReflectionAgent], session_id: str, query: str, limit: int = 5
) -> list[dict[str, Any]]:
    """Best-effort recall of pending same-task and verified cross-task lessons.

    Carries lessons learned in earlier turns into the current one so the agent
    reasons with them. Recalled pending lessons remain advisory. Never fatal.
    """
    if reflector is None:
        return []
    try:
        recall_relevant = getattr(reflector, "recall_relevant", None)
        if callable(recall_relevant):
            return recall_relevant(query, session_id, limit)
        return reflector.recall_pending(session_id, limit)
    except Exception as exc:  # noqa: BLE001 - lesson recall is an enhancement, never fatal
        logger.warning("Failed to recall lessons", exc_info=exc)
        return []


def _recall_skills(skills: SkillMemory, query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Best-effort recall of reusable workflows backed by repeated verification."""
    try:
        return skills.relevant_verified(query, limit)
    except Exception as exc:  # noqa: BLE001 - skill recall is an enhancement, never fatal
        logger.warning("Failed to recall verified skills", exc_info=exc)
        return []


def _verify_target_keys(command: str) -> list[str]:
    """Classification keys for one verification command.

    The same file is legitimately verified through different command spellings
    within one turn (the forced auto-verify vs the model's own pytest call), so a
    file key is the normalized ``.py`` token WITH its directory kept.
    Keeping the directory is load-bearing: two different files that share a
    basename (``a/test_w.py`` vs ``b/test_w.py``) must NOT collide, or a later
    sibling PASS would overwrite (mask) an earlier FAIL/weak target in the
    authoritative per-target maps and launder the turn's verdict + strength.

    Multi-file commands return one key per file. A failed ``pytest a.py b.py``
    therefore marks both targets unresolved; later single-file passes can clear
    each target independently, but a PASS on only ``a.py`` cannot mask ``b.py``.
    A suite-wide verify with no file token keys on the whole command — a
    whole-suite FAIL must be resolved by a whole-suite PASS of that same command.
    """
    keys: list[str] = []
    seen: set[str] = set()
    for token in command.replace('"', " ").replace("'", " ").split():
        if token.endswith(".py"):
            norm = token.replace("\\", "/").lower()
            while norm.startswith("./"):
                norm = norm[2:]
            if norm and norm not in seen:
                seen.add(norm)
                keys.append(norm)
    return keys or [command.strip().lower() or "unattributed"]


def _verify_target_key(command: str) -> str:
    """Backward-compatible single-target helper for older tests/callers."""
    return _verify_target_keys(command)[0]


def _workflow_step(event: dict[str, Any]) -> str:
    """Create a compact, redacted procedural step from one tool-call event."""
    name = str(event.get("tool", ""))
    raw_input = event.get("input")
    if not isinstance(raw_input, dict):
        return name
    useful = []
    for key in ("command", "filepath", "path", "goal"):
        value = raw_input.get(key)
        if value is not None and str(value).strip():
            useful.append(f"{key}={str(value).strip()[:160]}")
    detail = ", ".join(useful)
    return scan_and_redact(f"{name}: {detail}" if detail else name).scrubbed


def _index_turn(
    indexer: Optional[SemanticMemory], user_text: str, answer: str
) -> None:
    """Embed a completed Q->A turn into L3 semantic memory so future recall finds it.

    Best-effort and gated by the injected *indexer* (``None`` disables it). This
    is what makes recall self-reinforcing: today's answer becomes tomorrow's
    recalled context. Skipped for empty answers.
    """
    answer = (answer or "").strip()
    if indexer is None or not answer:
        return
    try:
        payload = f"UNVERIFIED_CHAT\nUser: {user_text}\nAssistant: {answer}"
        clean = scan_and_redact(payload).scrubbed
        try:
            indexer.add(clean, memory_type="chat", verification_status="unverified")
        except TypeError:
            indexer.add(clean)
    except Exception as exc:  # noqa: BLE001 - indexing must not break the chat
        logger.warning("Failed to index completed turn into semantic memory", exc_info=exc)


def _make_failure_hook(reflector: Optional[ReflectionAgent], session_id: str) -> Optional[Any]:
    """Build the agent's on-failure hook from a reflection agent (or ``None``).

    The hook records a structured lesson in the Mistake pool and returns a small
    summary for the UI; any failure to reflect is swallowed so a learning step
    never breaks the chat.
    """
    if reflector is None:
        return None

    def hook(command: str, error_output: str) -> Optional[dict[str, Any]]:
        try:
            reflection = reflector.reflect(command, error_output, task_id=session_id)
        except ReflectionError:
            return None
        except Exception as exc:  # noqa: BLE001 - reflection must never break the chat
            logger.warning("Reflection agent failed to record lesson", exc_info=exc)
            return None
        return {
            "error_type": reflection.error_type,
            "lesson_text": reflection.lesson_text,
            "recurrence": reflection.recurrence,
            "mistake_id": reflection.mistake_id,
        }

    return hook


def _make_confirm_hook(
    reflector: Optional[ReflectionAgent],
    consolidator: Optional[MemoryConsolidator] = None,
):
    """Build the agent's lesson-confirmation hook (promotes pending->verified).

    Guarded so promotion can never break the chat; ``None`` when reflection is
    disabled, in which case the agent simply never confirms.
    """
    if reflector is None:
        return None

    def confirm(mistake_id: int) -> None:
        try:
            reflector.confirm_lesson(mistake_id)
            if consolidator is not None:
                consolidator.consolidate_lesson(mistake_id)
        except Exception as exc:  # noqa: BLE001 - confirmation must never break the chat
            logger.warning("Failed to confirm/consolidate lesson", exc_info=exc)

    return confirm


@app.post("/api/generate")
def generate(
    req: GenerateRequest,
    request: Request,
    client: OllamaClient = Depends(get_ollama_client),
    bedrock: Optional[BedrockClient] = Depends(get_bedrock_client),
    gemini: Optional[GeminiClient] = Depends(get_gemini_client),
    executor: Executor = Depends(get_executor),
    indexer: Optional[SemanticMemory] = Depends(get_semantic_indexer),
    reflector: Optional[ReflectionAgent] = Depends(get_reflection_agent),
    snapshot: Callable[..., object] = Depends(get_edit_snapshot),
    planner_llm: LLMClient = Depends(get_llm_client),
    approvals: ApprovalStore = Depends(get_approval_store),
    development: DevelopmentTracker = Depends(get_development_tracker),
    skills: SkillMemory = Depends(get_skill_memory),
    swarm_patterns: SwarmPatternMemory = Depends(get_swarm_pattern_memory),
    autonomy: AutonomyLedger = Depends(get_autonomy),
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
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
        req.model_id, client, bedrock, gemini=gemini, task=task,
        metrics=_route_metrics(development, req.model_id),
        calibration_weight=config.ROUTER_CALIBRATION_WEIGHT,
    )
    # The serving model is announced lazily from inside the stream (see
    # `_route_frame`); here we only normalise `model` to the route's view of it.
    _, model = _active_route(chat_client, bedrock, gemini, model)

    def _route_meta() -> dict[str, Any]:
        """Development metadata for the model that ACTUALLY served (post-failover)."""
        p, m = _active_route(chat_client, bedrock, gemini, model)
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

    def event_stream() -> Iterator[str]:
        sse = _sse_writer(session_id)
        if not user_text:
            yield sse("error", {"text": "No user message provided."})
            return

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
            p, m = _active_route(chat_client, bedrock, gemini, model)
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
                yield sse("done", {})
                return

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

        facts_block = _recall_facts(facts, user_text)
        if facts_block:
            context_parts.append(facts_block)
            yield sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "query_facts",
                    "output": facts_block[:400],
                    "id": "fact-recall",
                },
            )

        # Narrative self (opt-in): a grounded, verified-only autobiographical
        # self-model joins the recalled context — the organism reasoning with an
        # honest sense of what it's actually reliable at. Fail-closed: empty when
        # there's too little verified evidence.
        if config.NARRATIVE_SELF_ENABLED:
            self_model_block = _recall_self_model(development, MistakeMemory())
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

        # 2. Persist the user turn.
        _record_episode(session_id, "user", user_text)

        # 3. Agentic loop with recalled context + lessons + reflection + confirmation.
        #    `chat_client` is local Ollama or cloud Bedrock per the selected model.
        #    The factory exists so the role-pass castes can stamp out per-role
        #    views (system prompt + tool subset) over the SAME gated wiring.
        def make_agent(**overrides: Any) -> ToolAgent:
            return ToolAgent(
                chat_client,
                executor,
                model=model,
                session_id=session_id,
                memory_context=memory_context,
                on_failure=_make_failure_hook(reflector, session_id),
                confirm_lesson=_make_confirm_hook(reflector, consolidator),
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
                approved_commands=approved_commands,
                approved_edits=approved_edits,
                approved_creations=approved_creations,
                snapshot=snapshot,
                planner_llm=planner_llm,
                self_analysis_llm=planner_llm,
                autonomy=autonomy,
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
                    user_text, passed=passed, evidence=evidence, strength=turn_strength
                )
            except Exception as exc:  # noqa: BLE001 - unmatched/invalid curriculum is harmless
                logger.warning("Failed to record curriculum match", exc_info=exc)

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
        swarm_plan: Optional[list[str]] = None
        for ev in event_source:
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
                cmd = ev["command"]
                edit = ev.get("edit")
                creation = ev.get("creation")
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
                else:
                    # The FORCED auto-verify is authoritative; fall back to the
                    # model's own verify only when nothing was auto-verified.
                    authoritative = auto_verdicts or verify_verdicts
                    if any(v == "FAIL" for v in authoritative.values()):
                        record_outcome("verified_failure")
                    else:
                        record_outcome("verified_success")
                approvals.clear_session(session_id)
                yield sse("done", {})

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


@app.post("/api/v1/chat")
def chat(
    req: ChatRequest,
    request: Request,
    client: OllamaClient = Depends(get_ollama_client),
    bedrock: Optional[BedrockClient] = Depends(get_bedrock_client),
    gemini: Optional[GeminiClient] = Depends(get_gemini_client),
    indexer: Optional[SemanticMemory] = Depends(get_semantic_indexer),
    facts: SemanticFacts = Depends(get_semantic_facts),
    compactor: MemoryCompactor = Depends(get_compactor),
) -> StreamingResponse:
    """Stream a lean Hinglish conversational reply (the Jarvis voice mind, Slice 1).

    This is CONVERSATION, not the agentic forge: it reuses the cross-provider
    router (so the operator's local-first privacy gate is fully intact), recalls
    relevant memory, and injects REAL personalization facts, then calls the chat
    client ONCE for a single reply — NO ``ToolAgent`` loop, NO file-write/coding
    tools. The reply is fake-streamed word-by-word (mirroring ``ToolAgent._finish``)
    so cloud and local providers share one wire shape. Frames, in order:

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
        req.model_id, client, bedrock, gemini=gemini, task=task,
    )
    provider, model = _active_route(chat_client, bedrock, gemini, model)

    def event_stream() -> Iterator[str]:
        sse = _sse_writer(session_id)
        if not user_text:
            yield sse("error", {"text": "No transcript provided."})
            return

        # Build the conversational system prompt: the Hinglish persona + REAL
        # operator facts (dormant when none) + relevant prior memory.
        system_parts: list[str] = [CHAT_SYSTEM_PROMPT]
        persona = _operator_facts_block(facts)
        if persona:
            system_parts.append(persona)
        recall = _recall_memory(user_text)
        if recall:
            system_parts.append(recall)
        messages = [
            {"role": "system", "content": "\n\n".join(system_parts)},
            {"role": "user", "content": user_text},
        ]

        _record_episode(session_id, "user", user_text)

        # The ACTIVE BRAIN for this turn (the UI 'voyaging mind' badge): provider/
        # model that served + privacy indicator. Local-first respected — the
        # provider is whatever the router chose, never hardcoded cloud.
        yield sse(
            "route",
            {
                "provider": provider,
                "model": model,
                "privacy": "local" if provider == router.PROVIDER_OLLAMA else "cloud",
                "task": task,
                "auto": req.model_id in _AUTO_IDS,
            },
        )

        # ONE chat call, tools=None => pure text, no tool loop, no file writes.
        try:
            reply = chat_client.chat(messages, tools=None, model=model)
        except LLMError as exc:
            yield sse("error", {"text": str(exc)})
            return
        text = str((reply or {}).get("content", "")).strip() or "(no answer)"

        # Fake-stream word-by-word, mirroring ToolAgent._finish, so the UI's
        # existing text_chunk reader works identically for local + cloud.
        for word in re.findall(r"\S+\s*", text):
            yield sse("text_chunk", {"text": word})

        _record_episode(session_id, "assistant", text)
        _index_turn(indexer, user_text, text)
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
