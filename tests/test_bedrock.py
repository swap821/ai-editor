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
    """Stub bedrock-runtime: records the converse kwargs, returns canned replies."""

    def __init__(self, reply: dict, *, stream_reply: dict | None = None) -> None:
        self.reply = reply
        self.stream_reply = stream_reply or {"stream": []}
        self.last: dict | None = None
        self.stream_last: dict | None = None

    def converse(self, **kwargs):
        self.last = kwargs
        return self.reply

    def converse_stream(self, **kwargs):
        self.stream_last = kwargs
        return self.stream_reply


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


def test_to_converse_merges_multiple_tool_results_into_one_user_turn() -> None:
    """Bedrock's Converse API rejects a toolUse turn whose results are split across
    multiple user turns -- it expects every toolResult for one assistant turn in a
    SINGLE following user message (reproduces a live ValidationException: "Expected
    toolResult blocks at messages.N.content for the following Ids: [...]").
    """
    _, conv = _to_converse([
        {"role": "user", "content": "do two things"},
        {"role": "assistant", "content": "",
         "tool_calls": [
             {"function": {"name": "create_file", "arguments": {"filepath": "a.py"}}},
             {"function": {"name": "run_command", "arguments": {"command": "pytest"}}},
         ]},
        {"role": "tool", "content": "created a.py"},
        {"role": "tool", "content": "pytest: 2 passed"},
    ])
    assert len(conv) == 3  # user, assistant(2 toolUse), ONE user(2 toolResult)
    tool_use_ids = [b["toolUse"]["toolUseId"] for b in conv[1]["content"] if "toolUse" in b]
    result_msg = conv[2]
    assert result_msg["role"] == "user"
    result_ids = [b["toolResult"]["toolUseId"] for b in result_msg["content"]]
    assert result_ids == tool_use_ids
    assert [b["toolResult"]["content"] for b in result_msg["content"]] == [
        [{"text": "created a.py"}], [{"text": "pytest: 2 passed"}],
    ]


def test_to_converse_orphans_extra_tool_result_when_unpaired() -> None:
    """A `role: tool` message with NO preceding matching toolUse (e.g.
    ToolAgent._auto_verify's forced post-write check, which the harness injects
    into history and which the model never asked for) currently falls back to a
    synthetic `tool_orphan_*` id (bedrock.py `_to_converse`:
    `tid = pending_ids.pop(0) if pending_ids else f"tool_orphan_{len(out)}"`).
    Because the buffering fix merges consecutive tool-role messages into ONE
    user turn, this manufactures an EXTRA toolResult block riding along with the
    genuine one -- 2 toolResult blocks for an assistant turn that only had 1
    toolUse block. Reproduces the live ValidationException: "The number of
    toolResult blocks at messages.N.content exceeds the number of toolUse
    blocks of previous turn."
    """
    _, conv = _to_converse([
        {"role": "user", "content": "edit and verify a.py"},
        {"role": "assistant", "content": "",
         "tool_calls": [
             {"function": {"name": "edit_file", "arguments": {"filepath": "a.py"}}},
         ]},
        {"role": "tool", "content": "edit applied"},            # paired to the real toolUse
        {"role": "tool", "content": "[VERIFY PASS] 2 passed"},   # auto-verify's unpaired append
    ])
    tool_use_ids = [b["toolUse"]["toolUseId"] for b in conv[1]["content"] if "toolUse" in b]
    result_msg = conv[2]
    result_ids = [b["toolResult"]["toolUseId"] for b in result_msg.get("content", []) if "toolResult" in b]
    assert len(result_ids) == len(tool_use_ids), (
        f"{len(result_ids)} toolResult blocks for only {len(tool_use_ids)} toolUse id(s) -- "
        "Bedrock rejects this with 'number of toolResult blocks exceeds toolUse blocks'"
    )


def test_to_converse_never_mixes_toolresult_and_text_in_one_user_turn() -> None:
    """Bedrock's Converse API rejects a user turn that mixes a toolResult block
    with a plain text block: "Conversation blocks and tool result blocks cannot
    be provided in the same turn" (confirmed live: a ValidationException at
    messages.N.content, e.g. https://github.com/browser-use/browser-use/issues/710).

    tool_agent.py's _pre_apply_grants appends a REAL create/edit toolResult on
    turn-resume, then _auto_verify appends its forced post-write check
    IMMEDIATELY after with no assistant/user message in between (e.g.
    "[VERIFY SKIPPED] no sibling test for pipeline.py" when the file has no
    sibling test yet -- true for the first file of any create-then-test
    mission). Defect 1's fix folds that orphan in as plain {"text": ...}, but
    it lands in the SAME buffered pending_results as the genuine toolResult,
    so _to_converse flushes both into ONE user turn -- reproducing the live
    ValidationException at messages.2 (right after the first assistant toolUse
    block) even with Defects 1 and 2 already fixed.
    """
    _, conv = _to_converse([
        {"role": "user", "content": "create pipeline.py"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "create_file",
                                       "arguments": {"filepath": "pipeline.py"}}}]},
        {"role": "tool", "content": "Created pipeline.py (120 bytes, 5 line(s))"},
        {"role": "tool", "content": "[VERIFY SKIPPED] no sibling test for pipeline.py"},
    ])
    result_msg = conv[-1]
    assert result_msg["role"] == "user"
    kinds = {tuple(block.keys())[0] for block in result_msg["content"]}
    assert kinds == {"toolResult"}, (
        f"user turn mixes block kinds {kinds} -- Bedrock rejects a turn combining "
        "toolResult blocks with plain text/conversation blocks in messages.N.content"
    )


