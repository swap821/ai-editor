"""Application-owned pipeline for ordinary conversational turns.

The HTTP route supplies validated request data and injected runtime services;
this module owns prompt assembly, provider selection, streaming, persistence,
and the terminal lifecycle frame.  Callbacks in ``RuntimeDeps.extra`` are
deliberately small infrastructure seams so the application layer does not
import the FastAPI module back into itself.
"""

from __future__ import annotations

import time
from typing import Any, Iterator

from aios.application.memory.human_representation import classify_human_state
from aios.application.turns.turn_context import TurnContext
from aios.application.turns.turn_coordinator import RuntimeDeps
from aios.core.events import CanonicalEvent, CanonicalEventType, EventPhase, TrustLevel
from aios.core.llm import LLMError
from aios.core.prompt_writer import PromptSection, PromptWriter
from aios.memory.fact_extraction import extract_candidates


def _active_route(
    runtime: RuntimeDeps, chat_client: Any, model: str
) -> tuple[str, str]:
    resolver = runtime.extra["active_route"]
    return resolver(
        chat_client,
        runtime.bedrock,
        runtime.gemini,
        model,
        openai=runtime.openai_client,
        anthropic=runtime.anthropic_client,
    )


def stream_conversation(context: TurnContext, runtime: RuntimeDeps) -> Iterator[str]:
    """Execute one conversation turn as a synchronous SSE iterator."""
    extra = runtime.extra
    user_text = str(extra.get("user_text", "")).strip()
    model_id = extra.get("model_id")
    task = str(extra["task"])
    sse = extra["sse_writer"](context.turn_id)
    telemetry = extra["telemetry"]
    started = time.perf_counter()
    selector = extra["select_chat_client"]
    chat_client, model = selector(task)
    _, model = _active_route(runtime, chat_client, model)
    yield sse("turn.started", {"mode": context.mode.value})

    def record_telemetry(outcome: str) -> None:
        provider, served_model = _active_route(runtime, chat_client, model)
        telemetry.record_run(
            session_id=context.session_id,
            task_signature=extra["task_signature"](user_text) if user_text else None,
            dispatch_path=telemetry.DISPATCH_LLM,
            provider=provider,
            model=served_model,
            verified_outcome=outcome,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    if not user_text:
        record_telemetry(telemetry.OUTCOME_ABORTED)
        yield sse("error", {"text": "No transcript provided."})
        return

    human_state = classify_human_state(user_text)
    yield sse("human_state", human_state.as_dict())
    extra["record_human_state"](context.session_id, context.turn_id, human_state)

    prompt_sections = [
        PromptSection(
            name="operator_facts",
            priority=90,
            render=lambda: extra["operator_facts_block"](
                runtime.facts,
                authority=runtime.memory_authority,
            ),
            max_tokens=800,
        ),
        PromptSection(
            name="recall",
            priority=70,
            render=lambda: extra["recall_memory"](user_text),
            max_tokens=1500,
        ),
    ]
    system_prompt = PromptWriter(
        extra["chat_system_prompt"], prompt_sections, total_budget=4000
    ).assemble(user_text)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    extra["record_episode"](context.session_id, "user", user_text)
    route_sent = False
    text_parts: list[str] = []

    def route_payload() -> dict[str, Any]:
        provider, served_model = _active_route(runtime, chat_client, model)
        return {
            "provider": provider,
            "model": served_model,
            "privacy": "local" if provider == extra["ollama_provider"] else "cloud",
            "task": task,
            "auto": model_id in extra["auto_ids"],
            "turn_id": context.turn_id,
            "mode": context.mode.value,
        }

    try:
        for chunk in extra["stream_chat_chunks"](chat_client, messages, model=model):
            if not route_sent:
                yield sse("route", route_payload())
                route_sent = True
            text_parts.append(str(chunk))
            yield sse("text_chunk", {"text": str(chunk)})
    except LLMError as exc:
        record_telemetry(telemetry.OUTCOME_ABORTED)
        yield sse("error", {"text": str(exc)})
        return

    if not route_sent:
        yield sse("route", route_payload())
    text = "".join(text_parts).strip() or "(no answer)"
    if not text_parts or not "".join(text_parts).strip():
        yield sse("text_chunk", {"text": text})

    extra["record_episode"](context.session_id, "assistant", text)
    extra["index_turn"](
        runtime.indexer,
        user_text,
        text,
        authority=runtime.memory_authority,
    )
    if extra["facts_auto_extract"]:
        try:
            proposed_count = 0
            for subject, predicate, obj in extract_candidates(
                user_text,
                max_candidates=extra["facts_auto_extract_max"],
            ):
                strengthen_or_propose = (
                    runtime.memory_authority.facts_strengthen_or_propose
                    if runtime.memory_authority is not None
                    and runtime.memory_authority.owns_store("facts", runtime.facts)
                    else runtime.facts.strengthen_or_propose
                )
                result = strengthen_or_propose(subject, predicate, obj)
                if result.proposed or result.reason == "strengthened":
                    proposed_count += 1
            cortex_bus = extra["cortex_bus"]
            if proposed_count and cortex_bus:
                canonical = CanonicalEvent(
                    event_type=CanonicalEventType.FACTS_PROPOSED.value,
                    phase=EventPhase.WONDER.value,
                    status="success",
                    trust=TrustLevel.VERIFIED.value,
                    source="chat",
                    session_id=context.session_id,
                    turn_id=context.turn_id,
                    payload={"count": proposed_count},
                )
                cortex_bus.append(canonical)
        except Exception:
            extra["logger"].warning("Chat fact extraction failed", exc_info=True)
    record_telemetry(telemetry.OUTCOME_UNVERIFIED)
    yield sse("done", {})
