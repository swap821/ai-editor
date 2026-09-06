"""Google Gemini chat client — a *cloud* ChatClient for the agentic loop.

Implements the same ``chat(messages, *, tools, model) -> message-dict`` contract
as :class:`aios.core.llm.OllamaClient` and :class:`aios.core.bedrock.BedrockClient`,
backed by **Gemini via Vertex AI** (the ``google-genai`` SDK). This gives the
GAGOS a Google frontier model alongside local + Bedrock — *without* changing the
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
  * **Privacy**: every message list is passed through :class:`PrivacyFilter`
    before transmission so conversation history, tool results, and secrets never
    leave the local machine unredacted.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Iterator, Optional

from aios import config
from aios.application.models.privacy_audit import PrivacyAuditTracker
from aios.core.llm import LLMError
from aios.core.privacy_filter import PrivacyFilter, scrub_exception
from aios.core.provider_retry import call_with_backoff, stream_with_backoff
from aios.core.stream_protocol import StreamFinished

logger = logging.getLogger(__name__)

#: Well-known Gemini chat models, used as the picker fallback when live discovery
#: returns nothing (Vertex discovery is best-effort / permission-dependent). These
#: ids are stable; the operator can still type any model id the project can serve.
CURATED_MODELS: list[dict[str, str]] = [
    # Verified by INVOKING each id on 2026-08-18, not by reading the publisher
    # listing -- the listing shows the catalogue, not what a project may call.
    #
    # REGION MATTERS, and silently: every gemini-3.x id below returns 404
    # NOT_FOUND in `us-central1` and 200 in `global`. AIOS_GEMINI_LOCATION
    # defaults to us-central1, so a 3.x model looks like it "does not exist"
    # when it is only in the wrong region. That cost a full golden cohort
    # (0/5, every step unverified) before the 404 body was read. Set
    # AIOS_GEMINI_LOCATION=global to use anything in the 3.x line.
    #
    # The default is deliberately NOT changed here: `global` routes the request
    # without a region guarantee, which is a data-residency decision for the
    # operator to make, not a convenience default to flip on their behalf.
    #
    # The 3.x line is flash-led: there is a 3.6-flash and a 3.7-flash but no
    # matching pro, so the newest *pro* is 3.1-pro-preview (3-pro-preview 404s
    # in both regions). Ordered newest-first so the picker's default stops being
    # the oldest option -- organ 44 measured eight cohorts on 2.5-pro while four
    # newer models were already callable.
    # Added 2026-09-06 to this list's own standard: INVOKED on the operator's
    # project (location=global) and answered 200/STOP, not merely listed. It is
    # present in the model-garden catalogue as google/gemini-3.8-flash@default.
    #
    # `gemini-3.8-flash-cyber` is deliberately ABSENT. It exists, but it is
    # gated behind Google's Fairwind programme (vetted security researchers,
    # governments, critical-infrastructure operators) and appears in ZERO of
    # the 640 model-garden entries this project can see. Listing an id nobody
    # here can call is exactly the catalogue-vs-callable confusion the header
    # above warns about.
    {"id": "gemini-3.8-flash", "name": "Google Gemini 3.8 Flash"},
    {"id": "gemini-3.7-flash", "name": "Google Gemini 3.7 Flash"},
    {"id": "gemini-3.6-flash", "name": "Google Gemini 3.6 Flash"},
    {"id": "gemini-3.5-flash", "name": "Google Gemini 3.5 Flash"},
    {"id": "gemini-3.1-pro-preview", "name": "Google Gemini 3.1 Pro (preview)"},
    {"id": "gemini-3-pro-preview", "name": "Google Gemini 3 Pro (preview)"},
    {"id": "gemini-2.5-pro", "name": "Google Gemini 2.5 Pro"},
    {"id": "gemini-2.5-flash", "name": "Google Gemini 2.5 Flash"},
    {"id": "gemini-2.0-flash", "name": "Google Gemini 2.0 Flash"},
]


#: Sent in place of a tool result when a function_call was never answered --
#: refused at the approval gate, blocked by the security gateway, or the turn
#: ended first. Factual, not instructive: the transport layer must not inject
#: guidance into a measured run.
_UNANSWERED_CALL_RESULT = (
    "No result: this tool call was not executed (refused, blocked, or the turn "
    "ended before it produced output)."
)


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

    index = 0
    while index < len(messages):
        msg = messages[index]
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            if str(content).strip():
                system_parts.append(str(content))
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": str(content)}]})
        elif role == "tool":
            # An orphan result with no preceding call. Kept rather than dropped
            # so nothing the agent observed disappears from the transcript.
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": "tool",
                                "response": {"result": str(content)},
                            }
                        }
                    ],
                }
            )
        elif role == "assistant":
            parts: list[dict[str, Any]] = []
            text = str(content).strip()
            if text:
                parts.append({"text": text})
            call_names: list[str] = []
            for call in msg.get("tool_calls") or []:
                fn = call.get("function", {}) if isinstance(call, dict) else {}
                name = str(fn.get("name", ""))
                call_names.append(name)
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                fc_part: dict[str, Any] = {
                    "function_call": {"name": name, "args": args or {}}
                }
                # Gemini 3.x rejects a replayed function_call whose
                # thought_signature is missing; 2.5 never sends one, so this is
                # emitted only when the model actually gave us one.
                signature = (
                    call.get("thought_signature") if isinstance(call, dict) else None
                )
                if signature:
                    fc_part["thought_signature"] = _decode_signature(signature)
                parts.append(fc_part)
            if not parts:
                parts.append({"text": ""})  # Gemini rejects empty content
            contents.append({"role": "model", "parts": parts})

            if call_names:
                # EVERY function_call must be answered, in ONE turn.
                #
                # Gemini validates the count: "the number of function response
                # parts is equal to the number of function call parts of the
                # function call turn". Two ways the old converter broke that,
                # both measured in a golden-mission cohort on 2026-09-02:
                #
                #  * a refused tool call produced no `role: "tool"` message at
                #    all, so its call went unanswered. That is not an edge case
                #    here -- refusing a YELLOW action is the supervision
                #    mechanism, so any approval-gated mission could hit it.
                #  * multiple results were emitted as separate user turns, so
                #    the answers were spread across turns instead of answering
                #    the call turn.
                #
                # Unanswered calls get a truthful placeholder rather than being
                # dropped: the model is told the call produced no result, which
                # is what actually happened. Deliberately factual and not
                # instructive -- a measured run must not have guidance smuggled
                # into it by the transport layer.
                results: list[str] = []
                lookahead = index + 1
                while (
                    lookahead < len(messages)
                    and messages[lookahead].get("role") == "tool"
                    and len(results) < len(call_names)
                ):
                    results.append(str(messages[lookahead].get("content") or ""))
                    lookahead += 1

                response_parts = [
                    {
                        "function_response": {
                            "name": name,
                            "response": {
                                "result": results[position]
                                if position < len(results)
                                else _UNANSWERED_CALL_RESULT
                            },
                        }
                    }
                    for position, name in enumerate(call_names)
                ]
                contents.append({"role": "user", "parts": response_parts})
                index = lookahead
                continue
        index += 1

    # Gemini 3.x: "Requests ending with a model turn are not supported." 2.5
    # accepted it, so the agent loop has always been able to reach chat() with
    # its own last turn at the end -- a blocked or refused tool call appends the
    # assistant message with no matching tool result, and the next request then
    # ends on `model`. That is a 400 on 3.x, and it killed four of five golden
    # missions after the earlier adapter fixes had already landed.
    #
    # Normalised here rather than in the loop: this is one provider transport
    # requirement and the agent should not have to know about it. The appended
    # turn is a neutral continuation, not new instruction -- it must not smuggle
    # guidance into a measured run.
    if contents and contents[-1].get("role") == "model":
        contents.append({"role": "user", "parts": [{"text": "Continue."}]})

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
                "parameters": fn.get("parameters")
                or {"type": "object", "properties": {}},
            }
        )
    return [{"function_declarations": decls}]


def _decode_signature(signature: Any) -> Any:
    """base64 text -> bytes for the wire; anything else passes through."""
    if isinstance(signature, str):
        try:
            return base64.b64decode(signature.encode("ascii"), validate=True)
        except Exception:  # noqa: BLE001 - a non-base64 value is sent as-is
            return signature
    return signature


def _tool_call_from_part(part: Any, fc: Any) -> dict[str, Any]:
    """Build one tool-call dict, carrying Gemini 3.x's ``thought_signature``.

    Gemini 3.x returns an opaque ``thought_signature`` on the *part* that holds
    a ``function_call``, and REQUIRES it back when that call is replayed in the
    conversation history. Dropping it is not a degradation, it is a hard 400:

        Function call is missing a thought_signature in functionCall parts.
        This is required for tools to work correctly.

    The first tool call therefore succeeds and the next request fails, which is
    why every golden mission on gemini-3.7-flash died ~35s in with every step
    unverified. 2.5 does not send the field, so this is invisible until a 3.x
    model is selected -- and the region default (us-central1) meant no 3.x
    model could be selected at all. Two defaults hid one protocol change.

    The signature rides on the tool-call dict, which ``ToolAgent`` stores
    verbatim in the conversation, so it survives the round trip without the
    agent needing to know it exists.
    """
    call: dict[str, Any] = {
        "id": None,
        "function": {
            "name": str(fc.name),
            "arguments": _coerce_args(getattr(fc, "args", None)),
        },
    }
    signature = getattr(part, "thought_signature", None)
    if signature:
        # base64 TEXT, not the raw bytes the SDK hands back. This dict is stored
        # in the agent conversation, which is streamed, audited and serialised;
        # raw bytes there raise "Object of type bytes is not JSON serializable"
        # and kill the turn just as dead as the 400 this field exists to avoid.
        # Decoded back to bytes at the API boundary in ``_to_gemini``.
        call["thought_signature"] = (
            base64.b64encode(signature).decode("ascii")
            if isinstance(signature, (bytes, bytearray))
            else str(signature)
        )
    return call


def _coerce_args(raw: Any) -> dict[str, Any]:
    """Best-effort coerce Gemini ``function_call.args`` (proto map/dict) to a dict."""
    if not raw:
        return {}
    try:
        return dict(raw)
    except (TypeError, ValueError):
        return {}


def _warn_if_truncated(candidate: Any, response: Any) -> None:
    """Log when the model was cut off, instead of returning silence.

    `finish_reason` was checked NOWHERE in this codebase, so a response cut off
    at `max_output_tokens` arrived downstream as an ordinary short answer -- or,
    when thinking consumed the whole budget, as nothing at all.

    That silence is what made the underlying defect expensive: organ 44's golden
    cohort recorded turns that "did nothing", and four hypotheses were tested and
    rejected before the live API was asked directly and answered
    `finish_reason=MAX_TOKENS, thoughts=980, output=39`.

    Best-effort only: a malformed or faked response must never break a chat
    call, so every read is guarded and nothing here can raise.
    """
    try:
        reason = str(getattr(candidate, "finish_reason", "") or "")
        if "MAX_TOKENS" not in reason.upper():
            return
        usage = getattr(response, "usage_metadata", None)
        logger.warning(
            "gemini_response_truncated",
            extra={
                "finish_reason": reason,
                "thinking_tokens": getattr(usage, "thoughts_token_count", None),
                "output_tokens": getattr(usage, "candidates_token_count", None),
                "hint": (
                    "raise AIOS_GEMINI_MAX_TOKENS -- on Gemini 2.5 the output "
                    "budget covers thinking AND visible output, and 2.5-pro "
                    "cannot disable thinking"
                ),
            },
        )
    except Exception:  # noqa: BLE001 - diagnostics must never break a call
        return


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
    _warn_if_truncated(candidates[0], response)

    text = ""
    tool_calls: list[dict[str, Any]] = []
    for part in parts:
        chunk = getattr(part, "text", None)
        if chunk:
            text += str(chunk)
        fc = getattr(part, "function_call", None)
        if fc is not None and getattr(fc, "name", None):
            tool_calls.append(_tool_call_from_part(part, fc))
    result: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def _stream_text_from_gemini(chunks: Any) -> Iterator[str]:
    """Yield text chunks from a Gemini ``generate_content_stream`` iterable."""
    for chunk in chunks or []:
        text = getattr(chunk, "text", None)
        if text:
            yield str(text)
            continue
        parsed = _parse_output(chunk)
        content = parsed.get("content")
        if content:
            yield str(content)


def _stream_from_gemini(chunks: Any) -> Iterator[str | StreamFinished]:
    """Yield text deltas then a :class:`StreamFinished` with any tool_calls.

    Each streaming chunk may contain text parts or function_call parts. Text
    is yielded immediately; function_calls are accumulated and returned in the
    final :class:`StreamFinished`.
    """
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for chunk in chunks or []:
        # NOTE: no `continue` after emitting text.
        #
        # This used to short-circuit the moment `chunk.text` was truthy, which
        # silently DROPPED any function_call riding in the same chunk -- Gemini
        # is free to put prose and a tool call in one chunk, and `.text`
        # concatenates only the text parts (the SDK even warns: "there are
        # non-text parts in the response: ['function_call'], returning
        # concatenated text result from text parts").
        #
        # The result was a turn that appeared to answer while never calling the
        # tool it had asked for. Falling through to the parts loop below costs
        # nothing -- it re-reads the same text guarded by `if t` -- and the
        # `seen_text` flag keeps that text from being emitted twice.
        text = getattr(chunk, "text", None)
        seen_text = False
        if text:
            text_parts.append(str(text))
            yield str(text)
            seen_text = True
        # Parse full chunk for both text and function_calls
        candidates = getattr(chunk, "candidates", None) or []
        if not candidates:
            continue
        content = getattr(candidates[0], "content", None)
        parts = (getattr(content, "parts", None) or []) if content is not None else []
        for part in parts:
            t = getattr(part, "text", None)
            if t and not seen_text:
                text_parts.append(str(t))
                yield str(t)
            fc = getattr(part, "function_call", None)
            if fc is not None and getattr(fc, "name", None):
                tool_calls.append(_tool_call_from_part(part, fc))

    yield StreamFinished(tool_calls=tool_calls, content="".join(text_parts))


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
        privacy_audit_tracker: Optional[PrivacyAuditTracker] = None,
    ) -> None:
        self.model = model
        self.project = project
        self.location = location
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.thinking_budget = thinking_budget
        #: Privacy filter — applied to every message list before cloud transmission.
        self._privacy_filter = PrivacyFilter()
        #: Organ 50: optional sink for the real per-call redaction audit
        #: (never constructed here -- a lookup failure must never break a
        #: chat call, so the caller supplies it or it stays None).
        self._privacy_audit_tracker = privacy_audit_tracker
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
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """One non-streaming chat turn via Gemini ``generate_content``.

        Returns the assistant message in the agent's shape
        (``role``/``content`` [+ ``tool_calls``]). Raises :class:`LLMError` on any
        Gemini/credential failure so the agent surfaces a clean error event.

        Privacy: *messages* are filtered through :class:`PrivacyFilter` before
        transmission so sensitive content never leaves the local machine.
        """
        # --- Privacy: sanitize before any cloud transmission. ---
        safe_messages, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info(
                "Gemini privacy filter applied",
                extra=audit,
            )
        if self._privacy_audit_tracker is not None:
            self._privacy_audit_tracker.record("gemini", audit)

        system_text, contents = _to_gemini(safe_messages)
        output_tokens = self.max_tokens if max_tokens is None else max_tokens
        if output_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        gen_config: dict[str, Any] = {
            "temperature": self.temperature,
            "max_output_tokens": output_tokens,
        }
        if system_text.strip():
            gen_config["system_instruction"] = system_text
        # A positive value bounds 2.5-era "thinking".  Vertex rejects an explicit
        # zero for some discovered models, so zero and negative values leave the
        # provider default untouched.
        if self.thinking_budget > 0:
            gen_config["thinking_config"] = {"thinking_budget": self.thinking_budget}
        tool_decls = _to_tools(tools)
        if tool_decls:
            gen_config["tools"] = tool_decls

        try:
            response = call_with_backoff(
                lambda: self._client.models.generate_content(
                    model=model or self.model,
                    contents=contents,
                    config=gen_config,
                ),
                on_retry=lambda n, exc, d: logger.warning(
                    "Gemini transient failure (attempt %s), retrying in %.1fs: %s",
                    n,
                    d,
                    scrub_exception(exc),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - surface uniformly to the agent
            # --- Privacy: scrub credentials from the exception before logging. ---
            scrubbed = scrub_exception(exc)
            logger.warning(
                "Gemini generate_content failed for '%s': %s",
                model or self.model,
                scrubbed,
                exc_info=False,  # never dump raw traceback (may contain secrets)
            )
            raise LLMError(
                f"Gemini generate_content failed for '{model or self.model}': {scrubbed}"
            ) from exc

        result = _parse_output(response)
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
        """Yield text chunks from Gemini ``generate_content_stream``.

        STREAM SEAM (C4): main.py no-tool chat paths may consume this.
        Privacy is identical to :meth:`chat`: sanitize before cloud transmission
        and scrub provider failures before surfacing them as :class:`LLMError`.
        """
        safe_messages, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info("Gemini privacy filter applied", extra=audit)
        if self._privacy_audit_tracker is not None:
            self._privacy_audit_tracker.record("gemini", audit)

        system_text, contents = _to_gemini(safe_messages)
        gen_config: dict[str, Any] = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
        }
        if system_text.strip():
            gen_config["system_instruction"] = system_text
        if self.thinking_budget > 0:
            gen_config["thinking_config"] = {"thinking_budget": self.thinking_budget}
        tool_decls = _to_tools(tools)
        if tool_decls:
            gen_config["tools"] = tool_decls

        try:
            # generate_content_stream is LAZY -- it issues no request until
            # iterated -- so retry must wrap CONSUMPTION, not creation, and is
            # bounded by emission: safe to re-issue while no chunk has escaped.
            yield from stream_with_backoff(
                lambda: _stream_text_from_gemini(
                    self._client.models.generate_content_stream(
                        model=model or self.model,
                        contents=contents,
                        config=gen_config,
                    )
                ),
                on_retry=lambda n, exc, d: logger.warning(
                    "Gemini transient stream failure (attempt %s), retrying in %.1fs: %s",
                    n,
                    d,
                    scrub_exception(exc),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - surface uniformly to the agent
            scrubbed = scrub_exception(exc)
            logger.warning(
                "Gemini generate_content_stream failed for '%s': %s",
                model or self.model,
                scrubbed,
                exc_info=False,
            )
            raise LLMError(
                f"Gemini generate_content_stream failed for '{model or self.model}': {scrubbed}"
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
        the model produced during the stream.
        """
        safe_messages, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info("Gemini privacy filter applied", extra=audit)
        if self._privacy_audit_tracker is not None:
            self._privacy_audit_tracker.record("gemini", audit)

        system_text, contents = _to_gemini(safe_messages)
        gen_config: dict[str, Any] = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
        }
        if system_text.strip():
            gen_config["system_instruction"] = system_text
        if self.thinking_budget > 0:
            gen_config["thinking_config"] = {"thinking_budget": self.thinking_budget}
        tool_decls = _to_tools(tools)
        if tool_decls:
            gen_config["tools"] = tool_decls

        try:
            # Lazy stream: retry wraps CONSUMPTION, bounded by emission. This
            # is the path that lost a golden-mission run to a 429 on
            # 2026-09-02 while a creation-only wrapper watched it go past.
            yield from stream_with_backoff(
                lambda: _stream_from_gemini(
                    self._client.models.generate_content_stream(
                        model=model or self.model,
                        contents=contents,
                        config=gen_config,
                    )
                ),
                on_retry=lambda n, exc, d: logger.warning(
                    "Gemini transient stream failure (attempt %s), retrying in %.1fs: %s",
                    n,
                    d,
                    scrub_exception(exc),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - surface uniformly to the agent
            scrubbed = scrub_exception(exc)
            logger.warning(
                "Gemini stream_chat_with_tools failed for '%s': %s",
                model or self.model,
                scrubbed,
                exc_info=False,
            )
            raise LLMError(
                f"Gemini stream_chat_with_tools failed for '{model or self.model}': {scrubbed}"
            ) from exc

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
        except Exception as exc:  # noqa: BLE001 - discovery is best-effort
            logger.debug("Gemini model discovery failed: %s", scrub_exception(exc))
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