def test_to_converse_drops_toolresult_for_dangling_tooluse() -> None:
    """When an assistant turn issues MULTIPLE tool calls and only SOME of them
    ever get a `role: tool` result appended (e.g. tool_agent.py's approval-pause
    path returns immediately once one call in the batch needs human approval,
    abandoning any LATER call in that same batch -- it is never dispatched,
    never surfaced to the user, and `_pre_apply_grants` on resume only re-applies
    what was actually approved), `_to_converse` silently resets `pending_ids` at
    the next assistant/user message instead of surfacing the gap, so the
    dangling toolUse is submitted to Bedrock with no matching toolResult ever.
    Reproduces the live ValidationException: "Expected toolResult blocks at
    messages.N.content for the following Ids: [...]."
    """
    _, conv = _to_converse([
        {"role": "user", "content": "edit two files"},
        {"role": "assistant", "content": "",
         "tool_calls": [
             {"id": "callB", "function": {"name": "edit_file", "arguments": {"filepath": "x.py"}}},
             {"id": "callC", "function": {"name": "edit_file", "arguments": {"filepath": "y.py"}}},
         ]},
        # Only callB ever gets a result (approved+applied on resume); callC was
        # never dispatched -- its toolUse is left permanently dangling.
        {"role": "tool", "content": "edit x.py applied"},
        {"role": "user", "content": "continue"},
    ])
    tool_use_ids = [b["toolUse"]["toolUseId"] for b in conv[1]["content"] if "toolUse" in b]
    result_ids = [b["toolResult"]["toolUseId"] for b in conv[2]["content"] if "toolResult" in b]
    assert set(result_ids) == set(tool_use_ids), (
        f"toolUse ids {tool_use_ids} vs answered ids {result_ids} -- Bedrock rejects this "
        "with 'Expected toolResult blocks ... for the following Ids'"
    )


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


def test_stream_chat_calls_converse_stream_and_yields_text_chunks() -> None:
    fake = FakeBedrock(
        {},
        stream_reply={"stream": [
            {"messageStart": {"role": "assistant"}},
            {"contentBlockDelta": {"delta": {"text": "hel"}}},
            {"contentBlockDelta": {"delta": {"text": "lo"}}},
            {"messageStop": {"stopReason": "end_turn"}},
        ]},
    )
    client = BedrockClient(model="model-x", region="us-east-1", client=fake)
    chunks = list(client.stream_chat(
        [{"role": "user", "content": "say hello"}],
        tools=[{"function": {"name": "read_file", "description": "", "parameters": {}}}],
    ))
    assert chunks == ["hel", "lo"]
    assert fake.stream_last["modelId"] == "model-x"
    assert "toolConfig" in fake.stream_last
    assert fake.stream_last["inferenceConfig"]["maxTokens"] >= 1


def test_stream_chat_applies_privacy_filter_before_converse_stream() -> None:
    raw_path = r"C:\Users\kumar\ai-editor\secrets.txt"
    fake = FakeBedrock({}, stream_reply={"stream": []})
    client = BedrockClient(model="m", region="r", client=fake)
    list(client.stream_chat([{"role": "user", "content": f"read {raw_path}"}]))
    sent = fake.stream_last["messages"][0]["content"][0]["text"]
    assert raw_path not in sent
    assert "[PATH REDACTED]" in sent


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


def test_list_models_falls_back_to_curated_range_on_control_plane_error() -> None:
    # No control-plane access (``bedrock:ListFoundationModels`` denied — a common
    # AWS permission posture) must NOT collapse the organism to a single Bedrock
    # model. It offers the curated RANGE so ``auto`` + failover still pick across
    # tiers/providers — mirroring the Gemini client's curated fallback.
    from aios.core.bedrock import CURATED_MODELS

    class Boom:
        def list_foundation_models(self, **kwargs):
            raise RuntimeError("AccessDeniedException")

    client = BedrockClient(model="m", region="r", client=FakeBedrock({}), ctrl_client=Boom())
    models = client.list_models()
    assert len(models) > 1  # a RANGE, never just the one default
    assert models == CURATED_MODELS
    assert all(m.get("id") and m.get("name") for m in models)
