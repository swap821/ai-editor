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
from typing import Callable, Iterator, Literal, Optional, Any, Sequence, cast

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import aios
from aios import config
from aios.logging_config import configure_logging, get_logger
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
    get_vertex_maas_client,
    get_autonomy,
    get_bedrock_client,
    get_cerebellum,
    get_conversation_state_store,
    get_curriculum_manager,
    get_development_tracker,
    get_emergency_stop,
    get_observability_authority,
    get_recovery_resumption_authority,
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
    get_optional_principal,
    require_privileged_operator,
    get_executor,
    get_action_broker,
    get_capability_authority,
    get_policy_kernel,
    get_rollback_engine,
    get_self_apply_engine,
    get_edit_snapshot,
    get_human_state_hypothesis_store,
    get_human_state_interpreter_authority,
    get_constitution_authority,
    get_operator_preference_store,
    get_operator_taste_model_authority,
    get_project_passport_store,
    get_project_understanding_authority,
    get_correction_record_store,
    get_correction_lineage_authority,
    get_representative_context_store,
    _session_id_from_request,
    _RATE_LIMITER,
    _SESSION_MANAGER,
)
from aios.api import http_middleware as _http_middleware  # noqa: E402
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
from aios.application.capabilities.authority import (
    CapabilityAuthority,
    CapabilityError,
    EmergencyStopHardWiringAuthority,
)
from aios.application.action_broker import ActionBroker, PolicyBrokerError
from aios.application.governance import EmergencyStopError
from aios.application.governance.constitution_authority import (
    ConstitutionAuthorityError,
)
from aios.application.intelligence.authenticated_chat import (
    AuthenticatedChatRepresentation,
)
from aios.application.identity.service import IdentityDegraded
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
from aios.memory.development import DevelopmentTracker
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
from aios.core.injection_scan import detect_injection

# Re-exported, not dead: aios/application/turns/generate_pipeline.py pulls
# `Zone` (and other names) off this module at runtime via _LIVE_NAMES /
# _refresh_main_bindings, a deliberate mutable API seam. ruff cannot see
# that reach-through and reports these as unused -- removing them on that
# advice broke four shield tests with `module 'aios.api.main' has no
# attribute 'Zone'` on 2026-09-03.
from aios.security.gateway import Zone, classify  # noqa: F401
from aios.security.secret_scanner import scan_and_redact

# Approval/rate-limit/session singletons moved to aios.api.deps (tranche 2).

#: Cloud chat-client singletons. Built lazily and reused across requests so we do
#: not re-run boto3/gcloud credential discovery on every turn. Enablement is still
#: checked per request so setting changes take effect without editing this module.
# Lazy cloud-client singletons moved to aios.api.deps (monolith split).

# ── Cortex bus W2 — singletons (None when CORTEX_BUS is off) ─────────────────
# The bus and its dispatcher are module-level so the lifespan can start/stop
# them and the generate endpoint can append to them without FastAPI Depends.
# Both are None when config.CORTEX_BUS is False — zero overhead on the hot path
# when the feature is off. Note the default is ON (aios/config.py: AIOS_CORTEX_BUS
# defaults True), so the normal path constructs them; set AIOS_CORTEX_BUS=0 to opt
# out. This comment claimed the opposite until 2026-08-04.
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
    # Organ 52: make structured logs survive the process that wrote them.
    # Attached FIRST, so the organ-42 recovery report below is itself captured
    # durably -- a crash report that only ever reached a dead process's stderr
    # is not evidence anyone can read afterwards.
    _observability = get_observability_authority()
    _log_path = _observability.enable_durable_logs()
    logger.info("observability_durable_logs", **_observability.durable_log_status())

    # Organ 42: surface missions whose last journalled transition is not
    # terminal -- i.e. those a crash interrupted mid-flight -- and prove the
    # journal saying so has not been altered.
    #
    # `resume_pending()` existed, was unit-tested, and had NO production caller
    # anywhere, so the journal recorded interruptions that nothing ever read.
    #
    # Deliberately REPORTS rather than re-drives: silently resuming a
    # half-promoted repair without a human decision is precisely the
    # unsupervised recovery this system refuses. `recovery_report()` never
    # raises, so the scan cannot block startup.
    _recovery = get_recovery_resumption_authority()
    _report = _recovery.recovery_report()
    if _report["integrity"] == "tampered":
        # Not fatal, but never quiet: recovery reads this journal to decide how
        # far a mission got, so an altered row misdirects recovery rather than
        # merely misreporting it.
        logger.error("mission_journal_tampered", **_report)
    elif _report["interrupted_count"]:
        logger.warning("missions_interrupted_pending_resumption", **_report)
    else:
        logger.info("missions_interrupted_pending_resumption", **_report)
    # Opt-in second injection layer: install the vector blocklist when enabled.
    # Best-effort — a model/load failure must never block startup, since the
    # regex layer remains the active defence.
    if config.INJECTION_VECTOR_SHIELD:
        try:
            from aios.security.injection_shield import InjectionShieldAuthority
            from aios.security.gateway import set_injection_shield

            set_injection_shield(InjectionShieldAuthority())
        except Exception as exc:  # noqa: BLE001 - enhancement; never block startup
            logger.warning(
                "Vector injection shield failed to load; regex layer remains active",
                exc_info=exc,
            )
    # Cortex bus W2: start the drainer only when the flag is set.  The bus
    # default is ON (config.CORTEX_BUS=True), so this block runs in the common
    # case; set AIOS_CORTEX_BUS=0 to skip it and get W1-identical behavior.
    # This comment claimed the default was OFF until 2026-08-04.
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


