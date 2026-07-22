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
    build_council_llm_client,
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
