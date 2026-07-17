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
import json
import re
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

import aios
from aios import config
from aios.logging_config import configure_logging, get_logger, session_log_key
from aios.core.metrics import MetricsMiddleware
from aios.agents.reflection_agent import ReflectionAgent
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.agents.tool_agent import ToolAgent
from aios.core.autonomy import AutonomyLedger
from aios.core.cerebellum import Cerebellum
from aios.core.executor import Executor
from aios.core.confidence_filter import gate as confidence_gate
from aios.core.planner import (
    Planner,
    PlannerError,
    plan_to_prompt_block,
    serialize_plan,
)
from aios.core.events import (
    event_for_sse,
    CanonicalEvent,
    CanonicalEventType,
    TrustLevel,
    EventPhase,
)
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
    get_emergency_stop,
    get_gemini_client,
    get_llm_client,
    get_memory_consolidator,
    get_memory_authority,
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
    get_identity_service,
    get_authenticated_principal,
    require_privileged_operator,
    get_executor,
    get_action_broker,
    get_capability_authority,
    get_policy_kernel,
    get_rollback_engine,
    get_self_apply_engine,
    get_edit_snapshot,
    _session_id_from_request,
    _RATE_LIMITER,
    _SESSION_MANAGER,
)
from aios.interfaces.http import edge_security
from aios.policy.kernel import RouteAuthority
from aios.core import catalog, router, telemetry
from aios.core.bedrock import BedrockClient
from aios.core.gemini import CURATED_MODELS as GEMINI_CURATED_MODELS
from aios.core.gemini import GeminiClient
from aios.core.llm import LLMClient, LLMError, OllamaClient
from aios.application.turns import (
    RuntimeDeps,
    TurnContext,
    TurnCoordinator,
    TurnMode,
    production_handlers,
)
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
from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.application.action_broker import ActionBroker, PolicyBrokerError
from aios.api.action_guard import enforce_action_boundary
from aios.domain.actions.envelope import (
    ActionEnvelope,
    ActionType,
    Principal as EnvelopePrincipal,
)
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest, resource_digest
from aios.domain.identity.models import Principal
from aios.core.alignment import (
    AlignmentInterpreter,
    apply_user_corrections,
    frame_from_state,
)
from aios.core.native_planner import NativePlanner
from aios.memory.db import get_connection, init_memory_db
from aios.memory.alignment_evaluation import AlignmentEvaluationStore
from aios.memory.compaction import MemoryCompactor
from aios.application.memory.adapters import MemoryCompactionAdapter
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.conversation import ConversationStateStore
from aios.memory.curriculum import CurriculumManager
from aios.memory.relevance import signature as task_signature
from aios.memory.embeddings import VectorIndex
from aios.memory.fact_extraction import extract_candidates
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory
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
            raise RuntimeError(
                "AIOS_API_TOKEN must be at least 32 characters for non-loopback use"
            )
    backend_warning = get_policy_kernel().validate_execution_backend()
    if backend_warning:
        logger.warning("approved_execution_backend", detail=backend_warning)
    active_profile = get_policy_kernel().active_runtime_profile()
    logger.info("runtime_profile_active", profile=active_profile.name)
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
            _self_model_handler = SelfModelHandler(
                memory_authority=get_memory_authority()
            )
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
        logger.info(
            "boot_attestation",
            integrity=attestation["integrity"],
            spine_hash=attestation["hash"][:16],
        )
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


def get_cortex_bus() -> Optional[CortexBus]:
    """Return the live cortex bus, or None when the bus is off (default)."""
    return _cortex_bus if config.CORTEX_BUS else None


def _get_cortex_dispatcher() -> Optional[CortexBusDispatcher]:
    """Return the live dispatcher, or None when the bus is off (default)."""
    return _cortex_dispatcher if config.CORTEX_BUS else None


