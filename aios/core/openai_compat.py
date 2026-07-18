"""OpenAI-compatible chat client — a *cloud* ChatClient for the agentic loop.

Implements the same ``complete(prompt, *, system) -> str`` contract as
:class:`aios.core.llm.OllamaClient` and the same
``chat(messages, *, tools, model) -> message-dict`` contract as
:class:`aios.core.bedrock.BedrockClient` / :class:`aios.core.gemini.GeminiClient`,
backed by any **OpenAI-compatible** ``/chat/completions`` endpoint — OpenAI itself,
Groq, Together, a local vLLM server, or LM Studio. This gives the GAGOS another
cloud (or self-hosted) option alongside Bedrock/Gemini — *without* changing the
tool loop, memory, reflection, or the security gateway.

Design notes (mirrors ``bedrock.py``/``gemini.py`` so the providers stay symmetric):
  * ``urllib``/``json`` only — no ``openai`` package dependency, matching the
    stdlib-only pattern already used by :mod:`aios.core.llm`.
  * The agent speaks an Ollama-shaped message protocol (``role``/``content``
    [+ ``tool_calls``]; ``role: "tool"`` results) which is already extremely close
    to the OpenAI chat-completions shape — the main gap is that OpenAI's
    ``tool_calls``/``tool`` messages carry an explicit ``tool_call_id`` and stringify
    ``arguments`` as JSON text, so :func:`_to_openai_messages` fills those in.
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
from aios.core.llm import LLMError
from aios.core.privacy_filter import PrivacyFilter, scrub_exception

logger = logging.getLogger(__name__)


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert agent (Ollama-style) messages into OpenAI chat-completions messages.

    The two shapes are close (``role``/``content``); the differences bridged here:
      * an assistant's ``tool_calls`` get a synthesised ``id`` (if missing) and
        ``arguments`` stringified to JSON text (OpenAI requires a JSON *string*,
        Ollama's shape allows a dict);
      * a ``role: "tool"`` result is paired with the id of the call it answers
        (in order) via ``tool_call_id``, mirroring how ``_to_converse`` /
        ``_to_gemini`` pair tool activity for their respective APIs.
    """
    out: list[dict[str, Any]] = []
    pending_ids: list[str] = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role in ("system", "user"):
            out.append({"role": role, "content": str(content)})
        elif role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": str(content)}
            calls = msg.get("tool_calls") or []
            pending_ids = []
            if calls:
                tool_calls: list[dict[str, Any]] = []
                for i, call in enumerate(calls):
                    fn = call.get("function", {}) if isinstance(call, dict) else {}
                    tid = str(call.get("id") or f"call_{len(out)}_{i}")
                    pending_ids.append(tid)
                    args = fn.get("arguments")
                    if not isinstance(args, str):
                        args = json.dumps(args or {})
                    tool_calls.append(
                        {
                            "id": tid,
                            "type": "function",
                            "function": {
                                "name": str(fn.get("name", "")),
                                "arguments": args,
                            },
                        }
                    )
                entry["tool_calls"] = tool_calls
            out.append(entry)
        elif role == "tool":
            tid = pending_ids.pop(0) if pending_ids else f"call_orphan_{len(out)}"
            out.append({"role": "tool", "tool_call_id": tid, "content": str(content)})
    return out


def _parse_output(message: dict[str, Any]) -> dict[str, Any]:
    """Map an OpenAI chat-completions assistant message to the agent's shape.

    Converts each ``tool_calls[].function.arguments`` JSON string back to a dict
    (best-effort — falls back to ``{}`` on malformed JSON) so downstream tool
    dispatch always sees a dict, matching :func:`aios.core.bedrock._parse_output`
    and :func:`aios.core.gemini._parse_output`.
    """
    text = str(message.get("content") or "")
    tool_calls: list[dict[str, Any]] = []
    for call in message.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        fn = call.get("function", {}) or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args else {}
            except json.JSONDecodeError:
                args = {}
        tool_calls.append(
            {
                "id": call.get("id"),
                "function": {"name": fn.get("name", ""), "arguments": args or {}},
            }
        )
    result: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


class OpenAICompatClient:
    """:class:`~aios.agents.tool_agent.ChatClient` backed by an OpenAI-compatible API.

    Works against OpenAI itself and any drop-in-compatible endpoint (Groq,
    Together, vLLM, LM Studio, …) by pointing ``base_url`` elsewhere.
    """

    def __init__(
        self,
        *,
        api_key: str = config.OPENAI_API_KEY,
        base_url: str = config.OPENAI_BASE_URL,
        model: str = config.OPENAI_MODEL,
        max_tokens: int = config.OPENAI_MAX_TOKENS,
        timeout_s: int = config.LLM_REQUEST_TIMEOUT_S,
        temperature: float = config.LLM_TEMPERATURE,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.temperature = temperature
        #: Privacy filter — applied to every message list before cloud transmission.
        self._privacy_filter = PrivacyFilter()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
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
                f"OpenAI-compatible endpoint returned HTTP {exc.code} for model "
                f"'{payload.get('model', self.model)}': {scrubbed}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            scrubbed = scrub_exception(exc)
            raise LLMError(
                f"OpenAI-compatible request to {self.base_url} failed: {scrubbed}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"OpenAI-compatible endpoint returned a non-JSON response: {exc}"
            ) from exc

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        """Generate a single non-streaming completion from *prompt*.

        Raises:
            LLMError: On any transport, HTTP, or decoding failure.
        """
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        body = self._post(payload)
        choices = body.get("choices") or []
        if not choices:
            return ""
        message = (choices[0] or {}).get("message") or {}
        return str(message.get("content") or "")

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """One non-streaming chat turn via ``/chat/completions``.

        Returns the assistant message in the agent's shape
        (``role``/``content`` [+ ``tool_calls``]). Raises :class:`LLMError` on any
        transport/HTTP failure so the agent surfaces a clean error event.

        Privacy: *messages* are filtered through :class:`PrivacyFilter` before
        transmission so sensitive content never leaves the local machine.
        """
        safe_messages, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info("OpenAI-compatible privacy filter applied", extra=audit)

        output_tokens = self.max_tokens if max_tokens is None else max_tokens
        if output_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": _to_openai_messages(safe_messages),
            "temperature": self.temperature,
            "max_tokens": output_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        body = self._post(payload)
        choices = body.get("choices") or []
        if not choices:
            return {"role": "assistant", "content": ""}
        message = (choices[0] or {}).get("message") or {}
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
        """Yield text chunks from a streamed ``/chat/completions`` (SSE) call.

        STREAM SEAM (C4): main.py no-tool chat paths may consume this.
        Privacy is identical to :meth:`chat`: sanitize before cloud transmission
        and scrub provider failures before surfacing them as :class:`LLMError`.
        """
        safe_messages, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info("OpenAI-compatible privacy filter applied", extra=audit)

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": _to_openai_messages(safe_messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
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
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0] or {}).get("delta") or {}
                    piece = delta.get("content")
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
                f"OpenAI-compatible stream returned HTTP {exc.code} for model "
                f"'{model or self.model}': {scrubbed}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            scrubbed = scrub_exception(exc)
            raise LLMError(
                f"OpenAI-compatible stream to {self.base_url} failed: {scrubbed}"
            ) from exc