@app.exception_handler(EmergencyStopError)
async def _emergency_stop_error_handler(
    request: Request, exc: EmergencyStopError
) -> JSONResponse:
    """Organ 26: a single, centralized 503 for every emergency-stop refusal.

    Several routes (aios/api/routes/maintenance.py) already catch
    EmergencyStopError locally and return 503 themselves -- that per-route
    handling still runs first and is unaffected. This handler only catches
    the routes that previously let it escape uncaught (e.g. Council mission
    creation/execution, gated deep inside route_intelligence_request()),
    which FastAPI would otherwise turn into an unhandled 500. Centralizing
    here means every emergency-stop refusal is consistently 503 regardless
    of which route triggered it, closing the "503 vs uncaught" duplication
    this organ's own blocker named.
    """
    return JSONResponse(
        status_code=503,
        content={"detail": f"Emergency stop engaged: {exc}"},
    )


@app.exception_handler(IdentityDegraded)
async def _identity_degraded_handler(
    request: Request, exc: IdentityDegraded
) -> JSONResponse:
    """Organ 24: a single, centralized 503 for a genuinely degraded identity store.

    Every real call site that resolves a Principal (action_guard.py's direct
    call, deps.py's shared get_authenticated_principal dependency, auth.py,
    mirror.py) ultimately calls IdentityService.get_authenticated_principal(),
    which now raises IdentityDegraded instead of letting a raw sqlite3.Error
    escape as an unhandled 500 when the store itself is failing. One handler
    here means every route gets the same honest, fail-closed 503 regardless
    of which one triggered it -- no NEW action can be authorized while
    identity is degraded. Already-issued, in-flight actions are unaffected:
    nothing on a mission's execution path re-checks identity mid-flight, so
    they complete normally (freeze in place, not a hard stop).
    """
    return JSONResponse(
        status_code=503,
        content={"detail": f"identity service degraded: {exc}"},
    )


