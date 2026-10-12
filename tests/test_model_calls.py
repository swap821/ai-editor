"""Every model call is counted where it leaves, inside the gateway or not.

Pinned without a model:
* each provider adapter records exactly one ledger entry per request, outside
  any scope as ungated, inside one as that entrance;
* each of the gateway's five entrances scopes the caller's model call -- and a
  stream holds the scope only while it advances, never while its consumer works;
* the ledger reader, retention, and a ledger that cannot be written;
* the inventory's verdicts: an ungated call, a surface that never reached a
  model, and a ledger that missed a request the server received.
"""

from __future__ import annotations

import io
import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from aios import config
from aios.core import model_calls


@pytest.fixture
def ledger(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(model_calls, "_WRITE_FAILED", False)
    return tmp_path / "model_calls"


def _records(ledger: Path) -> list[dict[str, Any]]:
    return model_calls.read_ledger(
        ledger.parent, datetime.now(timezone.utc) - timedelta(minutes=5)
    )


# --------------------------------------------------------------------------- #
# The ledger
# --------------------------------------------------------------------------- #


def test_a_call_outside_the_gateway_is_recorded_as_ungated_with_its_site(
    ledger,
) -> None:
    model_calls.observe("ollama", "m", "chat")
    (record,) = _records(ledger)
    assert record["entrance"] is None
    assert record["provider"] == "ollama" and record["model"] == "m"
    site = "tests/test_model_calls.py:" + (
        "test_a_call_outside_the_gateway_is_recorded_as_ungated_with_its_site"
    )
    assert record["site"] == site and record["stack"][0] == site
    assert set(record) == {
        "ts",
        "provider",
        "model",
        "method",
        "entrance",
        "site",
        "stack",
        "pid",
    }, "nothing else -- no prompt, no output, no key"


def test_a_scope_names_the_entrance_and_ends_with_its_block(ledger) -> None:
    with model_calls.gateway_scope("route"):
        model_calls.observe("ollama", "m", "chat")
    model_calls.observe("ollama", "m", "chat")
    assert [r["entrance"] for r in _records(ledger)] == ["route", None]


def test_a_stream_is_in_scope_only_while_it_advances(ledger) -> None:
    seen_by_consumer = []

    def provider_stream():
        model_calls.observe("ollama", "m", "stream_complete")
        yield "a"
        yield "b"

    for _chunk in model_calls.scoped_iter("stream", provider_stream):
        seen_by_consumer.append(model_calls.current_entrance())
        model_calls.observe("bedrock", "x", "converse")  # the consumer's own call
    assert seen_by_consumer == [None, None]
    assert [(r["provider"], r["entrance"]) for r in _records(ledger)] == [
        ("ollama", "stream"),
        ("bedrock", None),
        ("bedrock", None),
    ]


def test_a_failing_stream_still_resets_the_scope(ledger) -> None:
    def broken():
        yield "a"
        raise RuntimeError("provider died")

    with pytest.raises(RuntimeError):
        for _ in model_calls.scoped_iter("stream", broken):
            pass
    assert model_calls.current_entrance() is None


def test_the_reader_keeps_a_damaged_line_and_respects_since(ledger) -> None:
    ledger.mkdir(parents=True)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=2)).isoformat()
    (ledger / f"{now.date().isoformat()}.jsonl").write_text(
        json.dumps({"ts": old, "provider": "ollama"})
        + "\n{not json\n"
        + json.dumps({"ts": now.isoformat(), "provider": "bedrock"})
        + "\n",
        encoding="utf-8",
    )
    records = model_calls.read_ledger(ledger.parent, now - timedelta(hours=1))
    assert records == [
        {"unreadable": "{not json"},
        {"ts": now.isoformat(), "provider": "bedrock"},
    ]
    assert model_calls.read_ledger(ledger.parent / "absent", now) == []


