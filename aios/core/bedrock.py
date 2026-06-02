"""AWS Bedrock chat client — a *cloud* ChatClient for the agentic loop.

Implements the same ``chat(messages, *, tools, model) -> message-dict`` contract
as :class:`aios.core.llm.OllamaClient`, but backed by Bedrock's **Converse** API
(which offers uniform tool-use across Claude / Nova / Llama). This lets the agent
run in the cloud when the local GPU can't host a model — *without* changing the
tool loop, memory, reflection, or the security gateway.

Design notes:
  * ``boto3`` is imported **lazily** (only when a real client is constructed), so
    the dependency is optional and the test suite — which injects a fake client —
    never needs it.
  * Credentials come from boto3's default chain (env vars / shared profile /
    role). This module never reads or writes them to disk.
  * The agent speaks an Ollama-shaped message protocol (``tool_calls`` with no
    ids; ``role: "tool"`` results). Converse is Anthropic-shaped (``toolUse`` /
    ``toolResult`` paired by ``toolUseId``). :func:`_to_converse` bridges the two,
    synthesising ids and pairing each tool result with its preceding call.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from aios import config
from aios.core.llm import LLMError


def _to_converse(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert agent (Ollama-style) messages into ``(system, converse_messages)``.

    Converse takes the system prompt separately and represents tool activity as
    ``toolUse`` (assistant) / ``toolResult`` (user) content blocks paired by id.
    The agent's messages carry no ids, so we mint one per call and pair the
    following ``role: "tool"`` results to them in order.
    """
    system: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    pending_ids: list[str] = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            if str(content).strip():
                system.append({"text": str(content)})
        elif role == "user":
            out.append({"role": "user", "content": [{"text": str(content)}]})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            text = str(content).strip()
            if text:
                blocks.append({"text": text})
            pending_ids = []
            for i, call in enumerate(msg.get("tool_calls") or []):
                fn = call.get("function", {}) if isinstance(call, dict) else {}
                tid = str(call.get("id") or f"tool_{len(out)}_{i}")
                pending_ids.append(tid)
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                blocks.append(
                    {"toolUse": {"toolUseId": tid, "name": str(fn.get("name", "")), "input": args or {}}}
                )
            if not blocks:
                blocks.append({"text": ""})  # Converse rejects empty content
            out.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            tid = pending_ids.pop(0) if pending_ids else f"tool_orphan_{len(out)}"
            out.append(
                {
                    "role": "user",
                    "content": [
                        {"toolResult": {"toolUseId": tid, "content": [{"text": str(content)}]}}
                    ],
                }
            )
    return system, out


def _to_tool_config(tools: Optional[list[dict[str, Any]]]) -> Optional[dict[str, Any]]:
    """Map OpenAI-style function specs to a Converse ``toolConfig`` (or ``None``)."""
    if not tools:
        return None
    specs: list[dict[str, Any]] = []
    for tool in tools:
        fn = tool.get("function", {}) if isinstance(tool, dict) else {}
        specs.append(
            {
                "toolSpec": {
                    "name": str(fn.get("name", "")),
                    "description": str(fn.get("description", "")),
                    "inputSchema": {
                        "json": fn.get("parameters") or {"type": "object", "properties": {}}
                    },
                }
            }
        )
    return {"tools": specs}


def _parse_output(message: dict[str, Any]) -> dict[str, Any]:
    """Map a Converse assistant message back to the agent's Ollama-style dict."""
    text = ""
    tool_calls: list[dict[str, Any]] = []
    for block in message.get("content", []) or []:
        if not isinstance(block, dict):
            continue
        if "text" in block:
            text += str(block["text"])
        elif "toolUse" in block:
            tu = block["toolUse"]
            tool_calls.append(
                {
                    "id": tu.get("toolUseId"),
                    "function": {"name": tu.get("name", ""), "arguments": tu.get("input") or {}},
                }
            )
    result: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


class BedrockClient:
    """:class:`~aios.agents.tool_agent.ChatClient` backed by Bedrock Converse."""

    def __init__(
        self,
        *,
        model: str = config.BEDROCK_MODEL,
        region: str = config.BEDROCK_REGION,
        max_tokens: int = config.BEDROCK_MAX_TOKENS,
        temperature: float = config.LLM_TEMPERATURE,
        client: Optional[Any] = None,
    ) -> None:
        self.model = model
        self.region = region
        self.max_tokens = max_tokens
        self.temperature = temperature
        if client is not None:
            self._client = client  # injected fake (tests)
        else:
            try:
                import boto3  # lazy: only required when Bedrock is actually used
            except ImportError as exc:  # pragma: no cover - environment-dependent
                raise LLMError("boto3 is required for AWS Bedrock; pip install boto3") from exc
            self._client = boto3.client("bedrock-runtime", region_name=region or None)

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """One non-streaming chat turn via Bedrock Converse.

        Returns the assistant message in the agent's shape
        (``role``/``content`` [+ ``tool_calls``]). Raises :class:`LLMError` on any
        Bedrock/credential failure so the agent surfaces a clean error event.
        """
        system, converse_messages = _to_converse(messages)
        kwargs: dict[str, Any] = {
            "modelId": model or self.model,
            "messages": converse_messages,
            "inferenceConfig": {"maxTokens": self.max_tokens, "temperature": self.temperature},
        }
        if system:
            kwargs["system"] = system
        tool_config = _to_tool_config(tools)
        if tool_config:
            kwargs["toolConfig"] = tool_config

        try:
            response = self._client.converse(**kwargs)
        except Exception as exc:  # noqa: BLE001 - surface uniformly to the agent
            raise LLMError(f"Bedrock Converse failed for '{model or self.model}': {exc}") from exc

        message = (response.get("output") or {}).get("message") or {}
        if not isinstance(message, dict):
            return {"role": "assistant", "content": ""}
        return _parse_output(message)