@app.exception_handler(ConstitutionAuthorityError)
async def _constitution_degraded_handler(
    request: Request, exc: ConstitutionAuthorityError
) -> JSONResponse:
    """Organ 25: one centralized 503 for every fail-closed constitution state.

    Mirrors the IdentityDegraded handler above, and for the same reason: the
    constitution is resolved from many call sites (the policy kernel,
    capability consumption, every Principal stamp, the mirror projection), and
    each of them must produce the same honest answer rather than a 500 that
    reads like a bug.

    Covers all three subclasses -- no enrolled sovereign, an operator identity
    that has changed since a session or capability was minted, and a store
    that is unreadable or holds a tampered row. In every case no NEW action
    can be authorized, because there is no constitution to authorize it under.
    """
    return JSONResponse(
        status_code=503,
        content={"detail": f"constitution unavailable: {exc}"},
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


# The API's middleware -- CORS, metrics, request context, API token,
# browser-or-token for mutations, approval-route rate limit -- lives in
# aios/api/http_middleware.py and is registered here in its original order.
_http_middleware.install(app)

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
from aios.api.routes.preferences import router as _preferences_router
from aios.api.routes.files import router as _files_router
from aios.api.routes.security import router as _security_router
from aios.api.routes.execution_debugger import router as _execution_debugger_router
from aios.api.routes.v10 import router as _v10_router
from aios.api.routes.mirror import router as _mirror_router
from aios.api.routes.governance import router as _governance_router
from aios.api.routes.local_workforce import router as _local_workforce_router
from aios.api.routes.hiring import router as _hiring_router
from aios.api.routes.skills import router as _skills_router
from aios.api.routes.maintenance import router as _maintenance_router

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
app.include_router(_preferences_router)
app.include_router(_files_router)
app.include_router(_security_router)
app.include_router(_execution_debugger_router)
app.include_router(_v10_router)
app.include_router(_mirror_router)
app.include_router(_governance_router)
app.include_router(_local_workforce_router)
app.include_router(_hiring_router)
app.include_router(_skills_router)
app.include_router(_maintenance_router)


# Re-exported from the middleware module: tests and older callers import these
# from `main`.
from aios.api.http_middleware import (  # noqa: E402,F401
    _LOOPBACK_HOSTS,
    _RATE_LIMIT_ENDPOINTS,
    _RATE_LIMIT_WINDOW_S,
    _ROUTE_AUTHORITY,
    _check_endpoint_rate_limit,
    _is_private_ip,
    _rate_limited_route_path,
    _real_client_ip,
    _validate_cors_origins,
    bind_request_context,
    endpoint_rate_limit,
    require_api_token,
    require_browser_or_token_for_mutations,
)


# Slices 2-3 of the main.py split (2026-10-18): the turn endpoints and their
# shared machinery live in aios/api/turn_http.py and aios/api/routes/{generate,chat}.py.
# Re-exported: generate_pipeline's _LIVE_NAMES seam and tests read them here.
from aios.api.turn_http import (  # noqa: F401 -- re-exported
    CHAT_SYSTEM_PROMPT,
    ChatRequest,
    GenerateRequest,
    _COMPACTOR,
    _COMPACTOR_LOCK,
    _CONVERSATION_HITS,
    _CONVERSATION_RATE_MAX,
    _CONVERSATION_RATE_WINDOW_S,
    _EPISODIC,
    _IMAGE_BLOCK_KEYS,
    _MEMORY_AUTHORITY,
    _SEMANTIC,
    _STEP_EVENTS,
    _VECTOR_INDEX,
    _WORKING,
    _build_turn_context,
    _check_prompt_injection,
    _enforce_conversation_rate_limit,
    _generate_action_envelope,
    _generate_capability_binding,
    _message_context_chars,
    _messages_have_images,
    _sse,
    _sse_writer,
    _stream_chat_chunks,
    _to_chat_messages,
    _validate_generate_action_payload,
    get_compactor,
)
from aios.api.routes.generate import generate, api_router as _generate_router  # noqa: F401
from aios.api.routes.chat import chat, api_router as _chat_router  # noqa: F401

app.include_router(_generate_router)
app.include_router(_chat_router)


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class MemoryCompactRequest(BaseModel):
    """Body for ``/memory/compact``."""

    dry_run: bool = Field(
        True,
        description="When True, preview what would be removed. False performs the sweep.",
    )


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


# ── TurnCoordinator helpers ──────────────────────────────────────────────────
# Slice 6: both /api/generate and /api/v1/chat resolve through one coordinator.
# The routes stay thin HTTP adapters; the coordinator owns turn identity, mode
# classification, and the common event contract.


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
    _record_human_state,
    _verify_target_key,
    _verify_target_keys,
    _workflow_step,
)


class HumanStateCorrectionRequest(BaseModel):
    """Body for ``/api/v1/chat/human-state/correct`` -- organ 30's real
    ground-truth correction. Never authoritative: ``grants_authority`` on
    the original hypothesis was already pinned ``False`` and this changes
    nothing about the turn that already happened."""

    turn_id: str = Field(..., min_length=1, max_length=200, alias="turnId")
    corrected_state: Literal[
        "frustrated", "rushed", "decisive", "uncertain", "exploratory", "neutral"
    ] = Field(..., alias="correctedState")
    session_id: str = Field("voice-session", alias="sessionId")


@app.post(
    "/api/v1/chat/human-state/correct",
    dependencies=[Depends(enforce_action_boundary)],
)
def correct_human_state(
    req: HumanStateCorrectionRequest,
    request: Request,
    human_state_store=Depends(get_human_state_hypothesis_store),
    principal: Principal | None = Depends(get_optional_principal),
) -> dict[str, Any]:
    """Organ 30: let the operator correct a ``human_state`` guess.

    The frame's own ``user_correctable=True`` has existed since the
    classifier shipped, but nothing ever gave a human a real place to
    exercise it -- this is that place. Records real ground truth against
    the exact turn being corrected; never re-classifies, never changes the
    reply already given, never gates anything. ``principal`` is best-effort
    (this route stays reachable from an unauthenticated local session by
    design); the correction is attributed to a real operator id when one
    is resolvable, and honestly to none when it is not.
    """
    session_id = _session_id_from_request(request, req.session_id)
    corrected = human_state_store.record_correction(
        session_id,
        req.turn_id,
        req.corrected_state,
        operator_id=principal.principal_id if principal is not None else None,
    )
    if not corrected:
        raise HTTPException(
            status_code=404,
            detail=f"no human-state hypothesis recorded for turn {req.turn_id!r}",
        )
    return {
        "turnId": req.turn_id,
        "correctedState": req.corrected_state,
        "recorded": True,
    }


@app.get(
    "/api/v1/chat/human-state/accuracy",
    dependencies=[Depends(enforce_action_boundary)],
)
def human_state_accuracy(
    human_state_store=Depends(get_human_state_hypothesis_store),
) -> dict[str, Any]:
    """Organ 30: the classifier's real measured accuracy against every
    correction recorded so far -- the honest answer to "not measured
    against real production traffic", computed from whatever real
    corrections exist rather than synthetic examples. An empty report
    (``total_corrected: 0``) is itself an honest signal, not an error."""
    return human_state_store.accuracy_report().as_dict()


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