def test_old_days_are_pruned_when_a_new_day_starts(ledger) -> None:
    ledger.mkdir(parents=True)
    ancient = (datetime.now(timezone.utc) - timedelta(days=40)).date().isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    (ledger / f"{ancient}.jsonl").write_text("", encoding="utf-8")
    (ledger / f"{recent}.jsonl").write_text("", encoding="utf-8")
    model_calls.observe("ollama", "m", "chat")
    names = {p.stem for p in ledger.glob("*.jsonl")}
    assert ancient not in names and recent in names


def test_a_ledger_that_cannot_be_written_never_blocks_the_call_and_says_so(
    tmp_path, monkeypatch, caplog
) -> None:
    blocker = tmp_path / "data"
    blocker.write_text("a file where the directory should be", encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", blocker)
    monkeypatch.setattr(model_calls, "_WRITE_FAILED", False)
    with caplog.at_level(logging.WARNING, logger="aios.core.model_calls"):
        model_calls.observe("ollama", "m", "chat")
        model_calls.observe("ollama", "m", "chat")
    warnings = [r for r in caplog.records if "ledger write failed" in r.getMessage()]
    assert len(warnings) == 1, "said once, loudly"


# --------------------------------------------------------------------------- #
# The adapters: one record per request
# --------------------------------------------------------------------------- #


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(body: dict[str, Any]):
    def urlopen(request, timeout=None):
        return _Response(json.dumps(body).encode("utf-8"))

    return urlopen


def _call(fn) -> None:
    try:
        result = fn()
        if hasattr(result, "__next__"):
            list(result)
    except Exception:  # noqa: BLE001 - a parse failure after the send is fine here
        pass


def test_ollama_records_each_request(ledger, monkeypatch) -> None:
    from aios.core.llm import OllamaClient

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _fake_urlopen({"response": "ok", "message": {"content": "ok"}, "done": True}),
    )
    client = OllamaClient("m1", host="http://ollama.test")
    _call(lambda: client.complete("hi"))
    _call(lambda: client.chat([{"role": "user", "content": "hi"}], model="m2"))
    _call(lambda: client.stream_complete("hi"))
    assert [(r["provider"], r["model"], r["method"]) for r in _records(ledger)] == [
        ("ollama", "m1", "complete"),
        ("ollama", "m2", "chat"),
        ("ollama", "m1", "stream_complete"),
    ]


def test_ollama_metadata_probes_are_not_model_calls(ledger, monkeypatch) -> None:
    from aios.core.llm import OllamaClient

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({"models": []}))
    client = OllamaClient("m1", host="http://ollama.test")
    _call(client.list_models)
    _call(client.is_available)
    assert _records(ledger) == []


def test_bedrock_records_each_request_once_even_when_it_retries(ledger) -> None:
    from aios.core.bedrock import BedrockClient

    class Transport:
        def __init__(self) -> None:
            self.sent = 0

        def converse(self, **kwargs):
            self.sent += 1
            if self.sent == 1:
                raise RuntimeError("doesn't support the temperature field")
            return {"output": {"message": {"role": "assistant", "content": []}}}

        def converse_stream(self, **kwargs):
            return {"stream": []}

    class NoDiscovery:
        def list_foundation_models(self, **_):
            return {"modelSummaries": []}

        def list_inference_profiles(self, **_):
            return {"inferenceProfileSummaries": []}

    transport = Transport()
    client = BedrockClient(
        model="b.retry-test", region="r", client=transport, ctrl_client=NoDiscovery()
    )
    _call(lambda: client.chat([{"role": "user", "content": "hi"}]))
    _call(lambda: client.stream_chat([{"role": "user", "content": "hi"}]))
    assert transport.sent == 2, "the temperature retry re-sent"
    assert [(r["provider"], r["method"]) for r in _records(ledger)] == [
        ("bedrock", "converse"),
        ("bedrock", "converse_stream"),
    ], "one logical request, one record"


