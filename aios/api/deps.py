"""Shared FastAPI dependency providers for the API layer.

Extracted from ``aios/api/main.py`` (monolith split, 2026-07-06) so that route
modules under ``aios/api/routes/`` can depend on providers WITHOUT importing
``main`` (no import cycle) and WITHOUT redefining local proxy providers — the
proxy pattern silently breaks ``app.dependency_overrides`` because overrides
are keyed by function identity (the council-router seam documented in the
deep-audit report).

``main.py`` re-imports every name below, so the long-standing test idiom
``from aios.api.main import get_X`` keeps resolving to the SAME function
object and every existing dependency override remains valid.

Only STATELESS providers (fresh store constructors) and the self-contained
lazy cloud-client singletons live here. Providers entangled with ``main``'s
process state (approval store, session manager, executor/rate-limiter,
self-apply, edit snapshots, the memory compactor's singleton cluster) stay in
``main.py``.
"""

from __future__ import annotations

import os
import threading
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from fastapi import Depends, HTTPException, Request

from aios import config
from aios.agents.reflection_agent import ReflectionAgent
from aios.agents.rollback_engine import RollbackEngine
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.application.memory import MemoryAuthority
from aios.application.capabilities.authority import CapabilityAuthority
from aios.application.capabilities.verifier import CapabilityVerifier
from aios.application.action_broker import ActionBroker
from aios.application.governance import (
    EmergencyStopController,
    EmergencyStopHooks,
)
from aios.application.identity.service import IdentityService
from aios.application.memory.adapters import (
    AdvisoryPheromoneAdapter,
    EpisodicMemoryAdapter,
    LegacySemanticMemoryAdapter,
    MemoryConsolidationAdapter,
    MistakeMemoryAdapter,
    DevelopmentHistoryAdapter,
    SemanticFactsAdapter,
    SkillMemoryAdapter,
    WorkingMemoryAdapter,
)
from aios.core.autonomy import AutonomyLedger
from aios.core.alignment import AlignmentInterpreter
from aios.core.bedrock import BedrockClient
from aios.core.cerebellum import Cerebellum
from aios.core.executor import Executor
from aios.core.gemini import GeminiClient
from aios.core.llm import LLMClient, LLMError, OllamaClient
from aios.core.native_planner import NativePlanner
from aios.core.self_apply import DEFAULT_VERIFY_COMMAND, SelfApplyEngine
from aios.core.session_manager import SessionManager
from aios.domain.identity.models import Principal, PrincipalType
from aios.core.verifier import Verifier
from aios.memory.alignment_evaluation import AlignmentEvaluationStore
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.conversation import ConversationStateStore
from aios.memory.curriculum import CurriculumManager
from aios.memory.development import DevelopmentTracker
from aios.memory.episodic import EpisodicMemory
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory
from aios.memory.working import WorkingMemory
from aios.infrastructure.memory import MemoryAuthorityStore
from aios.security.audit_logger import log_action
from aios.security.gateway import RateLimiter, Zone

if TYPE_CHECKING:
    from aios.council.council_memory import CouncilMemory
    from aios.council.council_state import CouncilState
    from aios.policy.kernel import PolicyKernel

#: Lazy cloud-client singletons — built on first use, reused across requests.
_bedrock_client: Optional[BedrockClient] = None
_gemini_client: Optional[GeminiClient] = None
_openai_client: Optional[Any] = None
_anthropic_client: Optional[Any] = None
_bedrock_lock = threading.Lock()
_gemini_lock = threading.Lock()
_openai_lock = threading.Lock()
_anthropic_lock = threading.Lock()
_memory_authority: Optional[MemoryAuthority] = None
_memory_authority_lock = threading.Lock()
_identity_service: Optional[IdentityService] = None
_identity_service_lock = threading.Lock()
_emergency_stop: Optional[EmergencyStopController] = None
_emergency_stop_lock = threading.Lock()


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
    fresh each call (mirrors ``_router_policy``).
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
    fresh each call (mirrors ``_router_policy``).
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


