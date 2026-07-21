"""P0.1 -- engine preflight: verify exactly one configured LLM provider works
end-to-end (config present -> client constructs -> one real chat() round-trip
-> prints provider, model, latency). Ollama (free, local, sovereign) is the
default engine; set AIOS_PREFLIGHT_PROVIDER to check a specific cloud provider
instead. Exits non-zero with a plain-language fix hint on any failure.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aios import config
from aios.core.llm import LLMError, OllamaClient

PROVIDER_OLLAMA = "ollama"
PROVIDER_BEDROCK = "bedrock"
PROVIDER_GEMINI = "gemini"
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"

_ROUND_TRIP_PROMPT = "reply with OK"


class PreflightConfigError(RuntimeError):
    """Selected provider isn't configured; message is a plain-language fix hint."""


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    provider: str
    model: str
    latency_ms: Optional[float]
    detail: str


def select_provider() -> str:
    """Which provider to check: AIOS_PREFLIGHT_PROVIDER override, else Ollama."""
    override = os.getenv("AIOS_PREFLIGHT_PROVIDER", "").strip().lower()
    return override or PROVIDER_OLLAMA


def build_client(provider: str):
    """Construct the chat client for *provider*, or raise PreflightConfigError."""
    if provider == PROVIDER_OLLAMA:
        return OllamaClient(), config.LLM_MODEL
    if provider == PROVIDER_BEDROCK:
        if not config.BEDROCK_ENABLED:
            raise PreflightConfigError(
                "Bedrock selected but not configured. Set AIOS_BEDROCK_REGION and "
                "AIOS_BEDROCK_MODEL (plus AWS credentials) in .env, or unset "
                "AIOS_PREFLIGHT_PROVIDER to check Ollama instead."
            )
        from aios.core.bedrock import BedrockClient

        return BedrockClient(), config.BEDROCK_MODEL
    if provider == PROVIDER_GEMINI:
        if not config.GEMINI_ENABLED:
            raise PreflightConfigError(
                "Gemini selected but not configured. Set AIOS_GEMINI_PROJECT and "
                "AIOS_GEMINI_LOCATION in .env, or unset AIOS_PREFLIGHT_PROVIDER."
            )
        from aios.core.gemini import GeminiClient

        return GeminiClient(), config.GEMINI_MODEL
    if provider == PROVIDER_OPENAI:
        if not config.OPENAI_ENABLED:
            raise PreflightConfigError(
                "OpenAI-compatible provider selected but not configured. Set "
                "AIOS_OPENAI_API_KEY in .env, or unset AIOS_PREFLIGHT_PROVIDER."
            )
        from aios.core.openai_compat import OpenAICompatClient

        return OpenAICompatClient(), config.OPENAI_MODEL
    if provider == PROVIDER_ANTHROPIC:
        if not config.ANTHROPIC_ENABLED:
            raise PreflightConfigError(
                "Anthropic direct selected but not configured. Set "
                "AIOS_ANTHROPIC_API_KEY in .env, or unset AIOS_PREFLIGHT_PROVIDER."
            )
        from aios.core.anthropic_direct import AnthropicDirectClient

        return AnthropicDirectClient(), config.ANTHROPIC_MODEL
    raise PreflightConfigError(
        f"Unknown provider '{provider}'. Valid: ollama, bedrock, gemini, openai, anthropic."
    )


def run_roundtrip(client, provider: str, model: str) -> PreflightResult:
    """One real chat() call, timed. Never raises -- failures become a result."""
    started = time.monotonic()
    try:
        message = client.chat([{"role": "user", "content": _ROUND_TRIP_PROMPT}])
    except LLMError as exc:
        return PreflightResult(
            ok=False, provider=provider, model=model, latency_ms=None,
            detail=f"{provider} chat() round-trip failed: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 - surface anything unexpected as a clear failure
        return PreflightResult(
            ok=False, provider=provider, model=model, latency_ms=None,
            detail=f"unexpected error calling {provider}.chat(): {exc}",
        )
    latency_ms = (time.monotonic() - started) * 1000
    content = message.get("content", "") if isinstance(message, dict) else str(message)
    return PreflightResult(
        ok=True, provider=provider, model=model, latency_ms=latency_ms,
        detail=str(content).strip(),
    )


def format_result(result: PreflightResult) -> str:
    if not result.ok:
        return f"[preflight] FAIL provider={result.provider} model={result.model}: {result.detail}"
    return (
        f"[preflight] OK provider={result.provider} model={result.model} "
        f"latency_ms={result.latency_ms:.0f} reply={result.detail!r}"
    )


def main() -> int:
    provider = select_provider()
    try:
        client, model = build_client(provider)
    except PreflightConfigError as exc:
        print(f"[preflight] FAIL: {exc}")
        return 1

    result = run_roundtrip(client, provider, model)
    print(format_result(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
