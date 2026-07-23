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
  * **Privacy**: every message list is passed through :class:`PrivacyFilter`
    before transmission so conversation history, tool results, and secrets never
    leave the local machine unredacted.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator, Optional

from aios import config
from aios.application.models.privacy_audit import PrivacyAuditTracker
from aios.core.llm import LLMError
from aios.core.stream_protocol import StreamFinished
from aios.core.privacy_filter import PrivacyFilter, scrub_exception

logger = logging.getLogger(__name__)

#: Curated Bedrock range — the fallback when live control-plane discovery is
#: unavailable (``bedrock:ListFoundationModels`` denied, a common AWS posture). It
#: spans providers and capability tiers so the organism still routes across a RANGE
#: of cloud models, not just the one configured default. Live discovery, when
#: permitted, supersedes this entirely. Mirrors the Gemini client's curated list.
CURATED_MODELS: list[dict[str, str]] = [
    {
        "id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "name": "Anthropic Claude 3.5 Sonnet",
    },
    {
        "id": "anthropic.claude-3-5-haiku-20241022-v1:0",
        "name": "Anthropic Claude 3.5 Haiku",
    },
    {"id": "amazon.nova-pro-v1:0", "name": "Amazon Nova Pro"},
    {"id": "amazon.nova-lite-v1:0", "name": "Amazon Nova Lite"},
    {"id": "meta.llama3-1-70b-instruct-v1:0", "name": "Meta Llama 3.1 70B Instruct"},
    {"id": "mistral.mistral-large-2407-v1:0", "name": "Mistral Large"},
]