@pytest.mark.parametrize("kind", ["openai_compat", "vertex_maas", "anthropic"])
def test_http_cloud_adapters_record_each_request(ledger, monkeypatch, kind) -> None:
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _fake_urlopen({"choices": [{"message": {"content": "ok"}}], "content": []}),
    )
    if kind == "anthropic":
        from aios.core.anthropic_direct import AnthropicDirectClient

        client: Any = AnthropicDirectClient(api_key="k", model="c1")
    elif kind == "vertex_maas":
        from aios.core.vertex_maas import VertexMaaSClient

        client = VertexMaaSClient.__new__(VertexMaaSClient)
        from aios.core.openai_compat import OpenAICompatClient

        OpenAICompatClient.__init__(
            client, api_key="k", base_url="http://v.test", model="c1"
        )
        monkeypatch.setattr(client, "_headers", lambda: {})
    else:
        from aios.core.openai_compat import OpenAICompatClient

        client = OpenAICompatClient(api_key="k", base_url="http://o.test", model="c1")
    _call(lambda: client.chat([{"role": "user", "content": "hi"}]))
    _call(lambda: client.stream_chat([{"role": "user", "content": "hi"}]))
    provider = "anthropic" if kind == "anthropic" else kind
    assert [(r["provider"], r["method"]) for r in _records(ledger)] == [
        (provider, "chat"),
        (provider, "stream_chat"),
    ]


def test_gemini_records_each_request(ledger) -> None:
    from aios.core.gemini import GeminiClient

    class Models:
        def generate_content(self, **kwargs):
            raise ValueError("no content")

        def generate_content_stream(self, **kwargs):
            return iter(())

    class FakeGenai:
        models = Models()

    client = GeminiClient(model="g1", project="p", client=FakeGenai())
    _call(lambda: client.chat([{"role": "user", "content": "hi"}]))
    _call(lambda: client.stream_chat([{"role": "user", "content": "hi"}]))
    _call(lambda: client.stream_chat_with_tools([{"role": "user", "content": "hi"}]))
    assert [(r["provider"], r["method"]) for r in _records(ledger)] == [
        ("gemini", "chat"),
        ("gemini", "stream_chat"),
        ("gemini", "stream_chat_with_tools"),
    ]


# --------------------------------------------------------------------------- #
# The gateway's five entrances
# --------------------------------------------------------------------------- #


@pytest.fixture
def stop(tmp_path):
    """A wired, released emergency latch: the production provider's."""
    from aios.api.deps import get_emergency_stop

    return get_emergency_stop()


def _governed_kwargs(stop, model_call) -> dict[str, Any]:
    return {
        "request_id": "r-1",
        "operator_identity_digest": "a" * 64,
        "constitution_digest": "b" * 64,
        "goal": "say ok",
        "desired_outcome": "ok",
        "target": "local",
        "delegated_authority_summary": "none",
        "model_call": model_call,
        "emergency_stop": stop,
        "context_store": _NullStore(),
    }


class _NullStore:
    def save(self, *args, **kwargs) -> None:
        return None

    def save_bundle(self, *args, **kwargs) -> None:
        return None


def test_route_scopes_its_model_call(ledger, stop) -> None:
    from aios.application.intelligence import gateway

    def call(context):
        model_calls.observe("ollama", "m", "complete")
        return "ok"

    gateway.route_intelligence_request(**_governed_kwargs(stop, call))
    assert [r["entrance"] for r in _records(ledger)] == ["route"]


def test_stream_scopes_its_eager_call_and_each_advance(ledger, stop) -> None:
    from aios.application.intelligence import gateway

    def call(context):
        model_calls.observe("ollama", "m", "eager")

        def chunks():
            model_calls.observe("ollama", "m", "lazy")
            yield "ok"

        return chunks()

    result = gateway.stream_intelligence_request(**_governed_kwargs(stop, call))
    assert [r["method"] for r in _records(ledger)] == ["eager"], (
        "model_call ran at stream() time, as it always has"
    )
    consumer = []
    for _ in result.chunks:
        consumer.append(model_calls.current_entrance())
    assert consumer == [None]
    assert [(r["method"], r["entrance"]) for r in _records(ledger)] == [
        ("eager", "stream"),
        ("lazy", "stream"),
    ]


