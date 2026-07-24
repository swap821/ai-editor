"""Slice 30: Universal Intelligence Gateway pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.application.governance import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.application.intelligence.gateway import (
    IntelligenceGatewayError,
    route_intelligence_request,
    stream_intelligence_request,
)
from aios.domain.governance import EmergencyStopRequest


def _controller(tmp_path: Path) -> EmergencyStopController:
    return EmergencyStopController(
        tmp_path / "emergency.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda: None,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda reason: None,
        ),
    )


def _route(**overrides: object):
    fields: dict[str, object] = dict(
        request_id="req-1",
        operator_identity_digest="operator-digest",
        constitution_digest="c" * 64,
        goal="summarize the incident",
        desired_outcome="a short, accurate summary",
        target="local",
        delegated_authority_summary="advisory only, no write authority",
        model_call=lambda ctx: f"summary of: {ctx.goal}",
    )
    fields.update(overrides)
    return route_intelligence_request(**fields)


def test_gateway_compiles_context_and_returns_model_output() -> None:
    result = _route()
    assert result.output == "summary of: summarize the incident"
    assert result.context.goal == "summarize the incident"
    assert result.secrets_redacted is False


def test_provider_response_secrets_are_redacted() -> None:
    result = _route(model_call=lambda ctx: "here is the key: AKIAABCDEFGHIJKLMNOP")
    assert "AKIAABCDEFGHIJKLMNOP" not in result.output
    assert "REDACTED" in result.output
    assert result.secrets_redacted is True


def test_missing_operator_identity_digest_is_refused_before_any_model_call() -> None:
    calls: list[str] = []

    def _model_call(ctx):
        calls.append(ctx.goal)
        return "should never run"

    with pytest.raises(IntelligenceGatewayError, match="operator_identity_digest"):
        _route(operator_identity_digest="", model_call=_model_call)
    assert calls == []


def test_missing_constitution_digest_is_refused_before_any_model_call() -> None:
    calls: list[str] = []

    def _model_call(ctx):
        calls.append(ctx.goal)
        return "should never run"

    with pytest.raises(IntelligenceGatewayError, match="constitution_digest"):
        _route(constitution_digest="", model_call=_model_call)
    assert calls == []


@pytest.mark.parametrize("target", ["local", "cloud"])
def test_emergency_stop_blocks_both_local_and_cloud_calls(
    tmp_path: Path, target: str
) -> None:
    stopped = _controller(tmp_path)
    stopped.engage(
        EmergencyStopRequest(
            operator_id="operator-1",
            authentication_event_id="auth-1",
            reason="test",
        )
    )
    calls: list[str] = []

    def _model_call(ctx):
        calls.append(ctx.goal)
        return "should never run"

    with pytest.raises(EmergencyStopError):
        _route(target=target, model_call=_model_call, emergency_stop=stopped)
    assert calls == []


def test_local_target_does_not_claim_cloud_eligibility() -> None:
    result = _route(target="local")
    assert result.context.privacy_classification == "local"
    assert result.context.cloud_allowed_fields == ()


def _stream(**overrides: object):
    fields: dict[str, object] = dict(
        request_id="req-stream-1",
        operator_identity_digest="operator-digest",
        constitution_digest="c" * 64,
        goal="summarize the incident",
        desired_outcome="a short, accurate summary",
        target="local",
        delegated_authority_summary="advisory only, no write authority",
        model_call=lambda ctx: iter(["chunk-one ", "chunk-two ", f"goal:{ctx.goal}"]),
    )
    fields.update(overrides)
    return stream_intelligence_request(**fields)


def test_stream_gateway_yields_chunks_from_the_model_call() -> None:
    result = _stream()
    assert result.context.goal == "summarize the incident"
    assert list(result.chunks) == [
        "chunk-one ",
        "chunk-two ",
        "goal:summarize the incident",
    ]


def test_stream_gateway_redacts_each_chunk_independently() -> None:
    result = _stream(
        model_call=lambda ctx: iter(["safe text ", "here is the key: AKIAABCDEFGHIJKLMNOP"])
    )
    chunks = list(result.chunks)
    assert chunks[0] == "safe text "
    assert "AKIAABCDEFGHIJKLMNOP" not in chunks[1]
    assert "REDACTED" in chunks[1]


def test_stream_gateway_context_is_available_before_any_chunk_is_produced() -> None:
    """The whole point of returning context eagerly: a caller can emit a
    route/metadata frame before consuming the first chunk, exactly matching
    the existing chat SSE wire shape (route frame, then text_chunk frames)."""
    produced: list[str] = []

    def _model_call(ctx):
        def _gen():
            produced.append("chunk-1")
            yield "chunk-1"

        return _gen()

    result = _stream(model_call=_model_call)
    assert result.context.goal == "summarize the incident"
    assert produced == []  # nothing pulled yet -- the generator is lazy
    list(result.chunks)
    assert produced == ["chunk-1"]


def test_stream_gateway_missing_operator_identity_digest_never_starts_a_stream() -> None:
    calls: list[str] = []

    def _model_call(ctx):
        calls.append(ctx.goal)
        yield "should never run"

    with pytest.raises(IntelligenceGatewayError, match="operator_identity_digest"):
        _stream(operator_identity_digest="", model_call=_model_call)
    assert calls == []


def test_stream_gateway_missing_constitution_digest_never_starts_a_stream() -> None:
    calls: list[str] = []

    def _model_call(ctx):
        calls.append(ctx.goal)
        yield "should never run"

    with pytest.raises(IntelligenceGatewayError, match="constitution_digest"):
        _stream(constitution_digest="", model_call=_model_call)
    assert calls == []


@pytest.mark.parametrize("target", ["local", "cloud"])
def test_stream_gateway_emergency_stop_blocks_before_any_chunk(
    tmp_path: Path, target: str
) -> None:
    stopped = _controller(tmp_path)
    stopped.engage(
        EmergencyStopRequest(
            operator_id="operator-1",
            authentication_event_id="auth-1",
            reason="test",
        )
    )
    calls: list[str] = []

    def _model_call(ctx):
        calls.append(ctx.goal)
        yield "should never run"

    with pytest.raises(EmergencyStopError):
        _stream(target=target, model_call=_model_call, emergency_stop=stopped)
    assert calls == []


def test_gateway_denial_never_invokes_the_model_call_callback() -> None:
    """A refused request must not fall through to calling the model anyway --
    there is no other, unapproved path this function could take."""
    calls: list[str] = []

    def _model_call(ctx):
        calls.append(ctx.goal)
        return "unexpected"

    with pytest.raises(IntelligenceGatewayError):
        _route(operator_identity_digest="", model_call=_model_call)
    with pytest.raises(IntelligenceGatewayError):
        _route(constitution_digest="", model_call=_model_call)
    assert calls == []


def test_gateway_durably_records_the_compiled_context(tmp_path: Path) -> None:
    """Organ 31: every context that passes governance is durably recorded,
    not just returned in-memory and discarded."""
    from aios.infrastructure.intelligence.representative_context_store import (
        RepresentativeContextStore,
    )

    store = RepresentativeContextStore(tmp_path / "contexts.db")
    result = _route(request_id="req-recorded", context_store=store)

    recorded = store.get("req-recorded")
    assert recorded is not None
    assert recorded == result.context


def test_gateway_denial_records_no_context() -> None:
    """A refused request has no context to record -- the store must never
    see a request that never passed identity/constitution validation."""
    recorder_calls: list[object] = []

    class _SpyStore:
        def save(self, context: object) -> None:
            recorder_calls.append(context)

    with pytest.raises(IntelligenceGatewayError):
        _route(operator_identity_digest="", context_store=_SpyStore())
    assert recorder_calls == []


def test_gateway_context_recording_failure_never_breaks_a_governed_call() -> None:
    """A store failure is best-effort -- it must never surface to the caller
    or block a call that already passed every governance check."""

    class _BrokenStore:
        def save(self, context: object) -> None:
            raise RuntimeError("disk full")

    result = _route(context_store=_BrokenStore())
    assert result.output == "summary of: summarize the incident"


def test_stream_gateway_durably_records_the_compiled_context(tmp_path: Path) -> None:
    from aios.infrastructure.intelligence.representative_context_store import (
        RepresentativeContextStore,
    )

    store = RepresentativeContextStore(tmp_path / "contexts.db")
    result = _stream(request_id="req-stream-recorded", context_store=store)
    list(result.chunks)

    recorded = store.get("req-stream-recorded")
    assert recorded is not None
    assert recorded == result.context
