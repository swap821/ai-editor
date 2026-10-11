"""A model the account cannot call is skipped; it never switches off its provider.

Found 2026-10-11: Bedrock discovery lists models the operator's account cannot
invoke, and the router ranked denied Claude models near the top. The failover
client counted each refusal as a Bedrock outage, so one transient failure of
the top model plus two denied candidates opened the circuit breaker and turned
off EVERY Bedrock model for the cooldown.

Pinned, both directions, with the account's real refusal texts:
* a refusal of one model marks that model unavailable and spares the breaker;
* a provider-wide failure (bad key, an organization denying API keys,
  throttling, timeout, credits) still trips the breaker;
* a marked model is skipped by failover and not offered by the router, until
  the mark expires.
"""

from __future__ import annotations

import pytest

from aios.application.models.health import ProviderHealthTracker
from aios.core import model_availability as ma
from aios.core.failover import FailoverChatClient
from aios.core.llm import LLMError

DENIED = (
    "Bedrock Converse failed for 'global.anthropic.claude-sonnet-5': An error occurred "
    "(AccessDeniedException) when calling the Converse operation: anthropic.claude-sonnet-5 "
    "is not available for this account. You can explore other available models on Amazon Bedrock."
)
INVALID = (
    "Bedrock Converse failed for 'x': An error occurred (ValidationException) when calling "
    "the Converse operation: The provided model identifier is invalid."
)
RETIRED = (
    "OpenAI-compatible endpoint returned HTTP 410 for model 'deepseek-ai/deepseek-v4-flash-0731': "
    '{"title":"Gone","detail":"The model has reached its end of life"}'
)
SCP_DENY = (
    "An error occurred (AccessDeniedException) when calling the Converse operation: User: "
    "<arn> is not authorized to perform: bedrock:CallWithBearerToken on resource: * with an "
    "explicit deny in a service control policy"
)


@pytest.fixture(autouse=True)
def _fresh():
    ma.clear()
    yield
    ma.clear()


@pytest.mark.parametrize("text", [DENIED, INVALID, RETIRED])
def test_a_refusal_of_one_model_is_model_specific(text) -> None:
    assert ma.is_model_unavailable_error(LLMError(text))


@pytest.mark.parametrize(
    "text",
    [
        SCP_DENY,
        "An error occurred (ThrottlingException): Too many requests",
        "The security token included in the request is invalid",
        "OpenAI-compatible request failed: The read operation timed out",
        "HTTP 403: Your team has either used all available credits or reached its monthly spending limit",
    ],
)
def test_provider_wide_failures_are_not(text) -> None:
    assert not ma.is_model_unavailable_error(LLMError(text))


def test_a_mark_expires() -> None:
    ma.mark_unavailable("bedrock", "m", now=1000.0)
    assert ma.is_unavailable("bedrock", "m", now=1000.0 + ma.UNAVAILABLE_TTL_S - 1)
    assert not ma.is_unavailable("bedrock", "m", now=1000.0 + ma.UNAVAILABLE_TTL_S)
    assert not ma.is_unavailable("bedrock", "other")


class _Model:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.calls = 0

    def chat(self, messages, *, tools=None, model=None):
        self.calls += 1
        if self.error:
            raise LLMError(self.error)
        return {"role": "assistant", "content": "ok"}


def test_denied_models_never_open_the_breaker() -> None:
    health = ProviderHealthTracker()
    flaky = _Model("An error occurred (ServiceUnavailableException): try again")
    denied_a, denied_b, good = _Model(DENIED), _Model(DENIED), _Model()
    client = FailoverChatClient(
        [
            (flaky, "qwen.qwen3-coder-480b", "bedrock"),
            (denied_a, "global.anthropic.claude-opus-5-5", "bedrock"),
            (denied_b, "global.anthropic.claude-sonnet-5", "bedrock"),
            (good, "deepseek.v3.2", "bedrock"),
        ],
        provider_health=health,
    )
    assert client.chat([{"role": "user", "content": "hi"}])["content"] == "ok"
    assert health.is_call_allowed("bedrock"), (
        "two denied models must not count as outages"
    )
    assert ma.is_unavailable("bedrock", "global.anthropic.claude-opus-5-5")
    assert ma.is_unavailable("bedrock", "global.anthropic.claude-sonnet-5")
    assert not ma.is_unavailable("bedrock", "qwen.qwen3-coder-480b"), (
        "a transient error is not a refusal"
    )


def test_provider_wide_failures_still_open_the_breaker() -> None:
    health = ProviderHealthTracker()
    candidates = [(_Model(SCP_DENY), f"m{i}", "bedrock") for i in range(3)]
    client = FailoverChatClient(
        candidates + [(_Model(), "qwen2.5:3b", "ollama")], provider_health=health
    )
    client.chat([{"role": "user", "content": "hi"}])
    assert not health.is_call_allowed("bedrock")
    assert ma.unavailable_models() == {}


def test_a_marked_model_is_skipped_next_turn() -> None:
    ma.mark_unavailable("bedrock", "global.anthropic.claude-sonnet-5")
    denied, good = _Model(DENIED), _Model()
    client = FailoverChatClient(
        [
            (denied, "global.anthropic.claude-sonnet-5", "bedrock"),
            (good, "deepseek.v3.2", "bedrock"),
        ]
    )
    client.chat([{"role": "user", "content": "hi"}])
    assert denied.calls == 0 and good.calls == 1


def test_the_router_does_not_offer_a_marked_model(monkeypatch) -> None:
    from aios.core import catalog, router_wiring

    monkeypatch.setattr(
        router_wiring, "catalog_models", lambda cloud, name, default: ["good", "denied"]
    )
    ma.mark_unavailable("bedrock", "denied")

    class _Ollama:
        def list_models(self):
            return {"models": ["qwen2.5:3b"]}

    providers = router_wiring._build_providers(_Ollama(), object(), None)
    offered = [m for p in providers if p.name == "bedrock" for m in p.models]
    assert offered == ["good"]
    assert catalog is not None


def test_a_mixed_failure_counts_as_the_providers() -> None:
    """An aggregate that carries one model's refusal AND a provider-wide
    failure is the provider's: never let a model mark hide an outage."""
    mixed = f"all 3 model candidate(s) failed: bedrock:a -> {DENIED}; bedrock:b -> ThrottlingException"
    assert not ma.is_model_unavailable_error(LLMError(mixed))