def get_openai_client() -> Optional[Any]:
    """Provide the OpenAI-compatible chat client, or ``None`` when unconfigured."""
    global _openai_client
    if not config.OPENAI_ENABLED:
        return None
    if _openai_client is not None:
        return _openai_client
    with _openai_lock:
        if _openai_client is not None:
            return _openai_client
        from aios.core.openai_compat import OpenAICompatClient

        _openai_client = OpenAICompatClient()
    return _openai_client


def get_anthropic_client() -> Optional[Any]:
    """Provide the Anthropic direct chat client, or ``None`` when unconfigured."""
    global _anthropic_client
    if not config.ANTHROPIC_ENABLED:
        return None
    if _anthropic_client is not None:
        return _anthropic_client
    with _anthropic_lock:
        if _anthropic_client is not None:
            return _anthropic_client
        from aios.core.anthropic_direct import AnthropicDirectClient

        _anthropic_client = AnthropicDirectClient()
    return _anthropic_client


def get_semantic_indexer() -> Optional[Any]:
    """Provide the L3 semantic writer used to index completed chat turns.

    Returns ``None`` when :data:`aios.config.INDEX_CHAT` is disabled (so no
    embedding model is loaded). Overridden in tests with a fake recorder so the
    suite never loads the real embedder or mutates the on-disk vector index.
    """
    if not config.INDEX_CHAT:
        return None
    authority = get_memory_authority()
    adapter = authority.adapters.get("semantic")
    if adapter is None:
        raise RuntimeError("memory authority semantic adapter is unavailable")
    return adapter


def get_reflection_agent(
    llm: LLMClient = Depends(get_llm_client),
) -> Optional[ReflectionAgent]:
    """Provide the reflection agent that turns a command failure into a lesson.

    Returns ``None`` when :data:`aios.config.REFLECT_ON_FAILURE` is disabled.
    Reuses the injected LLM client so it is fully overridable in tests.
    """
    if not config.REFLECT_ON_FAILURE:
        return None
    authority = get_memory_authority()
    if isinstance(authority, MemoryAuthority):
        lessons = authority.adapters.get("lessons")
        store = getattr(lessons, "store", None)
        return ReflectionAgent(
            llm,
            mistakes=store if isinstance(store, MistakeMemory) else None,
            memory_authority=authority,
        )
    raise RuntimeError("MemoryAuthority is required for the reflection agent")


def get_swarm_pattern_memory() -> SwarmPatternMemory:
    """Provide the ant-colony swarm's decomposition-pattern memory."""
    return SwarmPatternMemory()


def _sync_pheromone_adapter(authority: MemoryAuthority) -> None:
    """Keep the advisory adapter aligned with the live configured store."""
    if not config.PHEROMONE_ENABLED:
        authority.pheromone_adapter = None
        return
    current = getattr(authority.pheromone_adapter, "store", None)
    configured_path = str(config.PHEROMONE_DB)
    if (
        isinstance(authority.pheromone_adapter, AdvisoryPheromoneAdapter)
        and current is not None
        and str(getattr(current, "_db_path", "")) == configured_path
        and getattr(current, "_lambda", None) == config.PHEROMONE_LAMBDA_DECAY
        and getattr(current, "_floor", None) == config.PHEROMONE_FLOOR
    ):
        return
    from aios.memory.pheromones import PheromoneStore

    authority.pheromone_adapter = AdvisoryPheromoneAdapter(
        PheromoneStore(
            db_path=config.PHEROMONE_DB,
            lambda_decay=config.PHEROMONE_LAMBDA_DECAY,
            floor=config.PHEROMONE_FLOOR,
        )
    )


