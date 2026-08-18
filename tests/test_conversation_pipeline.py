"""Organ 30 (Tier 3): classify_human_state() wired into the real, live
`/api/v1/chat` turn path -- `aios.application.turns.conversation_pipeline.
stream_conversation()`.

Exercises the actual production function (not a rewritten stand-in), with
fake collaborators standing in for the injected callables `extra` normally
carries from `aios/api/main.py::chat()`.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
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
        "active_route": lambda chat_client, bedrock, gemini, model, *, openai=None, anthropic=None, vertex_maas=None: (
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

def test_stream_conversation_authenticated_representation_uses_gateway_before_route() -> (
    None
):
    """An authenticated turn must not fall back to the legacy raw-facts prompt.

    The actual authenticated gateway is wired by the HTTP route. This test
    keeps the application boundary honest: it proves the production turn
    pipeline invokes that gateway, exposes only receipt references before the
    provider route, and leaves raw fact/recall assembly unreachable.
    """

    context = _make_context(operator_id="operator-1", session_id="session-auth")
    calls: list[dict[str, object]] = []

    class _AuthenticatedRepresentation:
        def stream(self, **kwargs: object) -> object:
            calls.append(kwargs)
            return SimpleNamespace(
                context=SimpleNamespace(context_digest="a" * 64),
                receipt=SimpleNamespace(
                    receipt_digest="b" * 64,
                    expires_at="2026-07-26T00:05:00+00:00",
                ),
                chunks=iter(("governed ", "reply")),
            )

    def _legacy_prompt_path(*args: object, **kwargs: object) -> str:
        raise AssertionError("authenticated chat must not use legacy prompt assembly")

    runtime = _make_runtime(
        extra_overrides={
            "authenticated_representation": _AuthenticatedRepresentation(),
            "record_human_state": lambda sid, tid, hyp: 73,
            "operator_facts_block": _legacy_prompt_path,
            "recall_memory": _legacy_prompt_path,
            "stream_chat_chunks": _legacy_prompt_path,
        }
    )

    frames = list(stream_conversation(context, runtime))
    events = [frame.split(":", 1)[0] for frame in frames]

    assert len(calls) == 1
    assert calls[0]["context"] == context
    assert calls[0]["human_state_hypothesis_id"] == 73
    assert calls[0]["provider"] == "ollama"
    assert events.index("human_state") < events.index("representative_context")
    assert events.index("representative_context") < events.index("route")
    receipt_frame = next(
        frame for frame in frames if frame.startswith("representative_context:")
    )
    assert "a" * 64 in receipt_frame
    assert "b" * 64 in receipt_frame
    text = "".join(
        frame.split("'text': ", 1)[1].rstrip("}") .strip("'")
        for frame in frames
        if frame.startswith("text_chunk:")
    )
    assert text == "governed reply"

def test_stream_conversation_anonymous_compatibility_uses_local_gateway_path() -> None:
    context = _make_context(session_id="session-compat")
    calls: list[str] = []

    class _Client:
        def __init__(self, label: str) -> None:
            self.label = label

        def stream_chat(self, messages, *, tools, model):
            calls.append(self.label)
            yield f"{self.label} reply"

    local_client = _Client("local")
    cloud_client = _Client("cloud")

    def _active_route(chat_client, bedrock, gemini, model, *, openai=None, anthropic=None, vertex_maas=None):
        return ("cloud", "cloud-model") if chat_client is cloud_client else ("ollama", "local-model")

    def _stream_chat_chunks(chat_client, messages, *, model):
        yield from chat_client.stream_chat(messages, tools=None, model=model)

    runtime = _make_runtime(
        extra_overrides={
            "select_chat_client": lambda task: (cloud_client, "cloud-model"),
            "active_route": _active_route,
            "stream_chat_chunks": _stream_chat_chunks,
            "ollama_client": local_client,
            "ollama_model": "local-model",
        }
    )

    frames = list(stream_conversation(context, runtime))
    route_frame = next(frame for frame in frames if frame.startswith("route:"))
    text = "".join(
        frame.split("'text': ", 1)[1].rstrip("}").strip("'")
        for frame in frames
        if frame.startswith("text_chunk:")
    )

    assert calls == ["local"]
    assert "'provider': 'ollama'" in route_frame
    assert "'model': 'local-model'" in route_frame
    assert "'privacy': 'local'" in route_frame
    assert text == "local reply"
