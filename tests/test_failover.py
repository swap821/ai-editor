"""Unit tests for the failover chat client (aios.core.failover).

The resilience layer of the multi-LLM library: a ranked list of (client, model,
provider) candidates tried in order, riding the next on an LLMError so one model's
outage never blocks the turn. Fakes only — no network.
"""
from __future__ import annotations

import pytest

from aios.core.failover import FailoverChatClient
from aios.core.llm import LLMError


class OK:
    """A client that succeeds and echoes the model it was handed."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def chat(self, messages, *, tools=None, model=None):
        self.calls += 1
        return {"role": "assistant", "content": self.reply, "_model": model}


class Boom:
    """A client whose chat always raises LLMError (provider outage/throttle)."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, *, tools=None, model=None):
        self.calls += 1
        raise LLMError("provider down")


MSG = [{"role": "user", "content": "hi"}]


def test_returns_first_candidate_on_success() -> None:
    c = OK("hello")
    fc = FailoverChatClient([(c, "m1", "ollama")])
    out = fc.chat(MSG)
    assert out["content"] == "hello"
    assert fc.active_provider == "ollama" and fc.active_model == "m1"
    assert c.calls == 1


def test_uses_the_candidate_model_not_the_passed_model() -> None:
    c = OK("x")
    fc = FailoverChatClient([(c, "candidate-model", "gemini")])
    out = fc.chat(MSG, model="ignored")
    assert out["_model"] == "candidate-model"  # the failover client supplies its own


def test_falls_over_to_next_on_llmerror() -> None:
    bad, good = Boom(), OK("served-by-fallback")
    fc = FailoverChatClient([(bad, "m1", "gemini"), (good, "m2", "bedrock")])
    out = fc.chat(MSG)
    assert out["content"] == "served-by-fallback"
    assert fc.active_provider == "bedrock" and fc.active_model == "m2"  # truthful attribution
    assert bad.calls == 1 and good.calls == 1


def test_same_cloud_provider_can_try_ranked_model_fallback_before_local() -> None:
    bad, good, local = Boom(), OK("served-by-same-provider"), OK("local")
    fc = FailoverChatClient(
        [(bad, "claude", "bedrock"), (good, "nova", "bedrock"), (local, "qwen", "ollama")]
    )
    out = fc.chat(MSG)
    assert out["content"] == "served-by-same-provider"
    assert fc.active_provider == "bedrock" and fc.active_model == "nova"
    assert bad.calls == 1 and good.calls == 1 and local.calls == 0


def test_different_cloud_provider_is_skipped_when_local_fallback_exists() -> None:
    bad, other_cloud, local = Boom(), OK("other-cloud"), OK("local")
    fc = FailoverChatClient(
        [(bad, "gemini-pro", "gemini"), (other_cloud, "sonnet", "bedrock"), (local, "qwen", "ollama")]
    )
    out = fc.chat(MSG)
    assert out["content"] == "local"
    assert fc.active_provider == "ollama" and fc.active_model == "qwen"
    assert bad.calls == 1 and other_cloud.calls == 0 and local.calls == 1


def test_all_candidates_failing_raises_llmerror() -> None:
    fc = FailoverChatClient([(Boom(), "a", "gemini"), (Boom(), "b", "bedrock")])
    with pytest.raises(LLMError):
        fc.chat(MSG)


def test_sticky_forward_does_not_retry_a_failed_candidate() -> None:
    bad, good = Boom(), OK("ok")
    fc = FailoverChatClient([(bad, "m1", "gemini"), (good, "m2", "bedrock")])
    fc.chat(MSG)  # fails over gemini -> bedrock
    fc.chat(MSG)  # next call must start from bedrock, NOT retry gemini
    assert bad.calls == 1  # tried exactly once across the whole turn
    assert good.calls == 2
    assert fc.active_model == "m2"


def test_non_llmerror_propagates_and_does_not_failover() -> None:
    # A real bug (not a provider outage) must surface, not be masked by failover.
    class Crash:
        def chat(self, messages, *, tools=None, model=None):
            raise ValueError("bug in mapping")

    after = OK("should-not-be-reached")
    fc = FailoverChatClient([(Crash(), "m1", "ollama"), (after, "m2", "gemini")])
    with pytest.raises(ValueError):
        fc.chat(MSG)
    assert after.calls == 0


def test_empty_candidate_list_is_rejected() -> None:
    with pytest.raises(ValueError):
        FailoverChatClient([])


def test_on_failover_hook_is_called_with_from_and_to() -> None:
    events = []
    fc = FailoverChatClient(
        [(Boom(), "m1", "gemini"), (OK("x"), "m2", "bedrock")],
        on_failover=lambda fp, fm, np, nm, e: events.append((fp, fm, np, nm)),
    )
    fc.chat(MSG)
    assert events == [("gemini", "m1", "bedrock", "m2")]
