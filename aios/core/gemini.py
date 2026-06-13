"""Google Gemini chat client — a *cloud* ChatClient for the agentic loop.

Implements the same ``chat(messages, *, tools, model) -> message-dict`` contract
as :class:`aios.core.llm.OllamaClient` and :class:`aios.core.bedrock.BedrockClient`,
backed by **Gemini via Vertex AI** (the ``google-genai`` SDK). This gives the
AI-OS a Google frontier model alongside local + Bedrock — *without* changing the
tool loop, memory, reflection, or the security gateway. The chosen model is still
only a proposer; the cage verifies regardless (RED stays hard-blocked).

Design notes (mirrors ``bedrock.py`` so the three providers stay symmetric):
  * ``google-genai`` is imported **lazily** (only when a real client is built),
    so the dependency is optional and the test suite — which injects a fake — never
    needs it or a network call.
  * **Auth is the laptop's ``gcloud`` Application Default Credentials (ADC)** via
    Vertex AI (``genai.Client(vertexai=True, project=…, location=…)``). No key is
    read from or written to disk in the repo (no-secret-persistence).
  * The agent speaks an Ollama-shaped protocol (``tool_calls`` without ids;
    ``role: "tool"`` results). Gemini is function-call-shaped: ``contents`` with
    ``role: "user"|"model"`` and ``function_call`` / ``function_response`` parts,
    paired by function *name*. :func:`_to_gemini` bridges the two (synthesising the
    pairing the way :func:`aios.core.bedrock._to_converse` pairs by tool id).
  * Message structures are built as **plain dicts** matching the google-genai
    ``Content`` schema, which the SDK coerces — so the conversion is fully unit
    testable with a fake client and no SDK types.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from aios import config
from aios.core.llm import LLMError

#: Well-known Gemini chat models, used as the picker fallback when live discovery
#: returns nothing (Vertex discovery is best-effort / permission-dependent). These
#: ids are stable; the operator can still type any model id the project can serve.
CURATED_MODELS: list[dict[str, str]] = [
    {"id": "gemini-2.5-pro", "name": "Google Gemini 2.5 Pro"},
    {"id": "gemini-2.5-flash", "name": "Google Gemini 2.5 Flash"},
    {"id": "gemini-2.0-flash", "name": "Google Gemini 2.0 Flash"},
]


def _to_gemini(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Convert agent (Ollama-style) messages into ``(system_text, contents)``.

    Gemini takes the system prompt separately (``system_instruction``) and
    represents tool activity as ``function_call`` (model) / ``function_response``
    (user) parts paired by the function *name*. The agent's messages carry no tool
    ids, so we remember the names from each assistant's ``tool_calls`` and pair the
    following ``role: "tool"`` results to them in order.
    """
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    pending_names: list[str] = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            if str(content).strip():
                system_parts.append(str(content))
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": str(content)}]})
        elif role == "assistant":
            parts: list[dict[str, Any]] = []
            text = str(content).strip()
            if text:
                parts.append({"text": text})
            pending_names = []
            for call in msg.get("tool_calls") or []:
                fn = call.get("function", {}) if isinstance(call, dict) else {}
                name = str(fn.get("name", ""))
                pending_names.append(name)
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                parts.append({"function_call": {"name": name, "args": args or {}}})
            if not parts:
                parts.append({"text": ""})  # Gemini rejects empty content
            contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            name = pending_names.pop(0) if pending_names else "tool"
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {"function_response": {"name": name, "response": {"result": str(content)}}}
                    ],
                }
            )
    return "\n\n".join(system_parts), contents


