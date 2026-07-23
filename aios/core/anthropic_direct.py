"""Anthropic Messages API client — a *cloud* ChatClient for the agentic loop.

Implements the same ``complete(prompt, *, system) -> str`` contract as
:class:`aios.core.llm.OllamaClient` and the same
``chat(messages, *, tools, model) -> message-dict`` contract as
:class:`aios.core.bedrock.BedrockClient` / :class:`aios.core.gemini.GeminiClient`,
but talks **directly** to Anthropic's own Messages API (``api.anthropic.com``)
rather than through Bedrock. Useful when the operator has a direct Anthropic key
(no AWS account) or wants the latest Claude models before they land on Bedrock.

Design notes (mirrors ``bedrock.py`` closely — Anthropic's own Messages API and
Bedrock Converse both speak the same "Claude" content-block shape):
  * ``urllib``/``json`` only — no ``anthropic`` package dependency, matching the
    stdlib-only pattern already used by :mod:`aios.core.llm` /
    :mod:`aios.core.bedrock`.
  * The agent speaks an Ollama-shaped message protocol (``tool_calls`` with no
    ids; ``role: "tool"`` results). The Messages API is content-block shaped:
    system is a **separate top-level string**, and tool activity is
    ``tool_use`` (assistant content block) / ``tool_result`` (user content
    block) paired by id — the same pairing problem :func:`aios.core.bedrock._to_converse`
    solves for Converse. :func:`_to_anthropic_messages` bridges the two,
    synthesising ids and pairing each tool result with its preceding call.
  * **Privacy**: every message list is passed through :class:`PrivacyFilter`
    before transmission so conversation history, tool results, and secrets never
    leave the local machine unredacted.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Iterator, Optional

from aios import config
from aios.application.models.privacy_audit import PrivacyAuditTracker
from aios.core.llm import LLMError
from aios.core.privacy_filter import PrivacyFilter, scrub_exception

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


def _to_anthropic_messages(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Convert agent (Ollama-style) messages into ``(system_text, anthropic_messages)``.

    The Messages API takes the system prompt as a separate top-level string and
    represents tool activity as ``tool_use`` (assistant content block) /
    ``tool_result`` (user content block) paired by id. The agent's messages carry
    no ids, so we mint one per call and pair the following ``role: "tool"``
    results to them in order — the same scheme as
    :func:`aios.core.bedrock._to_converse`.
    """
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []
    pending_ids: list[str] = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            if str(content).strip():
                system_parts.append(str(content))
        elif role == "user":
            out.append(
                {"role": "user", "content": [{"type": "text", "text": str(content)}]}
            )
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            text = str(content).strip()
            if text:
                blocks.append({"type": "text", "text": text})
            pending_ids = []
            for i, call in enumerate(msg.get("tool_calls") or []):
                fn = call.get("function", {}) if isinstance(call, dict) else {}
                tid = str(call.get("id") or f"toolu_{len(out)}_{i}")
                pending_ids.append(tid)
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tid,
                        "name": str(fn.get("name", "")),
                        "input": args or {},
                    }
                )
            if not blocks:
                blocks.append({"type": "text", "text": ""})  # API rejects empty content
            out.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            tid = pending_ids.pop(0) if pending_ids else f"toolu_orphan_{len(out)}"
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tid,
                            "content": str(content),
                        }
                    ],
                }
            )
    return "\n\n".join(system_parts), out


def _to_tools(tools: Optional[list[dict[str, Any]]]) -> Optional[list[dict[str, Any]]]:
    """Map OpenAI-style function specs to Anthropic ``tools`` (or ``None``)."""
    if not tools:
        return None
    specs: list[dict[str, Any]] = []
    for tool in tools:
        fn = tool.get("function", {}) if isinstance(tool, dict) else {}
        specs.append(
            {
                "name": str(fn.get("name", "")),
                "description": str(fn.get("description", "")),
                "input_schema": fn.get("parameters")
                or {"type": "object", "properties": {}},
            }
        )
    return specs


def _parse_output(body: dict[str, Any]) -> dict[str, Any]:
    """Map a Messages API response back to the agent's Ollama-style message dict."""
    text = ""
    tool_calls: list[dict[str, Any]] = []
    for block in body.get("content", []) or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text += str(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id"),
                    "function": {
                        "name": str(block.get("name", "")),
                        "arguments": block.get("input") or {},
                    },
                }
            )
    result: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