def get_memory_authority() -> MemoryAuthority:
    """Provide the process-wide provenance and promotion authority for memory."""
    global _memory_authority
    if _memory_authority is not None:
        _sync_pheromone_adapter(_memory_authority)
        return _memory_authority
    with _memory_authority_lock:
        if _memory_authority is None:
            adapters = {
                "working": WorkingMemoryAdapter(WorkingMemory()),
                "episodic": EpisodicMemoryAdapter(EpisodicMemory()),
                "semantic": LegacySemanticMemoryAdapter(
                    SemanticMemory(config.MEMORY_DB_PATH)
                ),
                "facts": SemanticFactsAdapter(SemanticFacts()),
                "skills": SkillMemoryAdapter(SkillMemory()),
                "lessons": MistakeMemoryAdapter(MistakeMemory()),
                "development": DevelopmentHistoryAdapter(DevelopmentTracker()),
            }
            _memory_authority = MemoryAuthority(
                store=MemoryAuthorityStore(config.MEMORY_DB_PATH),
                adapters=adapters,
            )
            consolidation = MemoryConsolidationAdapter(
                MemoryConsolidator(
                    semantic=adapters["semantic"].store,
                    mistakes=adapters["lessons"].store,
                    facts=adapters["facts"].store,
                    memory_authority=_memory_authority,
                )
            )
            _memory_authority.register_adapter("consolidation", consolidation)
            _sync_pheromone_adapter(_memory_authority)
            consolidation.bind_authority(_memory_authority)
    return _memory_authority


def get_council_memory_scope(
    runtime_root: str | Path,
) -> tuple[CouncilState, CouncilMemory, MemoryAuthority]:
    """Build the mission-local Council memory scope from the canonical authority.

    Council evidence is isolated per runtime root, so it must not be attached to
    the process-wide registry.  The copied authority keeps every shared adapter
    intact while the scoped Council adapter owns the exact mission-local store.
    This composition root is the only API-layer owner of the physical Council
    state construction; routes receive the already-bound scope.
    """
    from aios.application.memory.adapters import CouncilMemoryAdapter
    from aios.council.council_memory import CouncilMemory
    from aios.council.council_state import CouncilState

    root = Path(runtime_root)
    council_state = CouncilState(db_path=root / "council_state.db")
    council_memory = CouncilMemory(state=council_state)
    authority = get_memory_authority().with_adapter(
        "council", CouncilMemoryAdapter(council_memory)
    )
    return council_state, council_memory, authority


def _authority_store(name: str, expected_type: type[Any]) -> Any:
    """Return a canonical specialist store or fail closed."""
    adapter = get_memory_authority().adapters.get(name)
    store = getattr(adapter, "store", None)
    if not isinstance(store, expected_type):
        raise RuntimeError(f"memory authority {name} store is unavailable")
    return store


def get_semantic_facts() -> SemanticFacts:
    """Provide the human-approved personalization facts store (REAL only).

    Reads the ``semantic_facts`` table (human-gated writes); returns an empty
    list when no facts exist, so the conversational endpoint stays honest —
    personalization is dormant, never fabricated, when nothing is known. Cheap
    and stateless (opens a fresh connection per call). Overridden in tests.
    """
    return _authority_store("facts", SemanticFacts)


def get_development_tracker(
    facts: SemanticFacts = Depends(get_semantic_facts),
    authority: MemoryAuthority = Depends(get_memory_authority),
) -> DevelopmentTracker:
    """Provide the canonical evidence-backed developmental metrics store.

    ``facts`` remains in the dependency graph for compatibility with routes
    that override that input with an isolated test double. It must never cause
    this provider to construct a parallel developmental store.
    """
    if not isinstance(authority, MemoryAuthority):
        raise RuntimeError("MemoryAuthority is required")
    return _authority_store("development", DevelopmentTracker)