def _to_tools(tools: Optional[list[dict[str, Any]]]) -> Optional[list[dict[str, Any]]]:
    """Map OpenAI-style function specs to a Gemini ``tools`` list (or ``None``).

    A single ``Tool`` with one ``function_declaration`` per agent tool; the
    parameters JSON-schema is passed through (Gemini accepts the OpenAPI subset).
    """
    if not tools:
        return None
    decls: list[dict[str, Any]] = []
    for tool in tools:
        fn = tool.get("function", {}) if isinstance(tool, dict) else {}
        decls.append(
            {
                "name": str(fn.get("name", "")),
                "description": str(fn.get("description", "")),
                "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return [{"function_declarations": decls}]


def _coerce_args(raw: Any) -> dict[str, Any]:
    """Best-effort coerce Gemini ``function_call.args`` (proto map/dict) to a dict."""
    if not raw:
        return {}
    try:
        return dict(raw)
    except (TypeError, ValueError):
        return {}


def _parse_output(response: Any) -> dict[str, Any]:
    """Map a Gemini response back to the agent's Ollama-style assistant message.

    Tolerant of both real google-genai objects (attribute access) and the test
    fakes that mimic their shape — reads ``candidates[0].content.parts`` and pulls
    ``text`` / ``function_call`` from each part.
    """
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return {"role": "assistant", "content": ""}
    content = getattr(candidates[0], "content", None)
    parts = (getattr(content, "parts", None) or []) if content is not None else []

    text = ""
    tool_calls: list[dict[str, Any]] = []
    for part in parts:
        chunk = getattr(part, "text", None)
        if chunk:
            text += str(chunk)
        fc = getattr(part, "function_call", None)
        if fc is not None and getattr(fc, "name", None):
            tool_calls.append(
                {
                    "id": None,
                    "function": {"name": str(fc.name), "arguments": _coerce_args(getattr(fc, "args", None))},
                }
            )
    result: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


class GeminiClient:
    """:class:`~aios.agents.tool_agent.ChatClient` backed by Gemini (Vertex AI)."""

    def __init__(
        self,
        *,
        model: str = config.GEMINI_MODEL,
        project: str = config.GEMINI_PROJECT,
        location: str = config.GEMINI_LOCATION,
        max_tokens: int = config.GEMINI_MAX_TOKENS,
        temperature: float = config.LLM_TEMPERATURE,
        thinking_budget: int = config.GEMINI_THINKING_BUDGET,
        client: Optional[Any] = None,
    ) -> None:
        self.model = model
        self.project = project
        self.location = location
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.thinking_budget = thinking_budget
        if client is not None:
            self._client = client  # injected fake (tests)
        else:
            try:
                from google import genai  # lazy: only required when Gemini is used
            except ImportError as exc:  # pragma: no cover - environment-dependent
                raise LLMError(
                    "google-genai is required for Google Gemini; pip install google-genai"
                ) from exc
            # Vertex AI + ADC: credentials come from `gcloud auth application-default
            # login`; nothing secret is passed here or persisted.
            self._client = genai.Client(
                vertexai=True, project=project or None, location=location or None
            )

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """One non-streaming chat turn via Gemini ``generate_content``.

        Returns the assistant message in the agent's shape
        (``role``/``content`` [+ ``tool_calls``]). Raises :class:`LLMError` on any
        Gemini/credential failure so the agent surfaces a clean error event.
        """
        system_text, contents = _to_gemini(messages)
        gen_config: dict[str, Any] = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
        }
        if system_text.strip():
            gen_config["system_instruction"] = system_text
        # Bound 2.5-era "thinking" so it can't silently eat the output budget and
        # return zero text (``0`` disables it; ``-1`` leaves the model default on).
        if self.thinking_budget >= 0:
            gen_config["thinking_config"] = {"thinking_budget": self.thinking_budget}
        tool_decls = _to_tools(tools)
        if tool_decls:
            gen_config["tools"] = tool_decls

        try:
            response = self._client.models.generate_content(
                model=model or self.model,
                contents=contents,
                config=gen_config,
            )
        except Exception as exc:  # noqa: BLE001 - surface uniformly to the agent
            raise LLMError(
                f"Gemini generate_content failed for '{model or self.model}': {exc}"
            ) from exc

        return _parse_output(response)

    def list_models(self) -> list[dict[str, str]]:
        """List invocable Gemini chat models for the picker (best-effort).

        Tries live Vertex discovery (``client.models.list()``), keeping only
        ``gemini*`` generate-capable ids; falls back to :data:`CURATED_MODELS` when
        discovery is empty or unavailable (it is permission/SDK-version dependent),
        so the picker always has the well-known Gemini models to offer.
        """
        discovered = self._discover_models()
        return discovered or list(CURATED_MODELS)

    def _discover_models(self) -> list[dict[str, str]]:
        try:
            raw = self._client.models.list()
        except Exception:  # noqa: BLE001 - discovery is best-effort
            return []
        seen: set[str] = set()
        out: list[dict[str, str]] = []
        for m in raw or []:
            name = getattr(m, "name", None)
            if name is None and isinstance(m, dict):
                name = m.get("name")
            if not name:
                continue
            mid = str(name).split("/")[-1]  # 'publishers/google/models/x' -> 'x'
            if "gemini" not in mid.lower() or mid in seen:
                continue
            seen.add(mid)
            display = getattr(m, "display_name", None) or f"Google {mid}"
            out.append({"id": mid, "name": str(display)})
        out.sort(key=lambda x: x["name"].lower())
        return out
