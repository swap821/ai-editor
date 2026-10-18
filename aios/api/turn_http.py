"""The turn endpoints' shared HTTP machinery: request models, SSE framing,
turn context, the conversation flood throttle and the memory compactor.

Moved out of ``aios/api/main.py`` (2026-10-18, maintainability: slices 2-3 of
the split). Behaviour is unchanged. ``main`` re-exports every name here, so
``generate_pipeline``'s ``_LIVE_NAMES`` seam, tests and callers keep resolving
``aios.api.main.<name>``. The SSE event source stays ``"aios.api.main.sse"``:
it is a stable label consumers match on, not a module path.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from aios.api.deps import get_memory_authority
from aios.application.capabilities.authority import CapabilityError
from aios.application.memory.adapters import MemoryCompactionAdapter
from aios.application.turns import (
    TurnContext,
    TurnCoordinator,
)
from aios.core.events import (
    CanonicalEvent,
    CanonicalEventType,
    TrustLevel,
    event_for_sse,
)
from aios.core.injection_scan import detect_injection
from aios.domain.actions.envelope import (
    ActionEnvelope,
    ActionType,
    Principal as EnvelopePrincipal,
)
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import (
    payload_digest,
    resource_digest,
)
from aios.domain.identity.models import Principal
from aios.memory.compaction import MemoryCompactor
from fastapi import (
    HTTPException,
    Request,
)
from pydantic import (
    BaseModel,
    Field,
)
from typing import (
    Any,
    Callable,
    Iterator,
    Optional,
    cast,
)


def _main():
    """aios.api.main, read at CALL time: it owns the cortex bus and the API
    logger, and importing it at import time would be circular."""
    from aios.api import main

    return main


def get_compactor() -> MemoryCompactor:
    """Provide the audited memory-forgetting service backed by live stores.

    Returns a process-wide singleton so that working-session touch timestamps
    from ``/api/generate`` and ``/api/v1/chat`` survive into later compaction
    requests.
    """
    global _COMPACTOR
    if _COMPACTOR is None:
        with _COMPACTOR_LOCK:
            if _COMPACTOR is None:
                _COMPACTOR = MemoryCompactor(
                    working=_WORKING,
                    semantic=_SEMANTIC,
                    episodic=_EPISODIC,
                    index=_VECTOR_INDEX,
                )
                get_memory_authority().register_adapter(
                    "compaction", MemoryCompactionAdapter(_COMPACTOR)
                )
    return _COMPACTOR


class GenerateRequest(BaseModel):
    """Body for ``/api/generate`` — the conversational chat endpoint.

    ``messages`` is the front-end's running history in the shape
    ``[{"role": "user"|"assistant", "content": [{"text": "..."}]}]``.
    ``model_id`` is the UI's selected model id (e.g. ``ollama.llama3.2:3b``);
    the ``ollama.`` prefix is stripped, while an explicit non-local id requires
    configured Bedrock and never silently changes providers.
    """

    messages: list[dict[str, Any]] = Field(
        default_factory=lambda: cast(list[dict[str, Any]], [])
    )
    model_id: Optional[str] = Field(None, alias="modelId")
    session_id: str = Field("ui-session", alias="sessionId")
    approval_tokens: list[str] = Field(default_factory=list, alias="approvalTokens")
    #: Commands the human has authorised for this turn. When the agent pauses on
    #: a YELLOW command, the frontend re-sends the turn with that command added
    #: here so it actually runs (resumable in-chat approval — blueprint Q5).
    approved_commands: list[str] = Field(default_factory=list, alias="approvedCommands")
    #: File edits the human has authorised this turn (the edit analog of
    #: ``approvedCommands``), each ``{filepath, old_string, new_string}``.
    approved_edits: list[dict[str, Any]] = Field(
        default_factory=list, alias="approvedEdits"
    )
    #: New files the human has authorised this turn (the create analog of
    #: ``approvedEdits``), each ``{filepath, content}``.
    approved_creations: list[dict[str, Any]] = Field(
        default_factory=list, alias="approvedCreations"
    )
    #: Experimental role-pass selector. It is intentionally not production
    #: selected until WorkerFoundry owns its lifecycle.
    role_pass: bool = Field(False, alias="rolePass")
    #: Experimental swarm selector. It is intentionally not production selected
    #: until WorkerFoundry owns its lifecycle. Takes precedence over rolePass
    #: when both are set for the refusal message.
    swarm: bool = Field(False, alias="swarm")
    #: Explicitly opt into mission authority for this turn.  The route no
    #: longer upgrades every forge request to mission mode implicitly.
    mission_requested: bool = Field(False, alias="missionRequested")
    #: Explicit governance semantics are separate from mission semantics.
    governance_requested: bool = Field(False, alias="governanceRequested")

    model_config = {"populate_by_name": True}


def _generate_capability_binding(
    principal: Principal,
    action_type: str,
    payload: dict[str, Any],
    *,
    route: str = "/api/generate",
) -> CapabilityBinding:
    """Bind one generate approval to the authenticated human and exact action."""
    if action_type not in {"command", "edit", "create"}:
        raise CapabilityError(f"unsupported generate capability action: {action_type}")
    return CapabilityBinding(
        operator_id=principal.principal_id,
        device_id=principal.device_id,
        authentication_event_id=principal.authentication_event_id,
        session_id=principal.session_id,
        action_type=action_type,
        route=route,
        http_method="POST",
        payload_digest=payload_digest(payload),
        resource_digest=resource_digest({"workspace": "training_ground"}),
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope="training_ground/",
        verification_requirement=(
            "command_exit_zero"
            if action_type == "command"
            else "write_auto_verify_pass"
        ),
        constitution_digest=principal.constitution_digest or None,
    )


def _generate_action_envelope(
    principal: Principal,
    request: Request,
    action_type: str,
    payload: dict[str, Any],
) -> ActionEnvelope:
    """Build the R4 envelope for one streamed generate approval."""
    return ActionEnvelope(
        route="/api/generate",
        action_type=ActionType.GENERATE,
        http_method="POST",
        payload=payload,
        principal=EnvelopePrincipal(
            session_id=principal.session_id,
            actor_source="session",
            client_ip=principal.client_address or "127.0.0.1",
        ),
        request_id=principal.request_id or request.headers.get("x-request-id"),
        operator_id=principal.principal_id,
        device_id=principal.device_id,
        authentication_event_id=principal.authentication_event_id,
        resource={"workspace": "training_ground"},
        requested_capability=f"generate.{action_type}",
        correlation_id=(
            request.headers.get("x-correlation-id")
            or principal.request_id
            or request.headers.get("x-request-id")
            or str(uuid.uuid4())
        ),
    )


def _validate_generate_action_payload(
    action_type: str,
    payload: object,
) -> dict[str, Any]:
    """Accept only the server-issued payload shapes the tool loop can replay."""
    if not isinstance(payload, dict):
        raise CapabilityError("generate capability payload is not an object")
    required = {
        "command": ("command",),
        "edit": ("filepath", "old_string", "new_string"),
        "create": ("filepath", "content"),
    }.get(action_type)
    if required is None or any(
        not isinstance(payload.get(key), str) for key in required
    ):
        raise CapabilityError("generate capability payload is malformed")
    if any(
        not str(payload[key]).strip()
        for key in required
        if key in {"command", "filepath"}
    ):
        raise CapabilityError("generate capability payload contains an empty target")
    return dict(payload)


class ChatRequest(BaseModel):
    """Body for ``/api/v1/chat`` — the lean Hinglish conversational endpoint.

    Conversation only (the GAGOS voice mind): a single ``transcript``
    line from the operator + an optional ``sessionId``. It reuses the multi-LLM
    router (privacy gate intact), memory recall, and REAL personalization facts,
    then streams one reply. NO file-write or coding tools run here — this is talk,
    not the agentic forge.
    """

    transcript: str = Field(
        ...,
        max_length=2000,
        description="The operator's spoken/typed turn (input-shielded: capped length).",
    )
    session_id: str = Field("voice-session", alias="sessionId")
    model_id: Optional[str] = Field(None, alias="modelId")

    model_config = {"populate_by_name": True}


# --------------------------------------------------------------------------- #
# Front-end bridge: model discovery, conversational chat, UI terminal
# These three endpoints back the React UI's main surfaces. The ``/api/v1/*``
# routes above expose individual subsystems; these compose them for the UI.
# --------------------------------------------------------------------------- #
def _to_chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten the UI history (``content`` arrays) into Ollama chat messages."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            content_list: list[Any] = cast(list[Any], content)
            text_parts: list[str] = [
                cast(dict[str, Any], c).get("text", "")
                for c in content_list
                if isinstance(c, dict)
            ]
            text = " ".join(text_parts).strip()
        else:
            text = ""
        if text:
            out.append({"role": role, "content": text})
    return out


def _message_context_chars(messages: list[dict[str, Any]]) -> int:
    """Total characters of text the turn is carrying, history included.

    The routing signal for ``long_context`` is a MEASUREMENT, not a phrase:
    "summarise this huge file" and a pasted 200k-character file are the same
    routing decision, and only one of them says so in words. Counting the whole
    history rather than the last message is the point — a long conversation is a
    long-context problem even when the final turn is three words.
    """
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in cast(list[Any], content):
                if isinstance(block, dict):
                    total += len(str(cast(dict[str, Any], block).get("text") or ""))
    return total


#: Content-block keys that mean an image is present. Kept as data because the
#: shape differs by client (Bedrock Converse, Anthropic, OpenAI all spell it
#: differently) and a new one should be a one-line addition, not a rewrite.
_IMAGE_BLOCK_KEYS = ("image", "image_url", "inline_data", "source")


def _messages_have_images(messages: list[dict[str, Any]]) -> bool:
    """Whether any message actually carries an image block.

    Vision routing keys off this and never off wording: "look at this
    screenshot" with no screenshot is not a vision turn, and sending it to a
    vision model on the strength of the phrase is guessing dressed as
    classification.

    HONEST LIMIT: the frontend does not send image blocks today —
    ``_to_chat_messages`` reads ``block["text"]`` and drops everything else — so
    this returns False on every current request. It is the detector half of a
    path whose other half does not exist yet, tested directly so it is correct
    the day one arrives, rather than a claim that vision routing works now.
    """
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in cast(list[Any], content):
            if isinstance(block, dict) and any(
                key in cast(dict[str, Any], block) for key in _IMAGE_BLOCK_KEYS
            ):
                return True
    return False


def _sse(
    event: str,
    data: dict[str, Any],
    *,
    turn_id: Optional[str] = None,
    seq: Optional[int] = None,
) -> str:
    """Format one Server-Sent Event frame.

    All newline characters (\\n, \\r) in the JSON payload are escaped to \\n
    and \\r so that an LLM output cannot inject fake SSE events by embedding
    ``\\n\\nevent: approve\\ndata: {...}`` inside a data field.
    """
    if turn_id is not None and seq is not None:
        event_obj = event_for_sse(event, data, turn_id=turn_id, seq=seq)
        data = event_obj.to_sse_payload()

        bus = _main().get_cortex_bus()
        if bus is not None:
            # Opportunistic mapping to a canonical event for the truthful journal
            canonical_type = event
            if event == "turn.started":
                canonical_type = CanonicalEventType.TURN_STARTED.value
            elif event == "route":
                canonical_type = CanonicalEventType.ROUTE_SELECTED.value
            elif event == "human_required":
                canonical_type = CanonicalEventType.APPROVAL_REQUIRED.value
            elif event == "done":
                canonical_type = CanonicalEventType.TURN_COMPLETED.value
            elif event == "error":
                canonical_type = CanonicalEventType.TURN_FAILED.value
            elif event == "injection_detected":
                # An injection seen in TOOL OUTPUT. Recorded as an observation,
                # not a decision, so it is admissible under the cortex-bus law
                # ("carries what HAPPENED, never what is PERMITTED") -- the
                # `security.` prefix is deliberately outside
                # _AUTHORITY_EVENT_PREFIXES. Before 2026-09-03 an injection left
                # no trace at all, on any channel.
                canonical_type = CanonicalEventType.SECURITY_INJECTION_DETECTED.value

            canonical = CanonicalEvent(
                event_type=canonical_type,
                phase=event_obj.phase.value,
                status=(
                    "completed"
                    if event == "done"
                    else "failed"
                    if event == "error"
                    else "in_progress"
                ),
                trust=TrustLevel.ADVISORY.value,
                source="aios.api.main.sse",
                session_id=turn_id,
                turn_id=turn_id,
                sequence=seq,
                payload=data,
            )
            try:
                bus.append(canonical)
            except Exception:
                # Not re-raised: a rejected/failed cortex-bus mirror-mapping
                # must never break the real SSE response the operator is
                # waiting on. Logged (not silently dropped) because a
                # rejection here is a real gap in the truthful mirror, not
                # noise -- e.g. "human_required" maps to "approval.required",
                # which CortexBus.append() always refuses (an authority-
                # bearing prefix), so this canonical event never reaches
                # the mirror stream today.
                _main().logger.debug(
                    "cortex_bus_mirror_append_failed",
                    extra={"sse_event": event, "canonical_type": canonical_type},
                    exc_info=True,
                )
    payload = json.dumps(data, ensure_ascii=False)
    # Defensive: escape any literal newlines that would break the SSE frame.
    payload = payload.replace("\r", "\\r").replace("\n", "\\n")
    return f"event: {event}\ndata: {payload}\n\n"


def _sse_writer(turn_id: str) -> Callable[[str, dict[str, Any]], str]:
    seq = 0

    def write(event: str, data: dict[str, Any]) -> str:
        nonlocal seq
        seq += 1
        return _sse(event, data, turn_id=turn_id, seq=seq)

    return write


#: Agent event type -> SSE event name the front-end's stream reader understands.
_STEP_EVENTS = {"tool_call", "tool_result", "tool_blocked"}


#: Process-wide memory facades are all authority-owned adapters.  The
#: compatibility names remain because the compactor and legacy tests consume
#: these narrow interfaces.
_MEMORY_AUTHORITY = get_memory_authority()


_EPISODIC = _MEMORY_AUTHORITY.adapters["episodic"]


_WORKING = _MEMORY_AUTHORITY.adapters["working"]


_SEMANTIC = _MEMORY_AUTHORITY.adapters["semantic"]


#: FAISS vector index exposed by the authority-owned semantic adapter.
_VECTOR_INDEX = _SEMANTIC.index


#: Process-wide audited memory compactor so working-session touch timestamps are
#: preserved across independent FastAPI dependency injections.
_COMPACTOR: Optional[MemoryCompactor] = None


_COMPACTOR_LOCK = threading.Lock()


def _build_turn_context(
    session_id: str,
    directive: str,
    *,
    model_id: Optional[str] = None,
    approval_tokens: Optional[list[str]] = None,
    mission_requested: bool = False,
    governance_requested: bool = False,
    data_classification: str = "PROJECT_INTERNAL",
    operator_id: str | None = None,
    project_id: str | None = None,
) -> TurnContext:
    """Create a canonical TurnContext for the current directive."""
    mode = TurnCoordinator.classify_mode(
        directive,
        mission_requested=mission_requested,
        governance_requested=governance_requested,
    )
    return TurnContext(
        turn_id=str(uuid.uuid4()),
        session_id=session_id,
        operator_id=operator_id,
        project_id=project_id,
        directive=directive,
        mode=mode,
        model_id=model_id,
        approval_tokens=tuple(approval_tokens or []),
        data_classification=data_classification,
        correlation_id=str(uuid.uuid4()),
    )


#: System prompt for the lean conversational endpoint (the GAGOS voice mind,
#: Slice 1). It is CONVERSATION, not the coding forge: no file edits, no tool
#: loop — just a warm, technically deep Hinglish chat. The operator-facts context
#: block (REAL approved facts only; absent when none) is appended at request time,
#: and the honesty law is stated inline so the model never invents personal facts.
CHAT_SYSTEM_PROMPT = (
    "Tu GAGOS hai — operator ka personal AI-OS, 'the voyaging mind'. Tera naam HAMESHA "
    "GAGOS hai; tu KABHI khud ko 'Jarvis' ya kisi aur naam se nahi bulata. Tu ek saathi ki "
    "tarah baat karta hai: natural HINGLISH mein (English aur Hindi ka fluid mix), "
    "jaise operator khud likhta/bolta hai — uske tone aur mix ko match kar. "
    "Concise reh, warm reh, lekin technically deep — code, architecture, ya kuch "
    "bhi discuss kar sakta hai gehrai se. "
    "Yeh sirf baat-cheet hai, coding forge NAHI: tu koi file edit/create nahi karta, "
    "koi tool ya terminal nahi chalata, sirf jawaab deta hai. Agar operator ko "
    "actual code likhwana/chalwana ho, use politely batao ki woh main forge "
    "(generate) flow se kare. "
    "Personalization: neeche diye gaye operator ke REAL facts hi use kar; agar koi "
    "fact nahi diya gaya to koi personal baat invent mat kar — honest reh, "
    "generic reh."
)


# --- /api/v1/chat input-shield: per-session sliding-window flood throttle ----
# The voice/chat path is the one endpoint that takes free-form operator text and
# fans it straight at a (possibly cloud) provider with the operator's recalled
# facts attached. The Pydantic ``max_length`` cap bounds a single turn; this
# bounds the RATE so a stuck client (or a tab left auto-sending) cannot flood the
# router. It is deliberately lightweight and in-process (best-effort, per-worker),
# distinct from the durable security RateLimiter that governs RED actions.
_CONVERSATION_RATE_WINDOW_S = 60.0


_CONVERSATION_RATE_MAX = 30


_CONVERSATION_HITS: dict[str, list[float]] = {}


def _enforce_conversation_rate_limit(session_id: str) -> None:
    """Raise HTTP 429 if a session exceeds ``_CONVERSATION_RATE_MAX`` turns per window.

    A simple monotonic sliding window keyed by session id. Best-effort and
    in-process; the deterministic security cage (gateway, scope lock, audit) is
    unaffected — this only protects the conversational fan-out from flooding.
    """
    now = time.monotonic()
    cutoff = now - _CONVERSATION_RATE_WINDOW_S
    # BUG-F fix: evict fully-expired sessions so the map can't grow without bound
    # as fresh session ids keep arriving (each browser session mints a new one).
    # Previously every session left a key forever. This bounds the map to
    # sessions active within the window.
    for sid in [
        s for s, ts in _CONVERSATION_HITS.items() if not any(t > cutoff for t in ts)
    ]:
        del _CONVERSATION_HITS[sid]
    hits = [t for t in _CONVERSATION_HITS.get(session_id, ()) if t > cutoff]
    if len(hits) >= _CONVERSATION_RATE_MAX:
        _CONVERSATION_HITS[session_id] = hits
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many conversation turns; slow down. "
                f"Limit is {_CONVERSATION_RATE_MAX} per {int(_CONVERSATION_RATE_WINDOW_S)}s."
            ),
        )
    hits.append(now)
    _CONVERSATION_HITS[session_id] = hits


def _check_prompt_injection(text: str) -> Optional[str]:
    """Return the gateway reason if *text* is a prompt injection, else None.

    Thin wrapper over ``aios.core.injection_scan.detect_injection`` so this
    route and the TOOL-OUTPUT path share one predicate. That module reuses the
    public ``classify()`` API without editing frozen-core gateway code, and
    ignores non-injection RED results so normal conversation is not blocked.
    """
    # Delegates to the shared predicate so user input and TOOL OUTPUT cannot
    # drift apart. Two callers, one derivation: a differential "do these layers
    # agree?" gap is the shape that has produced real containment escapes here.
    return detect_injection(text)


def _stream_chat_chunks(
    chat_client: Any,
    messages: list[dict[str, Any]],
    *,
    model: str,
) -> Iterator[str]:
    """Yield real chat chunks when available, else preserve word streaming."""
    stream_fn = getattr(chat_client, "stream_chat", None)
    if callable(stream_fn):
        for chunk in stream_fn(messages, tools=None, model=model):
            text = str(chunk)
            if text:
                yield text
        return

    reply = chat_client.chat(messages, tools=None, model=model)
    text = str((reply or {}).get("content", "")).strip() or "(no answer)"
    for word in re.findall(r"\S+\s*", text):
        yield word