def get_emergency_stop() -> EmergencyStopController:
    """Provide the one durable stop latch shared by production boundaries."""
    global _emergency_stop
    if _emergency_stop is not None:
        return _emergency_stop
    with _emergency_stop_lock:
        if _emergency_stop is None:
            from aios.application.workers.scheduler import WorkerScheduler
            from aios.application.missions.mission_service import MissionService

            def cancel_queued_work(reason: str = "emergency stop") -> int:
                return MissionService.cancel_registered_queued(
                    reason
                ) + WorkerScheduler.cancel_queued_registered(reason)

            _emergency_stop = EmergencyStopController(
                hooks=EmergencyStopHooks(
                    revoke_capabilities=_CAPABILITIES.revoke_all_active,
                    cancel_queued_missions=cancel_queued_work,
                    kill_active_workers=WorkerScheduler.cancel_active_registered,
                    disable_autonomy=AutonomyLedger().revoke_all,
                    preserve_evidence=lambda reason: log_action(
                        "emergency-stop", f"engaged: {reason}", Zone.RED
                    ),
                )
            )
    return _emergency_stop


def get_autonomy() -> AutonomyLedger:
    """Provide the earned-autonomy ledger (opt-in; off => never grants autonomy)."""
    return AutonomyLedger(emergency_stop=get_emergency_stop())


def get_cerebellum() -> Cerebellum:
    """Provide the compiled-experience engine (sovereignty S1)."""
    cb = Cerebellum()
    cb.try_compile_all()
    return cb


def get_skill_memory(
    cerebellum: Cerebellum = Depends(get_cerebellum),
    facts: SemanticFacts = Depends(get_semantic_facts),
    authority: MemoryAuthority = Depends(get_memory_authority),
) -> SkillMemory:
    """Provide verification-backed procedural skill memory.

    Wired to the same request-scoped cerebellum instance so that a skill's
    promotion to 'verified' (or demotion back to 'candidate') during this
    request immediately compiles (or decompiles) the matching playbook —
    the sovereignty engine stays in sync with skill trust status. The facts
    store enables S2 cross-store ingestion on skill promotion.
    """
    if not isinstance(authority, MemoryAuthority):
        raise RuntimeError("MemoryAuthority is required")
    return _authority_store("skills", SkillMemory)


def get_mistake_memory(
    facts: SemanticFacts = Depends(get_semantic_facts),
    authority: MemoryAuthority = Depends(get_memory_authority),
) -> MistakeMemory:
    """Provide mistake memory with knowledge graph ingestion wiring."""
    if not isinstance(authority, MemoryAuthority):
        raise RuntimeError("MemoryAuthority is required")
    return _authority_store("lessons", MistakeMemory)


def get_native_planner(
    skills: SkillMemory = Depends(get_skill_memory),
    patterns: SwarmPatternMemory = Depends(get_swarm_pattern_memory),
    facts: SemanticFacts = Depends(get_semantic_facts),
) -> NativePlanner:
    """Provide the sovereignty S3 native symbolic planner."""
    return NativePlanner(
        skills=skills,
        patterns=patterns,
        facts=facts,
        memory_authority=get_memory_authority(),
    )


def get_curriculum_manager() -> CurriculumManager:
    """Provide the non-autonomous curriculum evidence store."""
    return CurriculumManager()


def get_memory_consolidator() -> MemoryConsolidator:
    """Provide the authority-owned trusted-memory promotion service.

    The process authority owns the canonical consolidation adapter. Returning
    that wrapped service keeps route ownership checks on the authority path;
    dependency overrides can still provide explicit test doubles.
    """
    authority = get_memory_authority()
    adapter = authority.adapters.get("consolidation")
    service = getattr(adapter, "service", None)
    if not isinstance(service, MemoryConsolidator):
        raise RuntimeError("memory authority consolidation adapter is unavailable")
    return service


def get_conversation_state_store() -> ConversationStateStore:
    """Provide durable, unverified shared-understanding state."""
    return ConversationStateStore()