def _append_turn_completed(
    bus: Optional[CortexBus], session_id: str, turn_id: str
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
        canonical = CanonicalEvent(
            event_type=CanonicalEventType.TURN_COMPLETED.value,
            phase=EventPhase.NARRATIVE.value,
            status="completed",
            trust=TrustLevel.VERIFIED.value,
            source="aios.api.main",
            session_id=session_id,
            turn_id=turn_id,
            payload={"ts": datetime.now(timezone.utc).isoformat()},
        )
        bus.append(canonical)
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
    return edge_security.validate_cors_origins(origins)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_validate_cors_origins(config.API_CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-AIOS-Capability",
        "X-Correlation-ID",
        "X-Request-ID",
    ],
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
from aios.api.routes.mirror import router as _mirror_router
from aios.api.routes.governance import router as _governance_router

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
app.include_router(_mirror_router)
app.include_router(_governance_router)


@app.middleware("http")
async def bind_request_context(request: Request, call_next):
    """Stamp every request with a correlation id and bind a hashed session id."""
    from structlog.contextvars import bind_contextvars, clear_contextvars

    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    clear_contextvars()
    bind_contextvars(
        request_id=request_id, method=request.method, path=request.url.path
    )
    try:
        session_id = await edge_security.extract_session_id(
            request, allow_body_fallback=True
        )
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
_LOOPBACK_HOSTS = edge_security.LOOPBACK_HOSTS


def _is_private_ip(ip: str) -> bool:
    """Return True if *ip* is loopback, link-local, or RFC 1918/4193 address."""
    return edge_security.is_private_ip(ip)


def _real_client_ip(request: Request) -> str:
    """Return the best-effort real client IP for auth decisions."""
    return edge_security.real_client_ip(request)


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    """Protect API and schema surfaces; keep unauthenticated use loopback-only."""
    error = edge_security.check_api_token_or_loopback(request)
    if error is not None:
        return error
    return await call_next(request)


@app.middleware("http")
async def require_browser_or_token_for_mutations(request: Request, call_next):
    """CSRF/Mutation protection: block unauthenticated non-browser mutations."""
    error = edge_security.check_mutation_origin_or_token(request)
    if error is not None:
        return error
    return await call_next(request)


# --------------------------------------------------------------------------- #
# In-memory sliding-window rate limiter for sensitive API endpoints.
# Protects against brute-force on approval tokens, noisy control routes, and
# expensive evidence scans. Best-effort, per-process; the durable RateLimiter
# governs RED actions. The route authority map is metadata only here: it
# centralizes API-surface posture without becoming a new security authority.
# --------------------------------------------------------------------------- #
_RATE_LIMIT_WINDOW_S = 60.0


# Route authority and per-endpoint rate limiting are owned by the PolicyKernel.
# Force lazy initialization now (this module is the runtime assembly point).
_POLICY_KERNEL = get_policy_kernel()
# Keep backward-compatible aliases so existing tests can import them from main.
_ROUTE_AUTHORITY = _POLICY_KERNEL.route_table
_RATE_LIMIT_ENDPOINTS = _POLICY_KERNEL.rate_limit_endpoints
_RATE_LIMIT_HITS = _POLICY_KERNEL.endpoint_hits


def _rate_limited_route_path(request: Request) -> str | None:
    """Return the literal or templated route key used by the rate limiter."""
    return _POLICY_KERNEL.rate_limited_route_path(request.url.path)


def _check_endpoint_rate_limit(path: str, client_ip: str) -> None:
    """Backward-compatible alias for the kernel's endpoint rate-limit check."""
    return _POLICY_KERNEL.check_endpoint_rate_limit(path, client_ip)


@app.middleware("http")
async def endpoint_rate_limit(request: Request, call_next):
    """Preflight only the legacy approval parser that can reject before broker.

    Ordinary routes are counted by ``PolicyKernel``.  The approval-resume
    route still inspects a bearer from its body before it can reach its broker
    call, so this uses the same kernel bucket to prevent invalid-token floods.
    """
    if request.method != "OPTIONS" and request.url.path == "/api/v1/approval/req":
        try:
            _POLICY_KERNEL.check_endpoint_rate_limit(
                "/api/v1/approval/req", edge_security.real_client_ip(request)
            )
        except HTTPException:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded for /api/v1/approval/req"},
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
                get_memory_authority().register_adapter(
                    "compaction", MemoryCompactionAdapter(_COMPACTOR)
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

    messages: list[dict[str, Any]] = Field(
        default_factory=lambda: cast(list[dict[str, Any]], [])
    )
    model_id: Optional[str] = Field(None, alias="modelId")
    session_id: str = Field("ui-session", alias="sessionId")
    approval_tokens: list[str] = Field(default_factory=list, alias="approvalTokens")
    #: Commands the human has authorised for this turn. When the agent pauses on
    #: a YELLOW command, the frontend re-sends the turn with that command added
    #: here so it actually runs (resumable in-chat approval — blueprint Q5).
    approved_commands: list[str] = Field(default_factory=list, alias="approvedCommands")
    #: File edits the human has authorised this turn (the edit analog of
    #: ``approvedCommands``), each ``{filepath, old_string, new_string}``.
    approved_edits: list[dict[str, Any]] = Field(
        default_factory=list, alias="approvedEdits"
    )
    #: New files the human has authorised this turn (the create analog of
    #: ``approvedEdits``), each ``{filepath, content}``.
    approved_creations: list[dict[str, Any]] = Field(
        default_factory=list, alias="approvedCreations"
    )
    #: Experimental role-pass selector. It is intentionally not production
    #: selected until WorkerFoundry owns its lifecycle.
    role_pass: bool = Field(False, alias="rolePass")
    #: Experimental swarm selector. It is intentionally not production selected
    #: until WorkerFoundry owns its lifecycle. Takes precedence over rolePass
    #: when both are set for the refusal message.
    swarm: bool = Field(False, alias="swarm")
    #: Explicitly opt into mission authority for this turn.  The route no
    #: longer upgrades every forge request to mission mode implicitly.
    mission_requested: bool = Field(False, alias="missionRequested")
    #: Explicit governance semantics are separate from mission semantics.
    governance_requested: bool = Field(False, alias="governanceRequested")

    model_config = {"populate_by_name": True}


def _generate_capability_binding(
    principal: Principal,
    action_type: str,
    payload: dict[str, Any],
    *,
    route: str = "/api/generate",
) -> CapabilityBinding:
    """Bind one generate approval to the authenticated human and exact action."""
    if action_type not in {"command", "edit", "create"}:
        raise CapabilityError(f"unsupported generate capability action: {action_type}")
    return CapabilityBinding(
        operator_id=principal.principal_id,
        device_id=principal.device_id,
        authentication_event_id=principal.authentication_event_id,
        session_id=principal.session_id,
        action_type=action_type,
        route=route,
        http_method="POST",
        payload_digest=payload_digest(payload),
        resource_digest=resource_digest({"workspace": "training_ground"}),
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope="training_ground/",
        verification_requirement=(
            "command_exit_zero"
            if action_type == "command"
            else "write_auto_verify_pass"
        ),
    )


def _generate_action_envelope(
    principal: Principal,
    request: Request,
    action_type: str,
    payload: dict[str, Any],
) -> ActionEnvelope:
    """Build the R4 envelope for one streamed generate approval."""
    return ActionEnvelope(
        route="/api/generate",
        action_type=ActionType.GENERATE,
        http_method="POST",
        payload=payload,
        principal=EnvelopePrincipal(
            session_id=principal.session_id,
            actor_source="session",
            client_ip=principal.client_address or "127.0.0.1",
        ),
        request_id=principal.request_id or request.headers.get("x-request-id"),
        operator_id=principal.principal_id,
        device_id=principal.device_id,
        authentication_event_id=principal.authentication_event_id,
        resource={"workspace": "training_ground"},
        requested_capability=f"generate.{action_type}",
        correlation_id=(
            request.headers.get("x-correlation-id")
            or principal.request_id
            or request.headers.get("x-request-id")
            or str(uuid.uuid4())
        ),
    )


def _validate_generate_action_payload(
    action_type: str,
    payload: object,
) -> dict[str, Any]:
    """Accept only the server-issued payload shapes the tool loop can replay."""
    if not isinstance(payload, dict):
        raise CapabilityError("generate capability payload is not an object")
    required = {
        "command": ("command",),
        "edit": ("filepath", "old_string", "new_string"),
        "create": ("filepath", "content"),
    }.get(action_type)
    if required is None or any(
        not isinstance(payload.get(key), str) for key in required
    ):
        raise CapabilityError("generate capability payload is malformed")
    if any(
        not str(payload[key]).strip()
        for key in required
        if key in {"command", "filepath"}
    ):
        raise CapabilityError("generate capability payload contains an empty target")
    return dict(payload)


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


@app.post("/api/v1/memory/compact", dependencies=[Depends(enforce_action_boundary)])
def memory_compact(
    req: MemoryCompactRequest,
    _principal: Any = Depends(require_privileged_operator),
    compactor: MemoryCompactor = Depends(get_compactor),
    authority=Depends(get_memory_authority),
) -> JSONResponse:
    """Operator-triggered memory compaction (audited "sleep" sweep).

    Defaults to ``dry_run=True`` so the caller MUST explicitly set
    ``dry_run=false`` to mutate stores. Returns a preview of what would be
    removed when dry-run is enabled; when disabled, performs the sweep and
    writes one audit entry under actor ``sleep-consolidation``.
    """
    authority_adapters = getattr(authority, "adapters", {})
    if "compaction" in authority_adapters and authority.owns_store(
        "compaction", compactor
    ):
        result = authority.compact_memory(dry_run=req.dry_run)
    else:
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
        event_obj = event_for_sse(event, data, turn_id=turn_id, seq=seq)
        data = event_obj.to_sse_payload()

        bus = get_cortex_bus()
        if bus is not None:
            # Opportunistic mapping to a canonical event for the truthful journal
            canonical_type = event
            if event == "turn.started":
                canonical_type = CanonicalEventType.TURN_STARTED.value
            elif event == "route":
                canonical_type = CanonicalEventType.ROUTE_SELECTED.value
            elif event == "human_required":
                canonical_type = CanonicalEventType.APPROVAL_REQUIRED.value
            elif event == "done":
                canonical_type = CanonicalEventType.TURN_COMPLETED.value
            elif event == "error":
                canonical_type = CanonicalEventType.TURN_FAILED.value

            canonical = CanonicalEvent(
                event_type=canonical_type,
                phase=event_obj.phase.value,
                status=(
                    "completed"
                    if event == "done"
                    else "failed"
                    if event == "error"
                    else "in_progress"
                ),
                trust=TrustLevel.ADVISORY.value,
                source="aios.api.main.sse",
                session_id=turn_id,
                turn_id=turn_id,
                sequence=seq,
                payload=data,
            )
            try:
                bus.append(canonical)
            except Exception:
                pass
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

#: Process-wide memory facades are all authority-owned adapters.  The
#: compatibility names remain because the compactor and legacy tests consume
#: these narrow interfaces.
_MEMORY_AUTHORITY = get_memory_authority()
_EPISODIC = _MEMORY_AUTHORITY.adapters["episodic"]
_WORKING = _MEMORY_AUTHORITY.adapters["working"]
_SEMANTIC = _MEMORY_AUTHORITY.adapters["semantic"]

#: FAISS vector index exposed by the authority-owned semantic adapter.
_VECTOR_INDEX = _SEMANTIC.index

#: Process-wide audited memory compactor so working-session touch timestamps are
#: preserved across independent FastAPI dependency injections.
_COMPACTOR: Optional[MemoryCompactor] = None
_COMPACTOR_LOCK = threading.Lock()


# ── TurnCoordinator helpers ──────────────────────────────────────────────────
# Slice 6: both /api/generate and /api/v1/chat resolve through one coordinator.
# The routes stay thin HTTP adapters; the coordinator owns turn identity, mode
# classification, and the common event contract.


def _build_turn_context(
    session_id: str,
    directive: str,
    *,
    model_id: Optional[str] = None,
    approval_tokens: Optional[list[str]] = None,
    mission_requested: bool = False,
    governance_requested: bool = False,
    data_classification: str = "PROJECT_INTERNAL",
) -> TurnContext:
    """Create a canonical TurnContext for the current directive."""
    mode = TurnCoordinator.classify_mode(
        directive,
        mission_requested=mission_requested,
        governance_requested=governance_requested,
    )
    return TurnContext(
        turn_id=str(uuid.uuid4()),
        session_id=session_id,
        operator_id=None,
        project_id=None,
        directive=directive,
        mode=mode,
        model_id=model_id,
        approval_tokens=tuple(approval_tokens or []),
        data_classification=data_classification,
        correlation_id=str(uuid.uuid4()),
    )


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


@app.post("/api/generate", dependencies=[Depends(enforce_action_boundary)])
def generate(
    req: GenerateRequest,
    request: Request,
    _principal: Principal = Depends(require_privileged_operator),
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
    capabilities: CapabilityAuthority = Depends(get_capability_authority),
    broker: ActionBroker = Depends(get_action_broker),
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
    alignment_evaluation: AlignmentEvaluationStore = Depends(
        get_alignment_evaluation_store
    ),
    alignment_interpreter: Optional[AlignmentInterpreter] = Depends(
        get_alignment_interpreter
    ),
    facts: SemanticFacts = Depends(get_semantic_facts),
    memory_authority=Depends(get_memory_authority),
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
    # Agentic generation can execute tools and therefore must be bound to the
    # authenticated operator session.  The legacy body sessionId remains part
    # of the request model for compatibility, but it is never authoritative.
    session_id = _principal.session_id
    _enforce_conversation_rate_limit(session_id)
    if len(user_text) > 2000:
        raise HTTPException(status_code=422, detail="Input exceeds 2000 characters.")
    if injection_reason := _check_prompt_injection(user_text):
        raise HTTPException(
            status_code=400, detail=f"[SECURITY BLOCK] {injection_reason}"
        )

    ctx = _build_turn_context(
        session_id,
        user_text,
        model_id=req.model_id,
        approval_tokens=req.approval_tokens,
        mission_requested=req.mission_requested,
        governance_requested=req.governance_requested,
    )
    runtime = RuntimeDeps(
        chat_client=client,
        bedrock=bedrock,
        gemini=gemini,
        openai_client=openai_client,
        anthropic_client=anthropic_client,
        executor=executor,
        indexer=indexer,
        reflector=reflector,
        snapshot=snapshot,
        planner_llm=planner_llm,
        mistakes=mistakes,
        development=development,
        skills=skills,
        swarm_patterns=swarm_patterns,
        autonomy=autonomy,
        curriculum=curriculum,
        cerebellum=cerebellum,
        consolidator=consolidator,
        conversation_state=conversation_state,
        alignment_evaluation=alignment_evaluation,
        alignment_interpreter=alignment_interpreter,
        facts=facts,
        memory_authority=memory_authority,
        compactor=compactor,
        extra={
            "route": "/api/generate",
            "request_model": req,
            "http_request": request,
            "principal": _principal,
            "capabilities": capabilities,
            "broker": broker,
        },
    )
    from aios.application.turns.generate_pipeline import (
        prepare_generate_state,
        stream_generate,
    )

    turn = TurnCoordinator(
        deps=runtime,
        handlers=production_handlers(
            stream_generate,
            preparer=prepare_generate_state,
        ),
    ).coordinate(ctx)
    return StreamingResponse(
        turn.events,
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


@app.post("/api/v1/chat", dependencies=[Depends(enforce_action_boundary)])
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
    memory_authority=Depends(get_memory_authority),
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
    authority_adapters = getattr(memory_authority, "adapters", {})
    if "compaction" in authority_adapters and memory_authority.owns_store(
        "compaction", compactor
    ):
        memory_authority.touch_working_session(session_id)
    else:
        compactor.touch_working_session(session_id)
    _enforce_conversation_rate_limit(session_id)
    user_text = req.transcript.strip()
    if injection_reason := _check_prompt_injection(user_text):
        raise HTTPException(
            status_code=400, detail=f"[SECURITY BLOCK] {injection_reason}"
        )

    ctx = _build_turn_context(
        session_id,
        user_text,
        model_id=req.model_id,
        approval_tokens=[],
    )

    # The application handler owns provider selection, prompt construction,
    # streaming, persistence, and terminal lifecycle.  The HTTP route only
    # supplies validated input plus injected infrastructure callbacks.
    task = infer_task(user_text)
    turn = TurnCoordinator(
        deps=RuntimeDeps(
            bedrock=bedrock,
            gemini=gemini,
            openai_client=openai_client,
            anthropic_client=anthropic_client,
            indexer=indexer,
            facts=facts,
            memory_authority=memory_authority,
            compactor=compactor,
            extra={
                "route": "/api/v1/chat",
                "user_text": user_text,
                "model_id": req.model_id,
                "task": task,
                "select_chat_client": lambda selected_task: _select_chat_client(
                    req.model_id,
                    client,
                    bedrock,
                    gemini=gemini,
                    openai=openai_client,
                    anthropic=anthropic_client,
                    task=selected_task,
                    data_classification=ctx.data_classification,
                ),
                "active_route": _active_route,
                "sse_writer": _sse_writer,
                "stream_chat_chunks": _stream_chat_chunks,
                "record_episode": _record_episode,
                "index_turn": _index_turn,
                "operator_facts_block": _operator_facts_block,
                "recall_memory": _recall_memory,
                "chat_system_prompt": CHAT_SYSTEM_PROMPT,
                "facts_auto_extract": config.FACTS_AUTO_EXTRACT,
                "facts_auto_extract_max": config.FACTS_AUTO_EXTRACT_MAX_PER_TURN,
                "cortex_bus": _cortex_bus,
                "logger": logger,
                "telemetry": telemetry,
                "task_signature": task_signature,
                "ollama_provider": router.PROVIDER_OLLAMA,
                "auto_ids": _AUTO_IDS,
            },
        ),
        handlers=production_handlers(),
    ).coordinate(ctx)
    return StreamingResponse(
        turn.events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/terminal", dependencies=[Depends(enforce_action_boundary)])
def terminal(
    req: TerminalRequest,
    request: Request,
    _principal: Principal = Depends(require_privileged_operator),
    executor: Executor = Depends(get_executor),
    broker: ActionBroker = Depends(get_action_broker),
) -> dict[str, Any]:
    """Run a UI-terminal command through the security gateway + sandbox.

    Returns the front-end terminal's ``{output, isError}`` shape. The command is
    classified and gated exactly like an agent action: RED is blocked, YELLOW is
    reported as needing approval, and only GREEN runs in the scope-locked
    sandbox. Every outcome is audited by the executor.
    """
    # Shell-command approval capabilities are bound to the validated browser
    # session.  Ignore the legacy body field so it cannot select another
    # principal or smuggle a privileged session through JSON.
    session_id = _principal.session_id
    payload = {"command": req.command}
    envelope = ActionEnvelope(
        route=request.url.path,
        action_type=ActionType.COMMAND,
        http_method=request.method,
        payload=payload,
        principal=EnvelopePrincipal(
            session_id=_principal.session_id,
            actor_source="session",
            client_ip=_principal.client_address or "127.0.0.1",
        ),
        request_id=_principal.request_id or request.headers.get("x-request-id"),
        operator_id=_principal.principal_id,
        device_id=_principal.device_id,
        authentication_event_id=_principal.authentication_event_id,
        resource={"workspace": "training_ground"},
        requested_capability="command.execute",
        correlation_id=(
            request.headers.get("x-correlation-id")
            or _principal.request_id
            or request.headers.get("x-request-id")
            or str(uuid.uuid4())
        ),
    )
    try:
        decision = broker.submit(
            envelope,
            capability_binding=_generate_capability_binding(
                _principal,
                "command",
                payload,
                route="/api/terminal",
            ),
        )
    except PolicyBrokerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if decision.blocked:
        return {"output": f"[BLOCKED] {decision.reason}", "isError": True}
    if decision.requires_approval:
        return {
            "output": f"[APPROVAL REQUIRED] {decision.reason}",
            "isError": False,
            "requiresApproval": True,
            "approvalToken": decision.approval_token,
            "command": req.command,
        }

    result = executor.execute(req.command, session_id=session_id)

    if result.status == "OK":
        output = (result.stdout or "") + (result.stderr or "")
        return {
            "output": output.strip() or "(no output)",
            "isError": bool(result.exit_code),
        }
    if result.status == "REQUIRE_APPROVAL":
        raise HTTPException(
            status_code=500,
            detail="executor disagreed with ActionBroker decision",
        )
    # BLOCKED / TIMEOUT / ERROR
    return {"output": f"[{result.status}] {result.reason}", "isError": True}


# Re-exports for backward compat — tests import these from aios.api.main
from aios.api.routes.voice import _get_stt_service, _get_tts_service  # noqa: F401, E402
from aios.api.routes.council import get_council_runtime_root  # noqa: F401, E402
