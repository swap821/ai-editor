"""Unit tests for the AWS Bedrock chat client (Converse mapping + parsing).

A fake bedrock-runtime client is injected, so the suite never imports boto3,
makes a network call, or needs AWS credentials — the conversion logic is what's
under test, not AWS itself.
"""
from __future__ import annotations

import pytest

from aios.core.bedrock import BedrockClient, _parse_output, _to_converse, _to_tool_config
from aios.core.llm import LLMError

pytestmark = [pytest.mark.cloud]


class FakeBedrock:
    """Stub bedrock-runtime: records the converse kwargs, returns a canned reply."""

    def __init__(self, reply: dict) -> None:
        self.reply = reply
        self.last: dict | None = None

    def converse(self, **kwargs):
        self.last = kwargs
        return self.reply


def test_to_converse_splits_system_and_pairs_tools() -> None:
    system, conv = _to_converse([
        {"role": "system", "content": "you are an agent"},
        {"role": "user", "content": "list files"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "execute_terminal", "arguments": {"command": "ls"}}}]},
        {"role": "tool", "content": "ran: ls"},
    ])
    assert system == [{"text": "you are an agent"}]
    assert conv[0] == {"role": "user", "content": [{"text": "list files"}]}
    tool_use = conv[1]["content"][-1]["toolUse"]
    assert tool_use["name"] == "execute_terminal"
    assert tool_use["input"] == {"command": "ls"}
    tool_result = conv[2]["content"][0]["toolResult"]
    assert tool_result["toolUseId"] == tool_use["toolUseId"]   # result paired to its call
    assert tool_result["content"] == [{"text": "ran: ls"}]


def test_to_converse_coerces_stringified_arguments() -> None:
    _, conv = _to_converse([
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file", "arguments": '{"filepath": "a.py"}'}}]},
    ])
    assert conv[0]["content"][0]["toolUse"]["input"] == {"filepath": "a.py"}


def test_to_tool_config_maps_function_specs() -> None:
    cfg = _to_tool_config([
        {"type": "function", "function": {
            "name": "read_file", "description": "read it",
            "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}},
                           "required": ["filepath"]},
        }}
    ])
    spec = cfg["tools"][0]["toolSpec"]
    assert spec["name"] == "read_file"
    assert spec["description"] == "read it"
    assert spec["inputSchema"]["json"]["properties"]["filepath"]["type"] == "string"


def test_to_tool_config_none_when_empty() -> None:
    assert _to_tool_config(None) is None
    assert _to_tool_config([]) is None


def test_parse_output_extracts_text_and_tool_calls() -> None:
    parsed = _parse_output({"role": "assistant", "content": [
        {"text": "On it."},
        {"toolUse": {"toolUseId": "x1", "name": "execute_terminal",
                     "input": {"command": "pip install flask"}}},
    ]})
    assert parsed["content"] == "On it."
    assert parsed["tool_calls"][0]["function"]["name"] == "execute_terminal"
    assert parsed["tool_calls"][0]["function"]["arguments"] == {"command": "pip install flask"}


def test_parse_output_text_only_has_no_tool_calls() -> None:
    parsed = _parse_output({"role": "assistant", "content": [{"text": "just words"}]})
    assert parsed == {"role": "assistant", "content": "just words"}


def test_chat_calls_converse_and_returns_agent_shape() -> None:
    reply = {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": "x", "name": "execute_terminal",
                     "input": {"command": "pip install flask"}}},
    ]}}}
    fake = FakeBedrock(reply)
    client = BedrockClient(model="model-x", region="us-east-1", client=fake)
    out = client.chat(
        [{"role": "user", "content": "install flask"}],
        tools=[{"function": {"name": "execute_terminal", "description": "", "parameters": {}}}],
    )
    assert out["tool_calls"][0]["function"]["arguments"] == {"command": "pip install flask"}
    # Converse was handed the model id, a tool config, and an inference config.
    assert fake.last["modelId"] == "model-x"
    assert "toolConfig" in fake.last
    assert fake.last["inferenceConfig"]["maxTokens"] >= 1


def test_chat_wraps_failures_as_llmerror() -> None:
    class Boom:
        def converse(self, **kwargs):
            raise RuntimeError("ExpiredTokenException")

    client = BedrockClient(model="m", region="r", client=Boom())
    with pytest.raises(LLMError):
        client.chat([{"role": "user", "content": "hi"}])


class FakeCtrl:
    """Stub bedrock control-plane client for model discovery."""

    def __init__(self, summaries: list) -> None:
        self.summaries = summaries

    def list_foundation_models(self, **kwargs):
        return {"modelSummaries": self.summaries}


def test_list_models_filters_sorts_and_dedups() -> None:
    ctrl = FakeCtrl([
        {"modelId": "anthropic.claude-3-5-sonnet-20240620-v1:0", "providerName": "Anthropic",
         "modelName": "Claude 3.5 Sonnet", "outputModalities": ["TEXT"]},
        {"modelId": "amazon.nova-pro-v1:0", "providerName": "Amazon",
         "modelName": "Nova Pro", "outputModalities": ["TEXT"]},
        {"modelId": "amazon.nova-pro-v1:0", "providerName": "Amazon",
         "modelName": "Nova Pro", "outputModalities": ["TEXT"]},               # duplicate
        {"modelId": "amazon.titan-embed-text-v2:0", "providerName": "Amazon",
         "modelName": "Titan Embed", "outputModalities": ["EMBEDDING"]},        # not chat
    ])
    client = BedrockClient(model="m", region="r", client=FakeBedrock({}), ctrl_client=ctrl)
    models = client.list_models()
    ids = [m["id"] for m in models]

    assert "amazon.titan-embed-text-v2:0" not in ids       # embeddings excluded
    assert ids.count("amazon.nova-pro-v1:0") == 1          # deduped
    assert [m["name"] for m in models] == ["Amazon Nova Pro", "Anthropic Claude 3.5 Sonnet"]  # sorted


def test_list_models_empty_on_control_plane_error() -> None:
    class Boom:
        def list_foundation_models(self, **kwargs):
            raise RuntimeError("AccessDeniedException")

    client = BedrockClient(model="m", region="r", client=FakeBedrock({}), ctrl_client=Boom())
    assert client.list_models() == []
