"""Cloud spend, measured and bounded across every metered call (2026-11-10).

Codex's design conditions (2026-11-02): record actual usage, and respect the
operator's ceiling at the gateway, not only in GAGOS's workshop. Pinned here,
with fake providers and no network:

* which brains are metered derives from the one registry; a provider the
  registry does not name as free is metered;
* each metered adapter records the tokens its provider reports, for a call and
  for a stream; a stream that reports none is recorded from its characters,
  marked estimated;
* once this month's recorded spend reaches the ceiling, ``model_calls.observe``
  refuses every metered call before it leaves, whatever its entrance; the
  refusal is recorded, and it is an ``LLMError`` so failover moves on; a free
  brain is never refused.
"""

from __future__ import annotations

import io
import json
import threading
from types import SimpleNamespace

import pytest

from aios import config
from aios.core import cloud_spend, model_calls
from aios.core.anthropic_direct import _note_stream_usage, _with_usage
from aios.core.bedrock import BedrockClient
from aios.core.llm import LLMError


@pytest.fixture(autouse=True)
def _own_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    cloud_spend.forget_last_usage()
    yield


def test_which_brains_are_metered_derives_from_the_registry() -> None:
    assert cloud_spend.free_call_providers() == {"ollama", "plan"}
    for name in ("bedrock", "gemini", "anthropic", "openai_compat", "vertex_maas"):
        assert cloud_spend.is_metered(name), name
    assert cloud_spend.is_metered("a-cloud-added-later"), "unknown means metered"


def test_usage_is_recorded_for_the_month_and_free_brains_cost_nothing() -> None:
    cloud_spend.record_usage("bedrock", "m", 1_000_000, 0)
    cloud_spend.record_usage("gemini", "g", 0, 250_000)
    cloud_spend.record_usage("ollama", "local", 9_000_000, 9_000_000)
    cloud_spend.record_usage("plan", "claude-sonnet-5-5", 9_000_000, 9_000_000)
    assert cloud_spend.month_spend() == pytest.approx(1.0 + 1.0)
    records = cloud_spend.month_records()
    assert [r["provider"] for r in records] == ["bedrock", "gemini"]
    assert all(
        set(r) >= {"tokens_in", "tokens_out", "usd", "estimated"} for r in records
    )
    assert not any("prompt" in r or "text" in r for r in records)


def test_the_last_usage_is_this_threads_own() -> None:
    cloud_spend.record_usage("bedrock", "mine", 3, 4)
    other: list = []
    t = threading.Thread(target=lambda: other.append(cloud_spend.last_usage()))
    t.start()
    t.join()
    assert other == [None]
    assert cloud_spend.last_usage()["model"] == "mine"


def test_at_the_ceiling_a_metered_call_is_refused_before_it_leaves(monkeypatch) -> None:
    monkeypatch.setattr(config, "CLOUD_MONTHLY_USD", 0.5)
    with model_calls.gateway_scope("test"):
        model_calls.observe("bedrock", "m", "converse")  # under: it leaves
        cloud_spend.record_usage("bedrock", "m", 500_000, 0)  # $0.50 recorded
        with pytest.raises(cloud_spend.CloudSpendCeilingReached) as refused:
            model_calls.observe("gemini", "g", "chat")
        assert isinstance(refused.value, LLMError), "failover moves on"
        assert "$0.50" in str(refused.value) and "AIOS_CLOUD_MONTHLY_USD" in str(
            refused.value
        )
        model_calls.observe("ollama", "local", "chat")  # the local brain: never
        model_calls.observe("plan", "claude-sonnet-5-5", "chat")  # his plan: never
    [day] = (config.DATA_DIR / "model_calls").glob("*.jsonl")
    rows = [json.loads(line) for line in day.read_text(encoding="utf-8").splitlines()]
    refused_rows = [r for r in rows if r.get("refused")]
    assert [(r["provider"], r["refused_for"]) for r in refused_rows] == [
        ("gemini", "spend ceiling")
    ]


def test_bedrock_records_the_tokens_aws_reports_for_a_call_and_a_stream() -> None:
    class Fake:
        def converse(self, **kwargs):
            return {
                "output": {"message": {"content": [{"text": "ok"}]}},
                "usage": {"inputTokens": 120, "outputTokens": 30},
            }

        def converse_stream(self, **kwargs):
            return {
                "stream": [
                    {"contentBlockDelta": {"delta": {"text": "o"}}},
                    {"contentBlockDelta": {"delta": {"text": "k"}}},
                    {"metadata": {"usage": {"inputTokens": 50, "outputTokens": 7}}},
                ]
            }

    client = BedrockClient(model="model-x", region="us-east-1", client=Fake())
    with model_calls.gateway_scope("test"):
        client.chat([{"role": "user", "content": "hi"}])
        assert "".join(client.stream_chat([{"role": "user", "content": "hi"}])) == "ok"
    assert [
        (r["tokens_in"], r["tokens_out"], r["estimated"])
        for r in cloud_spend.month_records()
    ] == [
        (120, 30, False),
        (50, 7, False),
    ]


def test_gemini_records_its_usage_metadata_thinking_as_output() -> None:
    from aios.core.gemini import _gemini_tokens

    usage = SimpleNamespace(
        prompt_token_count=40, candidates_token_count=10, thoughts_token_count=5
    )
    assert _gemini_tokens(SimpleNamespace(usage_metadata=usage)) == (40, 15)
    assert _gemini_tokens(SimpleNamespace()) is None
    chunks = [SimpleNamespace(), SimpleNamespace(usage_metadata=usage)]
    assert (
        list(cloud_spend.counted_stream(chunks, "gemini", "g", _gemini_tokens))
        == chunks
    )
    [record] = cloud_spend.month_records()
    assert (record["tokens_in"], record["tokens_out"]) == (40, 15)


def test_anthropic_records_a_calls_usage_and_a_streams() -> None:
    _with_usage({"usage": {"input_tokens": 11, "output_tokens": 2}}, "claude-x")
    seen = [0, 0]
    _note_stream_usage(
        {
            "type": "message_start",
            "message": {"usage": {"input_tokens": 90, "output_tokens": 1}},
        },
        seen,
    )
    _note_stream_usage({"type": "message_delta", "usage": {"output_tokens": 44}}, seen)
    assert seen == [90, 44]
    [record] = cloud_spend.month_records()
    assert (record["provider"], record["tokens_in"], record["tokens_out"]) == (
        "anthropic",
        11,
        2,
    )


def test_an_openai_style_stream_without_usage_is_recorded_as_an_estimate(
    monkeypatch,
) -> None:
    from aios.core import openai_compat

    lines = [
        b'data: {"choices": [{"delta": {"content": "hello there"}}]}\n',
        b"data: [DONE]\n",
    ]

    class _Response(io.BytesIO):
        def __enter__(self):
            return iter(lines)

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        openai_compat.urllib.request, "urlopen", lambda *a, **kw: _Response()
    )
    client = openai_compat.OpenAICompatClient(
        model="gpt-x", base_url="https://example.invalid/v1", api_key="k"
    )
    with model_calls.gateway_scope("test"):
        assert "".join(client.stream_chat([{"role": "user", "content": "hi"}])) == (
            "hello there"
        )
    [record] = cloud_spend.month_records()
    assert record["provider"] == "openai_compat" and record["estimated"] is True
    assert record["tokens_out"] == 4, "11 characters at three a token, rounded up"
