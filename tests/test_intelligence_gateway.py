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
