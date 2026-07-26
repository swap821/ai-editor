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
from aios.domain.intelligence.representative_context import (
    RepresentativeContextReceiptV1,
)


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


def test_stream_gateway_yields_the_model_calls_text() -> None:
    """Chunk BOUNDARIES are no longer preserved one-for-one: redaction now
    holds text back so a secret split across a boundary is still whole when it
    is scanned. The delivered text is what the contract is about, and it is
    unchanged."""
    result = _stream()
    assert result.context.goal == "summarize the incident"
    assert "".join(result.chunks) == ("chunk-one chunk-two goal:summarize the incident")


def test_stream_gateway_redacts_secrets_without_dropping_safe_text() -> None:
    result = _stream(
        model_call=lambda ctx: iter(
            ["safe text ", "here is the key: AKIAABCDEFGHIJKLMNOP"]
        )
    )

    out = "".join(result.chunks)

    assert out.startswith("safe text here is the key: ")
    assert "AKIAABCDEFGHIJKLMNOP" not in out
    assert "REDACTED" in out


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


def test_stream_gateway_missing_operator_identity_digest_never_starts_a_stream() -> (
    None
):
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


def _receipt_for_gateway_context(context):
    return RepresentativeContextReceiptV1.create(
        request_id=context.request_id,
        context_digest=context.context_digest,
        operator_identity_digest=context.operator_identity_digest,
        constitution_digest=context.constitution_digest,
        target=context.privacy_classification,
        active_project_revision=None,
        included_preference_ids=(),
        included_correction_ids=(),
        human_state_hypothesis_id=None,
        human_state_disposition="abstained",
        exclusions=(),
        consent_status="not_required_local",
        consent_scope=("authenticated-chat",),
        created_at="2026-07-26T00:00:00+00:00",
        expires_at="2099-07-26T00:05:00+00:00",
    )


def test_strict_streaming_receipt_persistence_failure_never_invokes_provider() -> None:
    """Authenticated chat must fail closed if its pre-call receipt is absent."""
    provider_calls: list[str] = []

    def _model_call(context):
        provider_calls.append(context.goal)
        yield "must not be reached"

    class _BrokenBundleStore:
        def save_bundle(self, context, receipt) -> None:
            raise OSError("disk full")

    with pytest.raises(IntelligenceGatewayError, match="receipt persistence"):
        _stream(
            model_call=_model_call,
            context_store=_BrokenBundleStore(),
            receipt_factory=_receipt_for_gateway_context,
            require_context_receipt=True,
        )
    assert provider_calls == []


def test_strict_streaming_receipt_is_persisted_before_the_provider_runs(
    tmp_path: Path,
) -> None:
    from aios.infrastructure.intelligence.representative_context_store import (
        RepresentativeContextStore,
    )

    store = RepresentativeContextStore(tmp_path / "strict-contexts.db")
    provider_calls: list[str] = []

    def _model_call(context):
        provider_calls.append(context.context_digest)
        yield "governed reply"

    result = _stream(
        request_id="req-strict-receipt",
        model_call=_model_call,
        context_store=store,
        receipt_factory=_receipt_for_gateway_context,
        require_context_receipt=True,
    )

    persisted = store.get_bundle("req-strict-receipt")
    assert persisted is not None
    assert persisted == (result.context, result.receipt)
    assert provider_calls == []
    assert list(result.chunks) == ["governed reply"]
    assert provider_calls == [result.context.context_digest]


# --------------------------------------------------------------------------- #
# Organ 32: streaming redaction must survive a chunk boundary.
#
# Redacting each chunk independently is not merely theoretically weak -- three
# real credential formats pass through IN FULL when split at the wrong offset,
# because neither half matches on its own. These cases are the proof, and they
# fail against per-chunk redaction.
# --------------------------------------------------------------------------- #

_SPLIT_SECRETS = {
    "openai": "sk-abcdefghij1234567890ABCDEFGHIJ1234",
    "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "github_pat": "ghp_16C7e42F292c6912E7710c838347Ae178B4a",
    "bearer": "Bearer abcdefghijklmnopqrstuvwxyz012345",
}


@pytest.mark.parametrize("secret", _SPLIT_SECRETS.values(), ids=_SPLIT_SECRETS.keys())
def test_a_secret_split_at_any_offset_never_reaches_the_client(secret: str) -> None:
    from aios.application.intelligence.gateway import _redact_stream
    from aios.runtime.secret_policy import SecretPolicy

    policy = SecretPolicy()
    text = f"here is your key {secret} -- keep it safe"
    offset = text.index(secret)

    leaked_at = [
        i
        for i in range(1, len(secret))
        if secret
        in "".join(_redact_stream([text[: offset + i], text[offset + i :]], policy))
    ]

    assert leaked_at == [], f"secret survived redaction when split at {leaked_at}"


def test_one_character_at_a_time_is_still_redacted() -> None:
    """The pathological stream: every chunk is a single character, so every
    pattern is split many times over."""
    from aios.application.intelligence.gateway import _redact_stream
    from aios.runtime.secret_policy import SecretPolicy

    secret = _SPLIT_SECRETS["openai"]
    text = f"here is your key {secret} -- keep it safe"

    out = "".join(_redact_stream(list(text), SecretPolicy()))

    assert secret not in out
    assert "REDACTED" in out
    # Non-secret text must survive intact -- redaction must not eat the reply.
    assert out.startswith("here is your key ")
    assert out.endswith(" -- keep it safe")


def test_ordinary_text_streams_through_unchanged() -> None:
    from aios.application.intelligence.gateway import _redact_stream
    from aios.runtime.secret_policy import SecretPolicy

    chunks = ["Hello, ", "this is ", "an ordinary reply ", "with no secrets."]

    assert "".join(_redact_stream(chunks, SecretPolicy())) == "".join(chunks)


def test_buffering_is_bounded_against_a_hostile_stream() -> None:
    """A stream that never resolves its straddling candidate must not grow the
    buffer without limit -- unbounded buffering would be a DoS vector."""
    from aios.application.intelligence.gateway import (
        _REDACTION_MAX_BUFFER_CHARS,
        _redact_stream,
    )
    from aios.runtime.secret_policy import SecretPolicy

    # A single unbroken high-entropy run: every cut looks like it splits a
    # candidate token, so the straddle check keeps deferring.
    hostile = ["A1b2C3d4" * 64 for _ in range(400)]
    total_in = sum(len(c) for c in hostile)

    emitted = list(_redact_stream(hostile, SecretPolicy()))

    assert emitted, "a bounded buffer must still flush"
    # Nothing is silently dropped, and no single emission exceeds the ceiling
    # by more than one incoming chunk.
    assert max(len(piece) for piece in emitted) <= (
        _REDACTION_MAX_BUFFER_CHARS + len(hostile[0])
    )
    assert total_in > _REDACTION_MAX_BUFFER_CHARS
