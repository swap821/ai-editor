"""Organ 30 (Tier 3): classify_human_state() wired into the real, live
`/api/v1/chat` turn path -- `aios.application.turns.conversation_pipeline.
stream_conversation()`.

Exercises the actual production function (not a rewritten stand-in), with
fake collaborators standing in for the injected callables `extra` normally
carries from `aios/api/main.py::chat()`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aios.application.turns.conversation_pipeline import stream_conversation
from aios.application.turns.turn_context import TurnContext, TurnMode
from aios.application.turns.turn_coordinator import RuntimeDeps
from aios.core import telemetry
from aios.domain.memory.human_representation import HumanStateHypothesis
from aios.infrastructure.memory.human_representation_store import (
    HumanStateHypothesisStore,
)


class _FakeChatClient:
    def stream_chat(self, messages: list[dict], *, tools: Any, model: str):
        yield "hello "
        yield "world"


def _sse_writer(turn_id: str):
    def write(event: str, data: dict[str, Any]) -> str:
        return f"{event}:{data}"

    return write


def _make_context(**overrides: object) -> TurnContext:
    payload: dict[str, object] = dict(
        turn_id="turn-1",
        session_id="session-1",
        operator_id=None,
        project_id=None,
        directive="hello there, still not working, ugh",
        mode=TurnMode.CONVERSATION,
        model_id=None,
        approval_tokens=(),
    )
    payload.update(overrides)
    return TurnContext(**payload)


def _make_runtime(*, extra_overrides: dict[str, object] | None = None) -> RuntimeDeps:
    recorded_human_state: list[tuple[str, str, HumanStateHypothesis]] = []
    extra: dict[str, object] = {
        "user_text": "still not working, ugh, this is broken again",
        "model_id": None,
        "task": "chat",
        "sse_writer": _sse_writer,
        "telemetry": telemetry,
        "select_chat_client": lambda task: (_FakeChatClient(), "fake-model"),
        "active_route": lambda chat_client, bedrock, gemini, model, *, openai=None, anthropic=None: (
            "ollama",
            model,
        ),
        "stream_chat_chunks": lambda chat_client, messages, *, model: chat_client.stream_chat(
            messages, tools=None, model=model
        ),
        "record_episode": lambda session_id, role, content: None,
        "record_human_state": lambda sid, tid, hyp: recorded_human_state.append(
            (sid, tid, hyp)
        ),
        "index_turn": lambda indexer, user_text, answer, *, authority=None: None,
        "operator_facts_block": lambda facts, *, authority=None: "",
        "recall_memory": lambda user_text: "",
        "chat_system_prompt": "system prompt",
        "facts_auto_extract": False,
        "facts_auto_extract_max": 0,
        "cortex_bus": None,
        "logger": __import__("logging").getLogger("test"),
        "task_signature": lambda text: "sig",
        "ollama_provider": "ollama",
        "auto_ids": (),
    }
    if extra_overrides:
        extra.update(extra_overrides)
    runtime = RuntimeDeps(extra=extra)
    runtime.extra["_recorded_human_state"] = recorded_human_state
    return runtime


def test_stream_conversation_emits_a_human_state_frame_before_route() -> None:
    context = _make_context()
    runtime = _make_runtime()

    events = [
        e.split(":", 1)[0] for e in stream_conversation(context, runtime)
    ]

    assert "human_state" in events
    assert events.index("human_state") < events.index("route")
    assert events.index("turn.started") < events.index("human_state")


def test_stream_conversation_human_state_reflects_the_real_classifier() -> None:
    context = _make_context()
    runtime = _make_runtime(
        extra_overrides={"user_text": "UGH this is still broken again?!"}
    )

    frames = list(stream_conversation(context, runtime))
    human_state_frame = next(f for f in frames if f.startswith("human_state:"))

    assert "'state': 'frustrated'" in human_state_frame
    assert "'grants_authority': False" in human_state_frame
    assert "'user_correctable': True" in human_state_frame


def test_stream_conversation_persists_the_hypothesis_best_effort(
    tmp_path: Path,
) -> None:
    store = HumanStateHypothesisStore(tmp_path / "human_state.db")
    context = _make_context(turn_id="turn-42", session_id="session-42")
    runtime = _make_runtime(
        extra_overrides={
            "user_text": "just do it, go ahead",
            "record_human_state": lambda sid, tid, hyp: store.save(sid, tid, hyp),
        }
    )

    list(stream_conversation(context, runtime))

    history = store.get_history("session-42")
    assert len(history) == 1
    turn_id, hypothesis = history[0]
    assert turn_id == "turn-42"
    assert hypothesis.state == "decisive"


def test_stream_conversation_yields_human_state_before_calling_record_human_state() -> (
    None
):
    """The classify+emit step happens before the persistence call, so the
    SSE frame reaches the wire even if a caller injects a non-best-effort
    record_human_state -- the real best-effort safety net lives inside
    the production _record_human_state() itself (see
    test_record_human_state_is_best_effort_and_never_raises in
    tests/test_api_main_gaps.py), not at this call site, matching
    record_episode's own established call-site convention exactly."""
    context = _make_context()
    call_order: list[str] = []

    def _tracking_record_human_state(sid: str, tid: str, hyp: HumanStateHypothesis) -> None:
        call_order.append("record_human_state")

    runtime = _make_runtime(
        extra_overrides={"record_human_state": _tracking_record_human_state}
    )

    frames = []
    for frame in stream_conversation(context, runtime):
        if frame.startswith("human_state:") and "record_human_state" not in call_order:
            frames.append("human_state_before_persist")
        frames.append(frame)

    assert "human_state_before_persist" in frames
    assert call_order == ["record_human_state"]