def get_alignment_evaluation_store() -> AlignmentEvaluationStore:
    """Provide diagnostic human-alignment evidence; it never changes policy."""
    return AlignmentEvaluationStore()


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
# Stateful / security-adjacent providers (tranche 2)
# _CAPABILITIES and _RATE_LIMITER are DB-backed (durable, multi-process safe by
# design); _SESSION_MANAGER holds the process's session state. They live here
# so route modules can Depends() on them without importing main. The former
# ApprovalStore compatibility surface is intentionally not constructed in the
# production dependency graph.
# --------------------------------------------------------------------------- #
_CAPABILITIES = CapabilityAuthority(db_path=config.CAPABILITY_DB_PATH)
_RATE_LIMITER = RateLimiter(db_path=config.APPROVAL_DB_PATH)

#: Server-side session manager with httpOnly cookie support.
#: Sessions are stored by SHA-256 hash only; the raw ID never leaves the server
#: except inside the httpOnly cookie response, and is never persisted.
_SESSION_MANAGER = SessionManager(
    max_age=3600,
    cleanup_interval=300,
    store_path=config.SESSION_DB_PATH,
)


def get_session_manager() -> SessionManager:
    """Provide the server-side session manager singleton."""
    return _SESSION_MANAGER


def get_identity_service() -> IdentityService:
    """Provide the durable Human Sovereign identity authority singleton."""
    global _identity_service
    if _identity_service is not None:
        return _identity_service
    with _identity_service_lock:
        if _identity_service is None:
            _identity_service = IdentityService(
                identity_db_path=config.IDENTITY_DB_PATH,
                session_db_path=config.SESSION_DB_PATH,
            )
    return _identity_service


def get_authenticated_principal(
    request: Request,
    identity: IdentityService = Depends(get_identity_service),
) -> Principal:
    """Resolve the operator only from the opaque server-side session cookie."""
    principal = identity.get_authenticated_principal(request.cookies.get("session_id"))
    if principal is None:
        raise HTTPException(
            status_code=401, detail="authenticated operator session required"
        )
    client_address = request.client.host if request.client is not None else ""
    return replace(
        principal,
        request_id=request.headers.get("x-request-id", ""),
        client_address=client_address,
    )


def require_privileged_operator(
    principal: Principal = Depends(get_authenticated_principal),
) -> Principal:
    """Require an authenticated Human Sovereign principal for control-plane work."""
    if principal.principal_type is not PrincipalType.OPERATOR:
        raise HTTPException(status_code=403, detail="Human Sovereign operator required")
    if principal.authentication_level != "privileged":
        raise HTTPException(
            status_code=403,
            detail="recent strong Human Sovereign re-authentication required",
        )
    return principal


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


def get_executor() -> Executor:
    """Provide the default executor; production crosses the private service."""
    kernel = get_policy_kernel()
    approved_runner = kernel.build_approved_runner()
    profile = os.environ.get("AIOS_PROFILE", "development").strip().lower()
    command_runner = (
        approved_runner
        if profile in {"production", "demo"}
        and getattr(approved_runner, "is_private_service", False)
        else None
    )
    return Executor(
        runner=command_runner,
        approved_runner=approved_runner,
        rate_limiter=_RATE_LIMITER,
        policy_kernel=kernel,
        emergency_stop=get_emergency_stop(),
    )


def get_capability_authority() -> CapabilityAuthority:
    """Provide the server-issued exact capability authority."""
    if _CAPABILITIES.emergency_stop is None:
        _CAPABILITIES.emergency_stop = get_emergency_stop()
    return _CAPABILITIES


def get_capability_verifier(
    authority: CapabilityAuthority = Depends(get_capability_authority),
) -> CapabilityVerifier:
    """Provide complete-binding capability verification for application routes."""
    return CapabilityVerifier(authority)


def get_policy_kernel() -> "PolicyKernel":
    """Provide the runtime policy kernel singleton.

    Delegates to :func:`aios.policy.kernel.get_policy_kernel` so every caller
    (route dependencies, the execution surface, and the router wiring) shares
    the same authority instance.
    """
    # Imported lazily to break the policy -> edge_security -> deps cycle.
    from aios.policy.kernel import get_policy_kernel as _kernel_singleton

    return _kernel_singleton(
        rate_limiter=_RATE_LIMITER,
        autonomy_ledger=AutonomyLedger(emergency_stop=get_emergency_stop()),
    )


