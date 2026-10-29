"""``/api/generate`` -- moved out of ``aios/api/main.py`` (2026-10-18).

Behaviour unchanged; ``main`` includes this router and re-exports ``generate``.
"""

from __future__ import annotations

from fastapi import APIRouter

from aios.agents.reflection_agent import ReflectionAgent
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import (
    get_action_broker,
    get_alignment_evaluation_store,
    get_alignment_interpreter,
    get_anthropic_client,
    get_autonomy,
    get_bedrock_client,
    get_capability_authority,
    get_cerebellum,
    get_conversation_state_store,
    get_curriculum_manager,
    get_development_tracker,
    get_edit_snapshot,
    get_emergency_stop,
    get_executor,
    get_gemini_client,
    get_llm_client,
    get_memory_authority,
    get_memory_consolidator,
    get_mistake_memory,
    get_native_planner,
    get_ollama_client,
    get_openai_client,
    get_reflection_agent,
    get_representative_context_store,
    get_semantic_facts,
    get_semantic_indexer,
    get_skill_memory,
    get_swarm_pattern_memory,
    get_vertex_maas_client,
    require_privileged_operator,
)
from aios.api.turn_http import (
    GenerateRequest,
    _build_turn_context,
    _check_prompt_injection,
    _enforce_conversation_rate_limit,
    _to_chat_messages,
    get_compactor,
)
from aios.api.turn_pipeline import _latest_user
from aios.application.action_broker import ActionBroker
from aios.application.capabilities.authority import (
    CapabilityAuthority,
    EmergencyStopHardWiringAuthority,
)
from aios.application.turns import (
    RuntimeDeps,
    TurnCoordinator,
    production_handlers,
)
from aios.application.turns.task_scope import (
    TaskScopeError,
    bound_preparer,
    bound_stream_factory,
    resolve_task_scope,
)
from aios.core.alignment import AlignmentInterpreter
from aios.core.autonomy import AutonomyLedger
from aios.core.bedrock import BedrockClient
from aios.core.cerebellum import Cerebellum
from aios.core.executor import Executor
from aios.core.gemini import GeminiClient
from aios.core.llm import (
    LLMClient,
    OllamaClient,
)
from aios.core.native_planner import NativePlanner
from aios.domain.identity.models import Principal
from aios.memory.alignment_evaluation import AlignmentEvaluationStore
from aios.memory.compaction import MemoryCompactor
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.conversation import ConversationStateStore
from aios.memory.curriculum import CurriculumManager
from aios.memory.development import DevelopmentTracker
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory
from fastapi import (
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import StreamingResponse
from typing import (
    Any,
    Callable,
    Optional,
)


api_router = APIRouter()


@api_router.post("/api/generate", dependencies=[Depends(enforce_action_boundary)])
def generate(
    req: GenerateRequest,
    request: Request,
    _principal: Principal = Depends(require_privileged_operator),
    client: OllamaClient = Depends(get_ollama_client),
    bedrock: Optional[BedrockClient] = Depends(get_bedrock_client),
    gemini: Optional[GeminiClient] = Depends(get_gemini_client),
    openai_client: Optional[Any] = Depends(get_openai_client),
    anthropic_client: Optional[Any] = Depends(get_anthropic_client),
    vertex_maas_client: Optional[Any] = Depends(get_vertex_maas_client),
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
    emergency_stop=Depends(get_emergency_stop),
    representative_context_store=Depends(get_representative_context_store),
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
    # Organ 32 / foundation law "human can stop, revoke and correct".
    #
    # The forge is the highest-traffic model path in the repo and had NO
    # emergency-stop check on its model call at all: the stop is only reached
    # from CapabilityAuthority.issue()/.consume(), which a read-only GREEN turn
    # never triggers, and ToolAgent.run() does not enter the gateway. So the
    # agent kept reasoning after the operator hit stop.
    EmergencyStopHardWiringAuthority.assert_operational(
        emergency_stop, boundary="api-main"
    )

    # Per-task scope (aios/application/turns/task_scope.py): declared by the
    # client or the launch environment, never by the model, and refused when
    # it cannot be honoured rather than run unbound.
    try:
        task_scope = resolve_task_scope(req.scope_root)
    except TaskScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        llm_client=client,
        chat_client=client,
        bedrock=bedrock,
        gemini=gemini,
        openai_client=openai_client,
        anthropic_client=anthropic_client,
        vertex_maas_client=vertex_maas_client,
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
            "emergency_stop": emergency_stop,
            "representative_context_store": representative_context_store,
        },
    )
    from aios.application.turns.generate_pipeline import (
        prepare_generate_state,
        stream_generate,
    )

    stream_factory, preparer = stream_generate, prepare_generate_state
    if task_scope is not None:
        # Prepared inside the binding (the reflex match reads the scope), and
        # streamed with it bound step by step: each step may run on another
        # thread-pool thread.
        stream_factory = bound_stream_factory(stream_generate, task_scope)
        preparer = bound_preparer(prepare_generate_state, task_scope)
    turn = TurnCoordinator(
        deps=runtime,
        handlers=production_handlers(stream_factory, preparer=preparer),
    ).coordinate(ctx)
    return StreamingResponse(
        turn.events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
