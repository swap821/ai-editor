"""Unit tests for the P0.1 engine-preflight tool's pure logic.

The actual chat() round-trip against a live provider is exercised by running
tools/preflight.py directly (see AGENTS.md / GAGOS_SEASON_ONE_KICKOFF.md P0.1),
not in this suite -- these tests cover provider selection, config-gating, and
result formatting with fake clients only.
"""
from __future__ import annotations

import pytest

from aios.core.llm import LLMError
from tools.preflight import (
    PROVIDER_BEDROCK,
    PROVIDER_OLLAMA,
    PreflightConfigError,
    PreflightResult,
    build_client,
    format_result,
    run_roundtrip,
    select_provider,
)


def test_select_provider_defaults_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIOS_PREFLIGHT_PROVIDER", raising=False)
    assert select_provider() == PROVIDER_OLLAMA


def test_select_provider_honors_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_PREFLIGHT_PROVIDER", "bedrock")
    assert select_provider() == PROVIDER_BEDROCK


def test_build_client_rejects_unconfigured_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aios.config.BEDROCK_ENABLED", False)
    with pytest.raises(PreflightConfigError, match="Bedrock"):
        build_client(PROVIDER_BEDROCK)


def test_build_client_rejects_unknown_provider() -> None:
    with pytest.raises(PreflightConfigError, match="Unknown provider"):
        build_client("carrier-pigeon")


def test_build_client_constructs_ollama_by_default() -> None:
    client, model = build_client(PROVIDER_OLLAMA)
    assert model
    assert hasattr(client, "chat")


class _FakeOkClient:
    def chat(self, messages: list[dict], **kwargs: object) -> dict:
        return {"role": "assistant", "content": "OK"}


class _FakeFailingClient:
    def chat(self, messages: list[dict], **kwargs: object) -> dict:
        raise LLMError("connection refused")


def test_run_roundtrip_reports_success() -> None:
    result = run_roundtrip(_FakeOkClient(), "ollama", "llama3.1:8b")
    assert result.ok is True
    assert result.detail == "OK"
    assert result.latency_ms is not None
    assert result.latency_ms >= 0


def test_run_roundtrip_reports_llm_error_as_failure_not_exception() -> None:
    result = run_roundtrip(_FakeFailingClient(), "ollama", "llama3.1:8b")
    assert result.ok is False
    assert "connection refused" in result.detail
    assert result.latency_ms is None


def test_format_result_ok() -> None:
    r = PreflightResult(ok=True, provider="ollama", model="llama3.1:8b", latency_ms=123.4, detail="OK")
    line = format_result(r)
    assert "OK" in line
    assert "ollama" in line
    assert "123" in line


def test_format_result_fail() -> None:
    r = PreflightResult(ok=False, provider="ollama", model="llama3.1:8b", latency_ms=None, detail="boom")
    line = format_result(r)
    assert "FAIL" in line
    assert "boom" in line
