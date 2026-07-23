"""Reconciliation pass, item 2: Council Planner/King LLM reasoning routed
through the Universal Intelligence Gateway.

Council's LLM slots were previously wired but never supplied a client in
production -- `build_council_llm_client` is the first thing that actually
does. Every completion must be emergency-stop gated and go through
`route_intelligence_request`, never a bare provider call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios import config
from aios.application.governance import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.domain.governance import EmergencyStopRequest
from aios.council.gateway_reasoning import (
    GatewayRoutedCouncilLLMClient,
    _ChatBackedCompleter,
    build_council_llm_client,
    build_dissent_llm_client,
)
from aios.infrastructure.identity.sqlite_store import IdentityStore, credential_digest


def _engaged_controller(tmp_path: Path) -> EmergencyStopController:
    controller = EmergencyStopController(
        tmp_path / "emergency.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda: None,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda reason: None,
        ),
    )
    controller.engage(
        EmergencyStopRequest(
            operator_id="operator-1",
            authentication_event_id="auth-event-1",
            reason="operator requested an immediate halt",
        )
    )
    return controller


class _FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, bool]] = []

    def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        self.calls.append((prompt, system, json_mode))
        return '{"risk_level": "YELLOW"}'


def _seed_operator(identity_path: Path, *, operator_id: str = "op-council") -> None:
    IdentityStore(identity_path).create_operator(
        operator_id=operator_id,
        display_name="Council Operator",
        credential_digest_value=credential_digest("password"),
        recovery_digest_value=credential_digest("recovery"),
    )


# --------------------------------------------------------------------------- #
# build_council_llm_client -- fail-closed factory
# --------------------------------------------------------------------------- #


def test_build_council_llm_client_returns_none_when_reasoning_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", False)
    monkeypatch.setattr(config, "IDENTITY_DB_PATH", tmp_path / "identity.db")
    _seed_operator(tmp_path / "identity.db")

    assert build_council_llm_client() is None


def test_build_council_llm_client_returns_none_with_no_enrolled_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    monkeypatch.setattr(config, "IDENTITY_DB_PATH", tmp_path / "identity.db")

    assert build_council_llm_client() is None


def test_build_council_llm_client_returns_real_client_when_operator_enrolled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    monkeypatch.setattr(config, "IDENTITY_DB_PATH", tmp_path / "identity.db")
    _seed_operator(tmp_path / "identity.db")

    client = build_council_llm_client()

    assert isinstance(client, GatewayRoutedCouncilLLMClient)


# --------------------------------------------------------------------------- #
# GatewayRoutedCouncilLLMClient.complete -- routes through the real gateway
# --------------------------------------------------------------------------- #


def test_complete_routes_through_the_gateway_not_the_provider_directly(
    tmp_path: Path,
) -> None:
    provider = _FakeProvider()
    client = GatewayRoutedCouncilLLMClient(
        operator_identity_digest=credential_digest("op-council"),
        constitution_digest="c" * 64,
        provider=provider,
    )

    output = client.complete("Mission goal:\nbuild a thing", system="be terse")

    assert output == '{"risk_level": "YELLOW"}'
    assert provider.calls == [("Mission goal:\nbuild a thing", "be terse", False)]


def test_complete_is_blocked_while_emergency_stop_is_engaged(tmp_path: Path) -> None:
    provider = _FakeProvider()
    client = GatewayRoutedCouncilLLMClient(
        operator_identity_digest=credential_digest("op-council"),
        constitution_digest="c" * 64,
        emergency_stop=_engaged_controller(tmp_path),
        provider=provider,
    )

    with pytest.raises(EmergencyStopError):
        client.complete("Mission goal:\nbuild a thing")

    assert provider.calls == []


def test_king_compatible_call_shape_single_positional_argument(tmp_path: Path) -> None:
    """King's reason_king calls `complete(prompt)` with no keyword arguments --
    confirm the bound method satisfies that exact call shape."""
    provider = _FakeProvider()
    client = GatewayRoutedCouncilLLMClient(
        operator_identity_digest=credential_digest("op-council"),
        constitution_digest="c" * 64,
        provider=provider,
    )
    king_complete = client.complete

    output = king_complete("King prompt only")

    assert output == '{"risk_level": "YELLOW"}'
    assert provider.calls == [("King prompt only", None, False)]


# --------------------------------------------------------------------------- #
# build_dissent_llm_client -- organ 39's real independent second reviewer
# --------------------------------------------------------------------------- #


class _FakeChatClient:
    """Stands in for a real cloud client's chat() -- never Ollama, so a
    real dissent client must never wrap one of these with provider='ollama'."""

    model = "gemini-2.5-flash"

    def __init__(self, content: str = '{"answer": "reject", "confidence": 0.7}') -> None:
        self._content = content
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict]) -> dict:
        self.calls.append(messages)
        return {"role": "assistant", "content": self._content}


def test_build_dissent_llm_client_returns_none_when_reasoning_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", False)
    monkeypatch.setattr(config, "IDENTITY_DB_PATH", tmp_path / "identity.db")
    _seed_operator(tmp_path / "identity.db")

    assert build_dissent_llm_client() is None


def test_build_dissent_llm_client_returns_none_with_no_enrolled_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    monkeypatch.setattr(config, "IDENTITY_DB_PATH", tmp_path / "identity.db")

    assert build_dissent_llm_client() is None


def test_build_dissent_llm_client_returns_none_when_no_cloud_provider_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    monkeypatch.setattr(config, "IDENTITY_DB_PATH", tmp_path / "identity.db")
    _seed_operator(tmp_path / "identity.db")
    from aios.api import deps

    monkeypatch.setattr(deps, "get_gemini_client", lambda: None)
    monkeypatch.setattr(deps, "get_bedrock_client", lambda: None)
    monkeypatch.setattr(deps, "get_openai_client", lambda: None)
    monkeypatch.setattr(deps, "get_anthropic_client", lambda: None)

    assert build_dissent_llm_client() is None


def test_build_dissent_llm_client_returns_real_gemini_backed_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    monkeypatch.setattr(config, "IDENTITY_DB_PATH", tmp_path / "identity.db")
    _seed_operator(tmp_path / "identity.db")
    from aios.api import deps

    fake_gemini = _FakeChatClient()
    monkeypatch.setattr(deps, "get_gemini_client", lambda: fake_gemini)
    monkeypatch.setattr(deps, "get_bedrock_client", lambda: None)
    monkeypatch.setattr(deps, "get_openai_client", lambda: None)
    monkeypatch.setattr(deps, "get_anthropic_client", lambda: None)

    result = build_dissent_llm_client()

    assert result is not None
    client, provider_name, model_id = result
    assert isinstance(client, GatewayRoutedCouncilLLMClient)
    assert provider_name == "gemini"
    assert model_id == "gemini-2.5-flash"
    output = client.complete("Independently assess this mission")
    assert output == '{"answer": "reject", "confidence": 0.7}'
    assert fake_gemini.calls  # the real chat() was actually invoked


def test_build_dissent_llm_client_falls_back_to_bedrock_when_gemini_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    monkeypatch.setattr(config, "IDENTITY_DB_PATH", tmp_path / "identity.db")
    _seed_operator(tmp_path / "identity.db")
    from aios.api import deps

    fake_bedrock = _FakeChatClient()
    fake_bedrock.model = "anthropic.claude-sonnet"
    monkeypatch.setattr(deps, "get_gemini_client", lambda: None)
    monkeypatch.setattr(deps, "get_bedrock_client", lambda: fake_bedrock)
    monkeypatch.setattr(deps, "get_openai_client", lambda: None)
    monkeypatch.setattr(deps, "get_anthropic_client", lambda: None)

    result = build_dissent_llm_client()

    assert result is not None
    _client, provider_name, model_id = result
    assert provider_name == "bedrock"
    assert model_id == "anthropic.claude-sonnet"


def test_chat_backed_completer_wraps_chat_into_a_completion_string() -> None:
    fake = _FakeChatClient(content="a real assistant reply")
    completer = _ChatBackedCompleter(fake)

    output = completer.complete("hello", system="be terse")

    assert output == "a real assistant reply"
    assert fake.calls == [
        [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hello"}]
    ]


def test_chat_backed_completer_returns_empty_string_for_tool_only_reply() -> None:
    fake = _FakeChatClient()
    fake.chat = lambda messages: {"role": "assistant", "content": None, "tool_calls": []}
    completer = _ChatBackedCompleter(fake)

    assert completer.complete("hello") == ""