def get_action_broker(
    kernel: "PolicyKernel" = Depends(get_policy_kernel),
    capabilities: CapabilityAuthority = Depends(get_capability_authority),
) -> ActionBroker:
    """Provide the production ActionEnvelope -> PolicyKernel broker chain."""
    return ActionBroker(kernel, capabilities=capabilities)


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
    isolated_runner = executor.approved_runner
    # Development/test callers may inject only the ordinary runner. Preserve
    # the legacy container-backed verifier contract for those callers while
    # keeping production/demo strictly dependent on the Executor Service
    # runner constructed by ``get_executor``.
    profile = os.environ.get("AIOS_PROFILE", "development").strip().lower()
    if isolated_runner is None and profile not in {"production", "demo"}:
        isolated_runner = get_policy_kernel().build_approved_runner()

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
            raise ValueError(
                "self-apply verifier accepts only the fixed project test command"
            )
        if isolated_runner is None:
            raise RuntimeError(
                "self-apply requires the container execution boundary; host mode "
                "refuses (set AIOS_APPROVED_EXECUTION_BACKEND=container and start the "
                "container runtime to apply proposals)"
            )
        return isolated_runner(
            "python -m pytest tests/ -q",
            cwd=str(config.PROJECT_ROOT.resolve()),
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


__all__ = [
    "get_llm_client",
    "get_ollama_client",
    "get_bedrock_client",
    "get_gemini_client",
    "get_openai_client",
    "get_anthropic_client",
    "get_semantic_indexer",
    "get_reflection_agent",
    "get_swarm_pattern_memory",
    "get_semantic_facts",
    "get_development_tracker",
    "get_autonomy",
    "get_cerebellum",
    "get_skill_memory",
    "get_mistake_memory",
    "get_native_planner",
    "get_curriculum_manager",
    "get_memory_consolidator",
    "get_memory_authority",
    "get_council_memory_scope",
    "get_conversation_state_store",
    "get_alignment_evaluation_store",
    "get_alignment_interpreter",
    "get_session_manager",
    "get_identity_service",
    "get_authenticated_principal",
    "require_privileged_operator",
    "get_executor",
    "get_policy_kernel",
    "get_rollback_engine",
    "get_self_apply_engine",
    "get_edit_snapshot",
    "get_local_workforce_registry",
    "get_local_workforce_service",
    "get_hiring_repository",
    "get_hiring_service",
    "get_cortex_observation_bus",
    "get_skill_repository",
    "get_maintenance_finding_repository",
    "get_maintenance_scan_repository",
    "get_maintenance_convergence_service",
    "get_learning_service",
]


def get_local_workforce_registry(
    ollama: OllamaClient = Depends(get_ollama_client),
) -> Any:
    """Provide the durable Local Workforce Registry (R15)."""
    from aios.domain.local_workforce.registry import LocalWorkforceRegistry

    return LocalWorkforceRegistry(ollama)


def get_local_workforce_service(
    registry: Any = Depends(get_local_workforce_registry),
    ollama: OllamaClient = Depends(get_ollama_client),
) -> Any:
    """Provide the application-layer local-workforce orchestration service."""
    from aios.application.local_workforce.service import LocalWorkforceService

    return LocalWorkforceService(registry=registry, ollama=ollama)


def get_hiring_repository() -> Any:
    """Provide the durable operational hiring-record repository."""
    from aios.domain.intelligence.repository import HiringRecordRepository

    return HiringRecordRepository(config.OPERATIONAL_STATE_DB_PATH)


def get_cortex_observation_bus() -> Any:
    """Provide the optional Cortex observation outbox without owning it."""
    from aios.api.main import get_cortex_bus

    return get_cortex_bus()


def get_hiring_service(
    ollama: Any = Depends(get_ollama_client),
    bedrock: Any = Depends(get_bedrock_client),
    gemini: Any = Depends(get_gemini_client),
    openai: Any = Depends(get_openai_client),
    anthropic: Any = Depends(get_anthropic_client),
    repository: Any = Depends(get_hiring_repository),
    cortex: Any = Depends(get_cortex_observation_bus),
    policy: Any = Depends(get_policy_kernel),
) -> Any:
    """Compose the canonical HiringBroker with injected runtime adapters."""
    from aios.application.models.hiring_service import (
        ChatProviderAdapter,
        IntelligenceHiringService,
    )
    from aios.core.router_wiring import _build_providers
    from aios.domain.intelligence.broker import HiringBroker

    raw_clients = {
        "ollama": ollama,
        "bedrock": bedrock,
        "gemini": gemini,
        "openai": openai,
        "anthropic": anthropic,
    }
    clients = {
        name: ChatProviderAdapter(client)
        for name, client in raw_clients.items()
        if client is not None
    }
    return IntelligenceHiringService(
        broker=HiringBroker(),
        providers=_build_providers(
            ollama,
            bedrock,
            gemini,
            openai=openai,
            anthropic=anthropic,
        ),
        clients=clients,
        repository=repository,
        cortex=cortex,
        policy=policy.router_policy(),
    )


def get_skill_repository() -> Any:
    """Provide the durable institutional-skill repository."""
    from aios.domain.learning.repository import SkillRepository

    return SkillRepository(config.OPERATIONAL_STATE_DB_PATH)


def get_maintenance_finding_repository() -> Any:
    """Provide the durable maintenance-finding repository."""
    from aios.domain.maintenance.repository import MaintenanceFindingRepository

    return MaintenanceFindingRepository(config.OPERATIONAL_STATE_DB_PATH)


def get_maintenance_scan_repository() -> Any:
    """Provide the durable bounded-scan metadata repository."""
    from aios.domain.maintenance.scan_repository import MaintenanceScanRepository

    return MaintenanceScanRepository(config.OPERATIONAL_STATE_DB_PATH)


def get_learning_service() -> Any:
    """Provide durable trajectory and skill reuse over canonical mission state."""
    from aios.application.learning.service import LearningService
    from aios.application.missions.mission_service import MissionService
    from aios.domain.learning.repository import SkillRepository
    from aios.domain.learning.trajectory_repository import TrajectoryRepository
    from aios.infrastructure.missions.sqlite_mission_repository import (
        SqliteMissionRepository,
    )
    from aios.policy.kernel import get_policy_kernel

    policy = get_policy_kernel()

    def reuse_policy(skill: Any, _context: dict[str, object]) -> bool:
        # PolicyKernel decides whether the advisory reuse class is enabled;
        # MissionService and the ordinary action boundary still govern work.
        return skill.state == "active" and policy.earned_autonomy_enabled()

    def verification_plan_validator(skill: Any) -> bool:  # noqa: C901
        """Strict typed SkillVerifierSpec validator — fails closed on any deviation.

        Rules (all must pass):
        1. Plan exists and is a SkillVerifierSpec — not None, not a str.
        2. verifier_id equals the canonical live value (``skill.reuse``).
        3. version equals the single supported value (``1``).
        4. target_pattern is non-empty and shell-free (enforced by the type).
        5. required_observations is non-empty (min_length=1 enforced by type).
        6. minimum_strength meets the policy floor (>= 1).
        7. No forbidden executable/command fields are present on the object.
        8. No unknown extra fields (extra="forbid" guards construction, but a
           subclass injection attempt is also rejected here by checking
           model_fields equality).
        """
        from aios.domain.verification import SkillVerifierSpec as _SVS

        _KNOWN_VERIFIER_ID = "skill.reuse"
        _KNOWN_VERSION = "1"
        _POLICY_MIN_STRENGTH = 1
        _FORBIDDEN = frozenset(
            {"command", "shell", "image", "program", "executable", "argv", "script", "cmd"}
        )

        plan = getattr(skill, "verification_plan", None)

        # Rule 1 — plan must be a typed SkillVerifierSpec.
        if plan is None:
            return False
        if isinstance(plan, str):
            return False  # legacy free-text — quarantined, not executable
        if not isinstance(plan, _SVS):
            return False

        # Rule 2 — known verifier_id.
        if getattr(plan, "verifier_id", None) != _KNOWN_VERIFIER_ID:
            return False

        # Rule 3 — supported version.
        if getattr(plan, "version", None) != _KNOWN_VERSION:
            return False

        # Rule 4 — non-empty target_pattern.
        target_pattern = getattr(plan, "target_pattern", None)
        if not target_pattern or not isinstance(target_pattern, str):
            return False

        # Rule 5 — non-empty required_observations.
        required_obs = getattr(plan, "required_observations", None)
        if not required_obs:
            return False

        # Rule 6 — minimum_strength meets the policy floor.
        min_strength = getattr(plan, "minimum_strength", 0)
        if not isinstance(min_strength, int) or min_strength < _POLICY_MIN_STRENGTH:
            return False

        # Rule 7 — no executable/command fields present.
        for forbidden in _FORBIDDEN:
            if getattr(plan, forbidden, None) is not None:
                return False

        # Rule 8 — no unknown extra fields.
        if frozenset(type(plan).model_fields) != frozenset(_SVS.model_fields):
            return False

        return True

    return LearningService(
        mission_service=MissionService(
            SqliteMissionRepository(config.MISSION_STATE_DB)
        ),
        trajectory_repository=TrajectoryRepository(config.OPERATIONAL_STATE_DB_PATH),
        skill_repository=SkillRepository(config.OPERATIONAL_STATE_DB_PATH),
        verification_plan_validator=verification_plan_validator,
        reuse_policy=reuse_policy,
    )


def get_maintenance_convergence_service() -> Any:
    """Provide canonical maintenance scan, repair, verification and rescan service."""
    from aios.application.evidence.verification import VerificationAuthority
    from aios.application.evidence.verifier_registry import VerifierRegistry
    from aios.application.executor.service import ExecutorService
    from aios.application.maintenance.service import MaintenanceConvergenceService
    from aios.application.missions.mission_service import MissionService
    from aios.application.promotion.authority import PromotionAuthority
    from aios.application.workers.foundry import WorkerFoundry
    from aios.application.workspaces import StagedWorkspaceManager
    from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
    from aios.domain.maintenance.repository import MaintenanceFindingRepository
    from aios.domain.maintenance.scan_repository import MaintenanceScanRepository
    from aios.infrastructure.missions.sqlite_mission_repository import (
        SqliteMissionRepository,
    )

    workspace_manager = StagedWorkspaceManager(
        config.DATA_DIR / "staged_maintenance",
        enrolled_roots=(config.PROJECT_ROOT,),
    )
    mission_service = MissionService(
        SqliteMissionRepository(config.MISSION_STATE_DB),
        workspace_manager=workspace_manager,
    )
    worker_foundry = WorkerFoundry(workspace_manager=workspace_manager)
    executor_service = ExecutorService(
        profile="production",
        runner=get_executor().execute,
        backend_name="private_service",
    )
    verification_authority = VerificationAuthority()
    promotion_authority = PromotionAuthority(
        workspace_manager,
        verification=verification_authority,
        emergency_stop=get_emergency_stop(),
    )
    lifecycle_engine = MaintenanceLifecycleEngine()

    return MaintenanceConvergenceService(
        finding_repository=MaintenanceFindingRepository(config.OPERATIONAL_STATE_DB_PATH),
        scan_repository=MaintenanceScanRepository(config.OPERATIONAL_STATE_DB_PATH),
        mission_service=mission_service,
        worker_foundry=worker_foundry,
        executor_service=executor_service,
        verifier_registry=VerifierRegistry(scanner_adapters={}),
        verification_authority=verification_authority,
        promotion_authority=promotion_authority,
        workspace_manager=workspace_manager,
        lifecycle_engine=lifecycle_engine,
    )