def test_structured_stream_scopes_its_call(ledger, stop) -> None:
    from aios.application.intelligence import gateway

    def call(context):
        model_calls.observe("bedrock", "m", "converse_stream")
        yield {"type": "text", "text": "ok"}

    result = gateway.stream_structured_intelligence_request(
        **_governed_kwargs(stop, call)
    )
    list(result.events)
    assert [r["entrance"] for r in _records(ledger)] == ["stream_structured"]


def test_the_compatibility_entrances_scope_their_calls(ledger, stop) -> None:
    from aios.application.intelligence import gateway

    def complete():
        model_calls.observe("ollama", "m", "complete")
        return "ok"

    def stream():
        model_calls.observe("ollama", "m", "stream_complete")
        yield "ok"

    gateway.complete_compatibility_intelligence_request(
        request_id="c-1", target="local", model_call=complete, emergency_stop=stop
    )
    list(
        gateway.stream_compatibility_intelligence_request(
            request_id="c-2", target="local", model_call=stream, emergency_stop=stop
        ).chunks
    )
    assert [r["entrance"] for r in _records(ledger)] == [
        "complete_compatibility",
        "stream_compatibility",
    ]


# --------------------------------------------------------------------------- #
# The inventory's verdicts (pure)
# --------------------------------------------------------------------------- #


def _surface(*calls: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"status": 200, "calls": list(calls), **extra}


def _c(entrance, provider="ollama", site="aios/x.py:f") -> dict[str, Any]:
    return {
        "provider": provider,
        "method": "chat",
        "entrance": entrance,
        "site": site,
        "stack": [site, "aios/y.py:outer"],
    }


def test_the_inventory_names_an_ungated_call_and_its_site() -> None:
    from tools import model_call_inventory as inv

    report = {
        "surfaces": {"a": _surface(_c("route")), "b": _surface(_c(None))},
        "bedrock_requests": 0,
    }
    result = inv.judge(report, ollama_requests=2)
    assert result["surfaces"]["a"]["verdict"] == "gated"
    assert result["surfaces"]["b"]["verdict"] == "UNGATED"
    assert result["ungated_sites"] == {"aios/x.py:f [ollama.chat]": 1}
    assert result["integrity"]["ledger_complete"] is True
    assert "aios/y.py:outer" in result["observed_frames"]


def test_a_surface_with_no_call_is_not_reached_never_clean() -> None:
    from tools import model_call_inventory as inv

    report = {"surfaces": {"a": _surface(), "b": _surface(error="boom")}}
    result = inv.judge(report, ollama_requests=0)
    assert result["surfaces"]["a"]["verdict"] == "not_reached"
    assert result["surfaces"]["b"]["verdict"] == "error"


def test_a_request_the_ledger_missed_breaks_integrity() -> None:
    from tools import model_call_inventory as inv

    report = {"surfaces": {"a": _surface(_c("route"))}, "bedrock_requests": 1}
    result = inv.judge(report, ollama_requests=1)
    assert result["integrity"]["ledger_complete"] is False, "bedrock: 1 sent, 0 seen"
    result = inv.judge({"surfaces": {"a": _surface(_c("route"))}}, ollama_requests=2)
    assert result["integrity"]["ledger_complete"] is False, "ollama: 2 sent, 1 seen"


def test_static_sites_find_a_real_caller_and_skip_the_plumbing() -> None:
    from tools import model_call_inventory as inv

    sites = inv.static_call_sites()
    assert "aios/core/alignment.py:understand" in sites
    assert not any(s.startswith("aios/core/llm.py") for s in sites)
    assert not any(
        s.startswith("aios/application/intelligence/gateway.py") for s in sites
    )