class AnthropicDirectClient:
    """:class:`~aios.agents.tool_agent.ChatClient` backed by Anthropic's Messages API."""

    def __init__(
        self,
        *,
        api_key: str = config.ANTHROPIC_API_KEY,
        model: str = config.ANTHROPIC_MODEL,
        max_tokens: int = config.ANTHROPIC_MAX_TOKENS,
        timeout_s: int = config.LLM_REQUEST_TIMEOUT_S,
        temperature: float = config.LLM_TEMPERATURE,
        privacy_audit_tracker: Optional[PrivacyAuditTracker] = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.temperature = temperature
        #: Privacy filter — applied to every message list before cloud transmission.
        self._privacy_filter = PrivacyFilter()
        #: Organ 50: optional sink for the real per-call redaction audit.
        self._privacy_audit_tracker = privacy_audit_tracker

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            _API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()
            except Exception:  # noqa: BLE001 - best-effort detail extraction
                detail = ""
            scrubbed = scrub_exception(detail or exc.reason)
            raise LLMError(
                f"Anthropic Messages API returned HTTP {exc.code} for model "
                f"'{payload.get('model', self.model)}': {scrubbed}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            scrubbed = scrub_exception(exc)
            raise LLMError(
                f"Anthropic Messages API request failed: {scrubbed}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Anthropic Messages API returned a non-JSON response: {exc}"
            ) from exc

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        """Generate a single non-streaming completion from *prompt*.

        Raises:
            LLMError: On any transport, HTTP, or decoding failure.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ],
        }
        if system:
            payload["system"] = system

        body = self._post(payload)
        text = ""
        for block in body.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text += str(block.get("text", ""))
        return text

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """One non-streaming chat turn via the Messages API.

        Returns the assistant message in the agent's shape
        (``role``/``content`` [+ ``tool_calls``]). Raises :class:`LLMError` on any
        transport/HTTP failure so the agent surfaces a clean error event.

        Privacy: *messages* are filtered through :class:`PrivacyFilter` before
        transmission so sensitive content never leaves the local machine.
        """
        safe_messages, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info("Anthropic privacy filter applied", extra=audit)
        if self._privacy_audit_tracker is not None:
            self._privacy_audit_tracker.record("anthropic", audit)

        system_text, anthropic_messages = _to_anthropic_messages(safe_messages)
        output_tokens = self.max_tokens if max_tokens is None else max_tokens
        if output_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        payload: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": output_tokens,
            "temperature": self.temperature,
            "messages": anthropic_messages,
        }
        if system_text.strip():
            payload["system"] = system_text
        tool_specs = _to_tools(tools)
        if tool_specs:
            payload["tools"] = tool_specs

        body = self._post(payload)
        result = _parse_output(body)
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
        """Yield text chunks from a streamed Messages API call (SSE).

        STREAM SEAM (C4): main.py no-tool chat paths may consume this.
        Privacy is identical to :meth:`chat`: sanitize before cloud transmission
        and scrub provider failures before surfacing them as :class:`LLMError`.
        """
        safe_messages, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info("Anthropic privacy filter applied", extra=audit)
        if self._privacy_audit_tracker is not None:
            self._privacy_audit_tracker.record("anthropic", audit)

        system_text, anthropic_messages = _to_anthropic_messages(safe_messages)
        payload: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": anthropic_messages,
            "stream": True,
        }
        if system_text.strip():
            payload["system"] = system_text
        tool_specs = _to_tools(tools)
        if tool_specs:
            payload["tools"] = tool_specs

        request = urllib.request.Request(
            _API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", "replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") != "content_block_delta":
                        continue
                    delta = event.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        piece = delta.get("text")
                        if piece:
                            yield str(piece)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()
            except Exception:  # noqa: BLE001 - best-effort detail extraction
                detail = ""
            scrubbed = scrub_exception(detail or exc.reason)
            raise LLMError(
                f"Anthropic Messages API stream returned HTTP {exc.code} for model "
                f"'{model or self.model}': {scrubbed}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            scrubbed = scrub_exception(exc)
            raise LLMError(f"Anthropic Messages API stream failed: {scrubbed}") from exc