def _to_converse(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert agent (Ollama-style) messages into ``(system, converse_messages)``.

    Converse takes the system prompt separately and represents tool activity as
    ``toolUse`` (assistant) / ``toolResult`` (user) content blocks paired by id.
    The agent's messages carry no ids, so we mint one per call and pair the
    following ``role: "tool"`` results to them in order. Converse requires ALL
    toolResult blocks for one assistant turn in a SINGLE following user turn
    (a turn with N toolUse blocks split across N separate user messages is
    rejected with a ValidationException), so consecutive ``role: "tool"``
    messages are buffered and flushed as one user message.

    Two additional Bedrock-only invariants this also repairs (found via live
    golden-mission runs, 2026-07-05): (1) a ``role: tool`` message with no
    preceding pending toolUse id (e.g. ToolAgent's forced post-write
    ``_auto_verify`` check, which the harness injects and the model never
    asked for) is folded in as plain text instead of a synthetic
    ``tool_orphan_*`` toolResult -- the old fallback manufactured an EXTRA
    toolResult with no matching toolUse, which Converse also hard-rejects.
    (2) any toolUse id that never receives a matching ``tool`` message before
    the turn closes (e.g. a tool call in a multi-call batch abandoned when an
    earlier call in the same batch pauses for approval) is answered with a
    placeholder toolResult instead of being silently dropped -- Converse
    requires EVERY toolUse in one assistant turn to be answered in the very
    next user turn, with no exceptions.
    """
    system: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    pending_ids: list[str] = []
    pending_results: list[dict[str, Any]] = []

    def flush_tool_results() -> None:
        for orphan_id in pending_ids:
            pending_results.append(
                {
                    "toolResult": {
                        "toolUseId": orphan_id,
                        "content": [
                            {"text": "[no result recorded for this tool call]"}
                        ],
                    }
                }
            )
        pending_ids.clear()
        if pending_results:
            out.append({"role": "user", "content": list(pending_results)})
            pending_results.clear()

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            if str(content).strip():
                system.append({"text": str(content)})
        elif role == "user":
            flush_tool_results()
            out.append({"role": "user", "content": [{"text": str(content)}]})
        elif role == "assistant":
            flush_tool_results()
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
                    {
                        "toolUse": {
                            "toolUseId": tid,
                            "name": str(fn.get("name", "")),
                            "input": args or {},
                        }
                    }
                )
            if not blocks:
                blocks.append({"text": ""})  # Converse rejects empty content
            out.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            if pending_ids:
                tid = pending_ids.pop(0)
                pending_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tid,
                            "content": [{"text": str(content)}],
                        }
                    }
                )
            else:
                # An orphaned tool-role message (no pending toolUse to pair with --
                # e.g. ToolAgent's forced post-write _auto_verify check, which the
                # harness injects and the model never asked for) must never share a
                # user turn with a genuine toolResult: Bedrock's Converse API rejects
                # ANY user turn that mixes toolResult blocks with plain text/
                # conversation blocks ("Conversation blocks and tool result blocks
                # cannot be provided in the same turn"). Fold it into the content of
                # the most recently buffered toolResult instead of adding a sibling
                # top-level text block, so the turn stays pure-toolResult; fall back
                # to a bare text block only when no toolResult is buffered to attach
                # to (then there is nothing to mix with).
                for prior in reversed(pending_results):
                    tool_result = prior.get("toolResult")
                    if tool_result is not None:
                        tool_result["content"].append({"text": str(content)})
                        break
                else:
                    pending_results.append({"text": str(content)})
    flush_tool_results()
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
                        "json": fn.get("parameters")
                        or {"type": "object", "properties": {}}
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
                    "function": {
                        "name": tu.get("name", ""),
                        "arguments": tu.get("input") or {},
                    },
                }
            )
    result: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def _stream_text_from_converse(response: dict[str, Any]) -> Iterator[str]:
    """Yield text deltas from a Bedrock ``converse_stream`` response."""
    stream = response.get("stream") if isinstance(response, dict) else response
    for event in stream or []:
        if not isinstance(event, dict):
            continue
        delta = (event.get("contentBlockDelta") or {}).get("delta") or {}
        text = delta.get("text")
        if text:
            yield str(text)


def _stream_from_converse(response: dict[str, Any]) -> Iterator[str | StreamFinished]:
    """Yield text deltas then a :class:`StreamFinished` with any tool_calls.

    Unlike :func:`_stream_text_from_converse`, this captures tool_use blocks
    from the stream so the caller can detect tool_calls after streaming text.
    """
    stream = response.get("stream") if isinstance(response, dict) else response
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    current_tool: dict[str, Any] | None = None
    current_tool_input: list[str] = []

    for event in stream or []:
        if not isinstance(event, dict):
            continue
        # Text deltas
        delta_block = (event.get("contentBlockDelta") or {}).get("delta") or {}
        text = delta_block.get("text")
        if text:
            text_parts.append(str(text))
            yield str(text)
            continue
        # Tool use input deltas (JSON fragments)
        tool_delta = delta_block.get("toolUse")
        if tool_delta and "input" in tool_delta:
            current_tool_input.append(str(tool_delta["input"]))
            continue
        # Tool use block start
        start = (event.get("contentBlockStart") or {}).get("start") or {}
        tool_start = start.get("toolUse")
        if tool_start:
            if current_tool is not None:
                _finish_tool(current_tool, current_tool_input, tool_calls)
            current_tool = tool_start
            current_tool_input = []
            continue
        # Block stop — finalize any in-progress tool
        if "contentBlockStop" in event and current_tool is not None:
            _finish_tool(current_tool, current_tool_input, tool_calls)
            current_tool = None
            current_tool_input = []

    # Finalize any trailing tool block (defensive)
    if current_tool is not None:
        _finish_tool(current_tool, current_tool_input, tool_calls)

    yield StreamFinished(tool_calls=tool_calls, content="".join(text_parts))


def _finish_tool(
    tool_start: dict[str, Any],
    input_fragments: list[str],
    out: list[dict[str, Any]],
) -> None:
    """Assemble a tool_call dict from accumulated stream fragments."""
    raw = "".join(input_fragments)
    try:
        args = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        args = {}
    out.append(
        {
            "id": tool_start.get("toolUseId"),
            "function": {"name": str(tool_start.get("name", "")), "arguments": args},
        }
    )


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
        ctrl_client: Optional[Any] = None,
        privacy_audit_tracker: Optional[PrivacyAuditTracker] = None,
    ) -> None:
        self.model = model
        self.region = region
        self.max_tokens = max_tokens
        self.temperature = temperature
        #: Control-plane client (``bedrock``) for model discovery — created lazily
        #: in :meth:`list_models` so it's only needed if discovery is used.
        self._ctrl_client = ctrl_client
        #: Privacy filter — applied to every message list before cloud transmission.
        self._privacy_filter = PrivacyFilter()
        #: Organ 50: optional sink for the real per-call redaction audit.
        self._privacy_audit_tracker = privacy_audit_tracker
        if client is not None:
            self._client = client  # injected fake (tests)
        else:
            try:
                import boto3  # lazy: only required when Bedrock is actually used
            except ImportError as exc:  # pragma: no cover - environment-dependent
                raise LLMError(
                    "boto3 is required for AWS Bedrock; pip install boto3"
                ) from exc
            self._client = boto3.client("bedrock-runtime", region_name=region or None)

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """One non-streaming chat turn via Bedrock Converse.

        Returns the assistant message in the agent's shape
        (``role``/``content`` [+ ``tool_calls``]). Raises :class:`LLMError` on any
        Bedrock/credential failure so the agent surfaces a clean error event.

        Privacy: *messages* are filtered through :class:`PrivacyFilter` before
        transmission so sensitive content never leaves the local machine.
        """
        # --- Privacy: sanitize before any cloud transmission. ---
        safe_messages, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info(
                "Bedrock privacy filter applied",
                extra=audit,
            )
        if self._privacy_audit_tracker is not None:
            self._privacy_audit_tracker.record("bedrock", audit)

        system, converse_messages = _to_converse(safe_messages)
        output_tokens = self.max_tokens if max_tokens is None else max_tokens
        if output_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        kwargs: dict[str, Any] = {
            "modelId": model or self.model,
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": output_tokens,
                "temperature": self.temperature,
            },
        }
        if system:
            kwargs["system"] = system
        tool_config = _to_tool_config(tools)
        if tool_config:
            kwargs["toolConfig"] = tool_config

        try:
            response = self._client.converse(**kwargs)
        except Exception as exc:  # noqa: BLE001 - surface uniformly to the agent
            # --- Privacy: scrub credentials from the exception before logging. ---
            scrubbed = scrub_exception(exc)
            logger.warning(
                "Bedrock Converse failed for '%s': %s",
                model or self.model,
                scrubbed,
                exc_info=False,  # never dump raw traceback (may contain secrets)
            )
            raise LLMError(
                f"Bedrock Converse failed for '{model or self.model}': {scrubbed}"
            ) from exc

        message = (response.get("output") or {}).get("message") or {}
        if not isinstance(message, dict):
            return {"role": "assistant", "content": ""}

        result = _parse_output(message)
        # --- Validate response structure before returning to the agent. ---
        self._privacy_filter.validate_response(result)
        return result

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> Iterator[str]:
        """Yield text chunks from Bedrock ConverseStream.

        STREAM SEAM (C4): main.py no-tool chat paths may consume this.
        Privacy is identical to :meth:`chat`: sanitize before cloud transmission
        and scrub provider failures before surfacing them as :class:`LLMError`.
        """
        safe_messages, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info("Bedrock privacy filter applied", extra=audit)
        if self._privacy_audit_tracker is not None:
            self._privacy_audit_tracker.record("bedrock", audit)

        system, converse_messages = _to_converse(safe_messages)
        kwargs: dict[str, Any] = {
            "modelId": model or self.model,
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            },
        }
        if system:
            kwargs["system"] = system
        tool_config = _to_tool_config(tools)
        if tool_config:
            kwargs["toolConfig"] = tool_config

        try:
            response = self._client.converse_stream(**kwargs)
            yield from _stream_text_from_converse(response)
        except Exception as exc:  # noqa: BLE001 - surface uniformly to the agent
            scrubbed = scrub_exception(exc)
            logger.warning(
                "Bedrock ConverseStream failed for '%s': %s",
                model or self.model,
                scrubbed,
                exc_info=False,
            )
            raise LLMError(
                f"Bedrock ConverseStream failed for '{model or self.model}': {scrubbed}"
            ) from exc

    def stream_chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> Iterator[str | StreamFinished]:
        """Stream text chunks then a :class:`StreamFinished` with tool_calls.

        Same privacy/error contract as :meth:`stream_chat`, but the final
        yielded item is always a :class:`StreamFinished` carrying any tool_calls
        the model produced during the stream. This allows the tool loop to
        stream tokens in real-time while still processing tool_calls.
        """
        safe_messages, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info("Bedrock privacy filter applied", extra=audit)
        if self._privacy_audit_tracker is not None:
            self._privacy_audit_tracker.record("bedrock", audit)

        system, converse_messages = _to_converse(safe_messages)
        kwargs: dict[str, Any] = {
            "modelId": model or self.model,
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            },
        }
        if system:
            kwargs["system"] = system
        tool_config = _to_tool_config(tools)
        if tool_config:
            kwargs["toolConfig"] = tool_config

        try:
            response = self._client.converse_stream(**kwargs)
            yield from _stream_from_converse(response)
        except Exception as exc:  # noqa: BLE001 - surface uniformly to the agent
            scrubbed = scrub_exception(exc)
            logger.warning(
                "Bedrock stream_chat_with_tools failed for '%s': %s",
                model or self.model,
                scrubbed,
                exc_info=False,
            )
            raise LLMError(
                f"Bedrock stream_chat_with_tools failed for '{model or self.model}': {scrubbed}"
            ) from exc

    def list_models(self) -> list[dict[str, str]]:
        """List on-demand, text Bedrock models for this region (best-effort).

        Tries live control-plane discovery (``ListFoundationModels``, TEXT output,
        ON_DEMAND) so the picker can offer the models this account/region can
        actually invoke; falls back to :data:`CURATED_MODELS` when discovery is
        empty or unavailable (e.g. the API key lacks control-plane access). Either
        way the organism gets a RANGE of cloud models, never just the one default,
        and discovery failing never breaks the picker.
        """
        return self._discover_models() or list(CURATED_MODELS)

    def _discover_models(self) -> list[dict[str, str]]:
        ctrl = self._ctrl_client
        if ctrl is None:
            try:
                import boto3  # lazy

                ctrl = boto3.client("bedrock", region_name=self.region or None)
            except Exception as exc:  # noqa: BLE001 - discovery is best-effort
                logger.debug(
                    "Bedrock control-plane client creation failed: %s",
                    scrub_exception(exc),
                )
                return []
        try:
            resp = ctrl.list_foundation_models(
                byOutputModality="TEXT", byInferenceType="ON_DEMAND"
            )
        except Exception as exc:  # noqa: BLE001 - no control-plane access -> fall back
            logger.debug(
                "Bedrock list_foundation_models failed: %s", scrub_exception(exc)
            )
            return []

        seen: set[str] = set()
        out: list[dict[str, str]] = []
        for summary in resp.get("modelSummaries", []) or []:
            if not isinstance(summary, dict):
                continue
            mid = summary.get("modelId")
            if not mid or mid in seen:
                continue
            # Only models usable for a chat/agent turn (skip embeddings etc.).
            if "EMBEDDING" in (summary.get("outputModalities") or []):
                continue
            seen.add(mid)
            provider = str(summary.get("providerName") or "").strip()
            model_name = str(summary.get("modelName") or mid).strip()
            name = f"{provider} {model_name}".strip() if provider else model_name
            out.append({"id": str(mid), "name": name})
        out.sort(key=lambda m: m["name"].lower())
        return out
