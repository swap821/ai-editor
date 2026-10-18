"""``/api/v1/chat`` -- moved out of ``aios/api/main.py`` (2026-10-18).

Behaviour unchanged; ``main`` includes this router and re-exports ``chat``.
"""

from __future__ import annotations

from fastapi import APIRouter

from aios import config
from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import (
    _session_id_from_request,
    get_anthropic_client,
    get_bedrock_client,
    get_constitution_authority,
    get_conversation_state_store,
    get_correction_lineage_authority,
    get_correction_record_store,
    get_emergency_stop,
    get_gemini_client,
    get_human_state_hypothesis_store,
    get_human_state_interpreter_authority,
    get_memory_authority,
    get_ollama_client,
    get_openai_client,
    get_operator_preference_store,
    get_operator_taste_model_authority,
    get_optional_principal,
    get_project_passport_store,
    get_project_understanding_authority,
    get_representative_context_store,
    get_semantic_facts,
    get_semantic_indexer,
    get_vertex_maas_client,
)
from aios.api.turn_http import (
    CHAT_SYSTEM_PROMPT,
    ChatRequest,
    _build_turn_context,
    _check_prompt_injection,
    _enforce_conversation_rate_limit,
    _sse_writer,
    _stream_chat_chunks,
    get_compactor,
)
from aios.api.turn_pipeline import (
    _index_turn,
    _operator_facts_block,
    _recall_memory,
    _record_episode,
    _record_human_state,
)
from aios.application.capabilities.authority import EmergencyStopHardWiringAuthority
from aios.application.intelligence.authenticated_chat import (
    AuthenticatedChatRepresentation,
)
from aios.application.turns import (
    RuntimeDeps,
    TurnCoordinator,
    production_handlers,
)
from aios.core import (
    router,
    telemetry,
)
from aios.core.bedrock import BedrockClient
from aios.core.gemini import GeminiClient
from aios.core.llm import OllamaClient
from aios.core.model_selector import infer_task
from aios.core.router_wiring import (
    _AUTO_IDS,
    _active_route,
    _select_chat_client,
)
from aios.domain.identity.models import Principal
from aios.memory.compaction import MemoryCompactor
from aios.memory.conversation import ConversationStateStore
from aios.memory.facts import SemanticFacts
from aios.memory.relevance import signature as task_signature
from aios.memory.semantic import SemanticMemory
from fastapi import (
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import StreamingResponse
from typing import (
    Any,
    Optional,
)


def _main():
    """aios.api.main, read at CALL time: it owns the cortex bus and the API
    logger, and importing it at import time would be circular."""
    from aios.api import main

    return main


api_router = APIRouter()


@api_router.post("/api/v1/chat", dependencies=[Depends(enforce_action_boundary)])
def chat(
    req: ChatRequest,
    request: Request,
    client: OllamaClient = Depends(get_ollama_client),
    bedrock: Optional[BedrockClient] = Depends(get_bedrock_client),
    gemini: Optional[GeminiClient] = Depends(get_gemini_client),
    openai_client: Optional[Any] = Depends(get_openai_client),
    anthropic_client: Optional[Any] = Depends(get_anthropic_client),
    vertex_maas_client: Optional[Any] = Depends(get_vertex_maas_client),
    indexer: Optional[SemanticMemory] = Depends(get_semantic_indexer),
    facts: SemanticFacts = Depends(get_semantic_facts),
    compactor: MemoryCompactor = Depends(get_compactor),
    memory_authority=Depends(get_memory_authority),
    human_state_store=Depends(get_human_state_hypothesis_store),
    human_state_interpreter=Depends(get_human_state_interpreter_authority),
    principal: Principal | None = Depends(get_optional_principal),
    constitution_authority=Depends(get_constitution_authority),
    preference_store=Depends(get_operator_preference_store),
    preference_authority=Depends(get_operator_taste_model_authority),
    project_passport_store=Depends(get_project_passport_store),
    project_passport_authority=Depends(get_project_understanding_authority),
    correction_store=Depends(get_correction_record_store),
    correction_authority=Depends(get_correction_lineage_authority),
    conversation_state: ConversationStateStore = Depends(get_conversation_state_store),
    representative_context_store=Depends(get_representative_context_store),
    emergency_stop=Depends(get_emergency_stop),
) -> StreamingResponse:
    """Stream a lean Hinglish conversational reply (the GAGOS voice mind).

    This is CONVERSATION, not the agentic forge: it reuses the cross-provider
    router (so the operator's local-first privacy gate is fully intact), recalls
    relevant memory, and injects REAL personalization facts, then calls the chat
    client ONCE for a single reply — NO ``ToolAgent`` loop, NO file-write/coding
    tools. Providers with streaming support forward real chunks; non-streaming
    clients fall back to word-by-word chunks so every route keeps one wire shape.
    Frames, in order:

      * ``turn.started`` — the turn has begun.
      * ``human_state``  — organ 30's advisory, non-authoritative guess at the
        operator's state (``HumanStateHypothesis.as_dict()``); always visible
        and user-correctable, never gates or grants anything.
      * ``route``        — the provider/model that served + a privacy indicator.
      * ``text_chunk``   — the reply, as a sequence of ``{"text": ...}`` frames.
      * ``done``         — terminal frame (``{}``), or ``error`` on transport failure.

    The user + assistant turns are persisted to L2 episodic memory, the
    human-state hypothesis is persisted to its own append-only history
    (best-effort), and the completed turn is embedded into L3
    (self-reinforcing recall), exactly like ``/api/generate``. Best-effort
    persistence never breaks the chat.
    """
    # Organ 32 / foundation law "human can stop, revoke and correct".
    #
    # This dependency was already injected here, but it was only ever handed to
    # AuthenticatedChatRepresentation -- so an ANONYMOUS turn (principal None)
    # reached a live, possibly cloud, provider with the stop engaged, and the
    # reply reached the client. Measured, not inferred: with the stop engaged
    # the provider spy was still called and its text still streamed back.
    #
    # Chat is a GREEN action, so it never issues or consumes a capability, and
    # assert_operational() is only reached from CapabilityAuthority.issue()/
    # .consume(). The gateway checks the stop too, but the anonymous path never
    # enters the gateway. Nothing on this route checked it.
    #
    # Routing anonymous chat through the gateway needs an answer to "what is an
    # anonymous caller's identity digest?", which is a real open design
    # question. Refusing to serve ANY chat turn while the operator has hit stop
    # does not -- so it is not deferred with it. EmergencyStopError is already
    # mapped to a 503 by the handler above.
    EmergencyStopHardWiringAuthority.assert_operational(
        emergency_stop, boundary="api-main"
    )

    session_id = (
        principal.session_id
        if principal is not None
        else _session_id_from_request(request, req.session_id)
    )
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
        operator_id=principal.principal_id if principal is not None else None,
    )

    authenticated_representation = (
        AuthenticatedChatRepresentation(
            principal=principal,
            constitution_authority=constitution_authority,
            preference_store=preference_store,
            preference_authority=preference_authority,
            project_passport_authority=project_passport_authority,
            project_passport_store=project_passport_store,
            correction_authority=correction_authority,
            correction_store=correction_store,
            conversation_state=conversation_state,
            representative_context_store=representative_context_store,
            emergency_stop=emergency_stop,
        )
        if principal is not None
        else None
    )

    # The application handler owns provider selection, prompt construction,
    # streaming, persistence, and terminal lifecycle.  The HTTP route only
    # supplies validated input plus injected infrastructure callbacks.
    from aios.application.turns.conversation_pipeline import stream_conversation

    task = infer_task(user_text)
    turn = TurnCoordinator(
        deps=RuntimeDeps(
            bedrock=bedrock,
            gemini=gemini,
            openai_client=openai_client,
            anthropic_client=anthropic_client,
            vertex_maas_client=vertex_maas_client,
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
                "ollama_client": client,
                "ollama_model": config.LLM_MODEL,
                "emergency_stop": emergency_stop,
                "record_episode": _record_episode,
                "interpret_human_state": human_state_interpreter.classify,
                "record_human_state": lambda sid, tid, hyp: _record_human_state(
                    sid, tid, hyp, store=human_state_store
                ),
                "authenticated_representation": authenticated_representation,
                "index_turn": _index_turn,
                "operator_facts_block": _operator_facts_block,
                "recall_memory": _recall_memory,
                # Plan Phase 4c: whose turn this is; None (unauthenticated)
                # recalls no learned row and records unattributed ones.
                "principal_id": (
                    str(principal.principal_id) if principal is not None else None
                ),
                "chat_system_prompt": CHAT_SYSTEM_PROMPT,
                "facts_auto_extract": config.FACTS_AUTO_EXTRACT,
                "facts_auto_extract_max": config.FACTS_AUTO_EXTRACT_MAX_PER_TURN,
                "cortex_bus": _main()._cortex_bus,
                "logger": _main().logger,
                "telemetry": telemetry,
                "task_signature": task_signature,
                "ollama_provider": router.PROVIDER_OLLAMA,
                "auto_ids": _AUTO_IDS,
            },
        ),
        # Every mode streams as conversation here: this route is talk only.
        # With no factory, a read-only directive ("what is ...", "explain
        # ...") classified ADVISORY found no stream and raised -- a 500 for
        # the most ordinary questions (found by tools/model_call_inventory.py).
        handlers=production_handlers(stream_conversation),
    ).coordinate(ctx)
    return StreamingResponse(
        turn.events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
