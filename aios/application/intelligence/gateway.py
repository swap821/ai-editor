"""Universal Intelligence Gateway pipeline (Slice 30).

This is the non-provider-specific half of "one universal gateway": identity/
constitution validation, representative-context compilation (Slice 29),
emergency-stop enforcement (Slice 27), and output secret redaction. It takes
the actual provider call as a caller-supplied `model_call` callback rather
than constructing a client itself -- so this module never needs to appear in
`tests/architecture/test_intelligence_boundary.py`'s allow-list, and adding a
new provider never requires touching this file.

Full scope note: this pipeline is not yet the mandatory entrance for every
model interaction in the codebase. Within the audited Phase-2 paths, the
remaining direct model-call seams are narrow legacy CRAG helpers retained for
direct unit tests. The production CRAG judge and optional cloud source enter
this authority through authenticated generate-state callbacks; the local-clerk
structured advisory path and local-workforce health/qualification probes enter
the explicit local-only compatibility boundary below. The maintenance
convergence service itself has no direct model call and is not an Organ 32
bypass. See
docs/architecture/GAGOS_54_ORGANS.md organ 32 for the exact current scope and
follow-on work, including reconciliation with the two pre-existing
gateway-shaped implementations, aios.runtime.intelligence_gateway.
IntelligenceGateway and aios.application.models.hiring_service.
IntelligenceHiringService.
Anonymous compatibility conversation has an explicit local-only entrance
below; it has no authenticated identity/constitution binding, so it emits no
representative-context receipt.
"""

from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from aios.application.intelligence.context_compiler import (
    CompilationTarget,
    RepresentativeContextCompilerAuthority,
)
from aios.domain.intelligence.representative_context import (
    RepresentativeContextReceiptV1,
    RepresentativeContextV1,
)
from aios.domain.memory.human_representation import (
    CorrectionRecordV1,
    OperatorPreferenceV1,
    ProjectPassportV1,
)
from aios.runtime.secret_policy import SecretPolicy

_LOGGER = logging.getLogger(__name__)
_REPRESENTATIVE_CONTEXT_COMPILER = RepresentativeContextCompilerAuthority()


class IntelligenceGatewayError(RuntimeError):
    """Raised when the gateway itself refuses a request (not a provider error)."""


@dataclass(frozen=True, slots=True)
class IntelligenceGatewayResult:
    """The final, redacted result of one gateway-routed model call."""

    context: RepresentativeContextV1
    output: str
    secrets_redacted: bool


@dataclass(frozen=True, slots=True)
class StreamingIntelligenceGatewayResult:
    """The compiled context (available immediately, before streaming starts)
    plus a lazy, boundary-safe redacted stream of text. ``context`` is available
    right away specifically so a caller can emit a "route"/metadata frame
    before the first text chunk, matching the existing chat SSE wire shape.
    """

    context: RepresentativeContextV1
    chunks: Iterator[str]
    receipt: RepresentativeContextReceiptV1 | None = None

@dataclass(frozen=True, slots=True)
class CompatibilityStreamingIntelligenceGatewayResult:
    """A redacted local-only stream for anonymous compatibility callers."""

    chunks: Iterator[str]
    target: str = "local"


@dataclass(frozen=True, slots=True)
class StructuredStreamingIntelligenceGatewayResult:
    """Compiled context plus a lazy structured forge event stream."""

    context: RepresentativeContextV1
    events: Iterator[dict[str, Any]]
    receipt: RepresentativeContextReceiptV1 | None = None


def _validate_and_compile(
    *,
    request_id: str,
    operator_identity_digest: str,
    constitution_digest: str,
    goal: str,
    desired_outcome: str,
    target: CompilationTarget,
    delegated_authority_summary: str,
    explicit_constraints: Sequence[str],
    current_decisions: Sequence[str],
    active_preferences: Sequence[OperatorPreferenceV1],
    project_passport: ProjectPassportV1 | None,
    project_passport_stale: bool,
    relevant_memory_refs: Sequence[str],
    permitted_tools: Sequence[str],
    evidence_requirements: Sequence[str],
    communication_mode: str,
    latest_correction: CorrectionRecordV1 | None,
    policy: SecretPolicy,
    emergency_stop: Any | None,
) -> RepresentativeContextV1:
    """Shared identity/constitution validation + emergency-stop check +
    context compilation for both the synchronous and streaming gateway
    entrances, so the two can never silently drift apart."""
    if not operator_identity_digest.strip():
        raise IntelligenceGatewayError("operator_identity_digest is required")
    if not constitution_digest.strip():
        raise IntelligenceGatewayError("constitution_digest is required")
    if emergency_stop is not None:
        emergency_stop.assert_operational()

    return _REPRESENTATIVE_CONTEXT_COMPILER.compile(
        request_id=request_id,
        operator_identity_digest=operator_identity_digest,
        constitution_digest=constitution_digest,
        goal=goal,
        desired_outcome=desired_outcome,
        target=target,
        delegated_authority_summary=delegated_authority_summary,
        explicit_constraints=explicit_constraints,
        current_decisions=current_decisions,
        active_preferences=active_preferences,
        project_passport=project_passport,
        project_passport_stale=project_passport_stale,
        relevant_memory_refs=relevant_memory_refs,
        permitted_tools=permitted_tools,
        evidence_requirements=evidence_requirements,
        communication_mode=communication_mode,
        latest_correction=latest_correction,
        secret_policy=policy,
    )


def _default_context_store() -> Any:
    from aios import config
    from aios.infrastructure.intelligence.representative_context_store import (
        RepresentativeContextStore,
    )

    return RepresentativeContextStore(config.REPRESENTATIVE_CONTEXT_DB_PATH)


def _record_context(context: RepresentativeContextV1, store: Any | None) -> None:
    """Organ 31: durably record every context that passed identity/
    constitution/emergency-stop validation and is about to inform a real
    model call. Best-effort, never fatal -- a store failure must never
    block an already-governed call, matching `_record_human_state`'s
    (organ 30) established convention exactly."""
    try:
        target = store if store is not None else _default_context_store()
        target.save(context)
    except Exception:  # noqa: BLE001 - persistence must never break a gated call
        _LOGGER.warning("Failed to record representative context", exc_info=True)


#: How much raw text is held back before emitting, so a secret straddling a
#: chunk boundary is still whole when it is scanned.
_REDACTION_LAG_CHARS = 64

#: Hard ceiling on buffered text. Reached only when a candidate match keeps
#: straddling the boundary; without it a hostile or malformed stream could grow
#: the buffer without limit.
_REDACTION_MAX_BUFFER_CHARS = 65536


def _redact_stream(chunks: Iterable[Any], policy: SecretPolicy) -> Iterator[str]:
    """Redact a token stream without letting a split secret escape.

    Redacting each chunk independently is not safe, and not theoretically so:
    an OpenAI ``sk-`` key, an AWS access key id and a GitHub PAT all pass
    through *in full* when split at the wrong offset, because neither half
    matches on its own. Whole-string redaction catches all three.

    A fixed look-behind window cannot fix this on its own -- every key pattern
    is open-ended (``{32,}``), and the PEM private-key pattern spans arbitrary
    content between its BEGIN and END markers. Nor can we flush on whitespace:
    ``Bearer\\s+<token>`` and ``password\\s*=\\s*<value>`` both match across it.

    So the boundary is detected rather than assumed. Text is held back by
    ``_REDACTION_LAG_CHARS``; before emitting a prefix we check whether
    redacting the buffer as a whole differs from redacting the prefix and the
    held-back tail separately. If it differs, some match straddles the cut, and
    the buffer grows instead of emitting. That is exact for anything the
    scanner can match, not an approximation of it.

    Honest, bounded limitation: a single secret longer than
    ``_REDACTION_MAX_BUFFER_CHARS`` could still be split at the cap. 64 KiB
    comfortably exceeds a 4096-bit PEM key, and the alternative -- unbounded
    buffering -- is a denial-of-service vector.
    """
    carry = ""
    for chunk in chunks:
        text = str(chunk)
        if not text:
            continue
        carry += text
        if len(carry) <= _REDACTION_LAG_CHARS:
            continue
        head, tail = carry[:-_REDACTION_LAG_CHARS], carry[-_REDACTION_LAG_CHARS:]
        joint = policy.redact_text(carry)
        if joint == policy.redact_text(head) + policy.redact_text(tail):
            # Nothing spans the cut: the prefix is final and safe to emit.
            emitted = policy.redact_text(head)
            if emitted:
                yield emitted
            carry = tail
        elif len(carry) >= _REDACTION_MAX_BUFFER_CHARS:
            # Still straddling at the ceiling. Emit the whole buffer redacted
            # as one piece -- correct for every match inside it -- rather than
            # buffering without limit.
            if joint:
                yield joint
            carry = ""
    if carry:
        final = policy.redact_text(carry)
        if final:
            yield final


class _StructuredTextRedactor:
    """Boundary-safe redaction window for incremental event text."""

    def __init__(self, policy: SecretPolicy) -> None:
        self._policy = policy
        self._carry = ""

    def feed(self, value: str) -> list[str]:
        self._carry += value
        if len(self._carry) <= _REDACTION_LAG_CHARS:
            return []
        head = self._carry[:-_REDACTION_LAG_CHARS]
        tail = self._carry[-_REDACTION_LAG_CHARS:]
        joint = self._policy.redact_text(self._carry)
        if joint == self._policy.redact_text(head) + self._policy.redact_text(tail):
            self._carry = tail
            emitted = self._policy.redact_text(head)
            return [emitted] if emitted else []
        if len(self._carry) >= _REDACTION_MAX_BUFFER_CHARS:
            self._carry = ""
            return [joint] if joint else []
        return []

    def flush(self) -> list[str]:
        if not self._carry:
            return []
        value = self._policy.redact_text(self._carry)
        self._carry = ""
        return [value] if value else []


def _redact_structured_value(value: Any, policy: SecretPolicy) -> Any:
    """Recursively redact provider-visible event values."""
    if isinstance(value, str):
        return policy.redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(key): _redact_structured_value(item, policy)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_structured_value(item, policy) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_structured_value(item, policy) for item in value)
    return value


def _redact_structured_event(
    event: Mapping[str, Any], policy: SecretPolicy
) -> dict[str, Any]:
    """Scrub display fields while preserving exact approval payloads.

    ToolAgent events are also an internal control protocol. The generate
    pipeline must receive the original command/edit/create payload so its
    capability binding and approval resume remain exact. Those fields are not
    rewritten here; user-visible text, explanations, and tool results are.
    """
    event_type = str(event.get("type", ""))
    authority_fields = (
        {"command", "edit", "creation", "_convo_tail"}
        if event_type in {"tool_call", "human_required"}
        else set()
    )
    return {
        str(key): (
            value
            if key in authority_fields
            else _redact_structured_value(value, policy)
        )
        for key, value in event.items()
    }


def _redact_structured_stream(
    events: Iterable[Mapping[str, Any]], policy: SecretPolicy
) -> Iterator[dict[str, Any]]:
    """Redact structured events, including secrets split across text events."""
    stream_redactor = _StructuredTextRedactor(policy)
    pending_template: dict[str, Any] | None = None
    pending_key: str | None = None

    def flush_pending() -> Iterator[dict[str, Any]]:
        nonlocal pending_template, pending_key
        if pending_template is None or pending_key is None:
            return
        for text_value in stream_redactor.flush():
            event = dict(pending_template)
            event[pending_key] = text_value
            yield event
        pending_template = None
        pending_key = None

    for raw_event in events:
        if not isinstance(raw_event, Mapping):
            raise IntelligenceGatewayError("structured model events must be mappings")
        event_type = str(raw_event.get("type", ""))
        stream_key = (
            "text"
            if event_type == "text" and isinstance(raw_event.get("text"), str)
            else "code"
            if event_type == "code" and isinstance(raw_event.get("code"), str)
            else None
        )
        if stream_key is None:
            yield from flush_pending()
            yield _redact_structured_event(raw_event, policy)
            continue

        template = {
            str(key): _redact_structured_value(value, policy)
            for key, value in raw_event.items()
            if key != stream_key
        }
        if pending_template is None:
            pending_template = template
            pending_key = stream_key
        for text_value in stream_redactor.feed(str(raw_event[stream_key])):
            event = dict(pending_template or template)
            event[pending_key or stream_key] = text_value
            yield event
            pending_template = None
            pending_key = None

    yield from flush_pending()


def _record_required_receipt(
    context: RepresentativeContextV1,
    *,
    receipt_factory: Callable[[RepresentativeContextV1], RepresentativeContextReceiptV1]
    | None,
    store: Any | None,
) -> RepresentativeContextReceiptV1:
    """Persist a complete authenticated-chat receipt before any provider call.

    The generic gateway keeps its historic best-effort context recording for
    compatibility. Authenticated chat opts into this stricter bundle operation:
    a missing, expired, malformed, or unwritable receipt is a refusal, never a
    reason to silently fall back to an unrecorded model call.
    """
    if receipt_factory is None:
        raise IntelligenceGatewayError(
            "authenticated request requires a representative context receipt"
        )
    try:
        receipt = receipt_factory(context)
        expiry = datetime.fromisoformat(receipt.expires_at.replace("Z", "+00:00"))
        if expiry <= datetime.now(timezone.utc):
            raise IntelligenceGatewayError("representative context receipt expired")
        target = store if store is not None else _default_context_store()
        target.save_bundle(context, receipt)
    except IntelligenceGatewayError:
        raise
    except Exception as exc:  # noqa: BLE001 - strict authenticated boundary
        raise IntelligenceGatewayError(
            "representative context receipt persistence failed"
        ) from exc
    return receipt


class UniversalIntelligenceGatewayAuthority:
    """Own synchronous, plain-text, and structured streaming gateway entrances.

    The authority enforces the shared call contract before either execution
    path is entered: a real request id, a valid local/cloud target, and a
    callable provider adapter. All paths then share the existing identity,
    constitution, emergency-stop, context-recording, and output-redaction
    implementation; no caller can silently choose only one of those gates.
    """

    @staticmethod
    def _validate_call_contract(kwargs: dict[str, Any]) -> None:
        request_id = str(kwargs.get("request_id", "")).strip()
        if not request_id:
            raise IntelligenceGatewayError("request_id is required")
        if kwargs.get("target") not in ("local", "cloud"):
            raise IntelligenceGatewayError("target must be local or cloud")
        if not callable(kwargs.get("model_call")):
            raise IntelligenceGatewayError("model_call must be callable")

    def route(self, **kwargs: Any) -> IntelligenceGatewayResult:
        """Compile context, invoke the caller's model call, redact the output.

        Pipeline order (matching the brief): identity/constitution validation
        (bare non-empty checks here -- full constitution-mismatch enforcement at
        the PolicyKernel decision path is still open, see organ 25's blockers) ->
        representative-context compilation -> emergency-stop check -> the
        caller's model call -> output secret redaction. Provider eligibility,
        budget, and health checks are deliberately not reimplemented here --
        they already exist (`aios.core.router`, `aios.runtime.budget_guard`) and
        a caller wires them into how it builds `model_call`, rather than this
        pipeline re-deciding provider selection.

        `context_store` (organ 31) durably records the compiled context once it
        has passed every check above -- pass an explicit store (or a test spy)
        to override the default `RepresentativeContextStore`; the record is
        best-effort and never blocks the call itself.
        """
        self._validate_call_contract(kwargs)
        policy = kwargs.get("secret_policy") or SecretPolicy()
        context = _validate_and_compile(
            request_id=kwargs["request_id"],
            operator_identity_digest=kwargs["operator_identity_digest"],
            constitution_digest=kwargs["constitution_digest"],
            goal=kwargs["goal"],
            desired_outcome=kwargs["desired_outcome"],
            target=kwargs["target"],
            delegated_authority_summary=kwargs["delegated_authority_summary"],
            explicit_constraints=kwargs.get("explicit_constraints", ()),
            current_decisions=kwargs.get("current_decisions", ()),
            active_preferences=kwargs.get("active_preferences", ()),
            project_passport=kwargs.get("project_passport"),
            project_passport_stale=kwargs.get("project_passport_stale", False),
            relevant_memory_refs=kwargs.get("relevant_memory_refs", ()),
            permitted_tools=kwargs.get("permitted_tools", ()),
            evidence_requirements=kwargs.get("evidence_requirements", ()),
            communication_mode=kwargs.get("communication_mode", "direct"),
            latest_correction=kwargs.get("latest_correction"),
            policy=policy,
            emergency_stop=kwargs.get("emergency_stop"),
        )
        _record_context(context, kwargs.get("context_store"))

        raw_output = kwargs["model_call"](context)
        decision = policy.inspect_text(raw_output)
        return IntelligenceGatewayResult(
            context=context,
            output=decision.scrubbed,
            secrets_redacted=decision.detected,
        )

    def stream(self, **kwargs: Any) -> StreamingIntelligenceGatewayResult:
        """Streaming counterpart to `route()` for text-chunk model calls."""
        self._validate_call_contract(kwargs)
        policy = kwargs.get("secret_policy") or SecretPolicy()
        context = _validate_and_compile(
            request_id=kwargs["request_id"],
            operator_identity_digest=kwargs["operator_identity_digest"],
            constitution_digest=kwargs["constitution_digest"],
            goal=kwargs["goal"],
            desired_outcome=kwargs["desired_outcome"],
            target=kwargs["target"],
            delegated_authority_summary=kwargs["delegated_authority_summary"],
            explicit_constraints=kwargs.get("explicit_constraints", ()),
            current_decisions=kwargs.get("current_decisions", ()),
            active_preferences=kwargs.get("active_preferences", ()),
            project_passport=kwargs.get("project_passport"),
            project_passport_stale=kwargs.get("project_passport_stale", False),
            relevant_memory_refs=kwargs.get("relevant_memory_refs", ()),
            permitted_tools=kwargs.get("permitted_tools", ()),
            evidence_requirements=kwargs.get("evidence_requirements", ()),
            communication_mode=kwargs.get("communication_mode", "direct"),
            latest_correction=kwargs.get("latest_correction"),
            policy=policy,
            emergency_stop=kwargs.get("emergency_stop"),
        )
        require_context_receipt = kwargs.get("require_context_receipt", False)
        receipt = (
            _record_required_receipt(
                context,
                receipt_factory=kwargs.get("receipt_factory"),
                store=kwargs.get("context_store"),
            )
            if require_context_receipt
            else None
        )
        if not require_context_receipt:
            _record_context(context, kwargs.get("context_store"))

        def _redacted_chunks() -> Iterator[str]:
            return _redact_stream(kwargs["model_call"](context), policy)

        return StreamingIntelligenceGatewayResult(
            context=context, chunks=_redacted_chunks(), receipt=receipt
        )

    def stream_structured(
        self, **kwargs: Any
    ) -> StructuredStreamingIntelligenceGatewayResult:
        """Govern and redact a structured forge event stream."""
        self._validate_call_contract(kwargs)
        policy = kwargs.get("secret_policy") or SecretPolicy()
        context = _validate_and_compile(
            request_id=kwargs["request_id"],
            operator_identity_digest=kwargs["operator_identity_digest"],
            constitution_digest=kwargs["constitution_digest"],
            goal=kwargs["goal"],
            desired_outcome=kwargs["desired_outcome"],
            target=kwargs["target"],
            delegated_authority_summary=kwargs["delegated_authority_summary"],
            explicit_constraints=kwargs.get("explicit_constraints", ()),
            current_decisions=kwargs.get("current_decisions", ()),
            active_preferences=kwargs.get("active_preferences", ()),
            project_passport=kwargs.get("project_passport"),
            project_passport_stale=kwargs.get("project_passport_stale", False),
            relevant_memory_refs=kwargs.get("relevant_memory_refs", ()),
            permitted_tools=kwargs.get("permitted_tools", ()),
            evidence_requirements=kwargs.get("evidence_requirements", ()),
            communication_mode=kwargs.get("communication_mode", "direct"),
            latest_correction=kwargs.get("latest_correction"),
            policy=policy,
            emergency_stop=kwargs.get("emergency_stop"),
        )
        require_context_receipt = kwargs.get("require_context_receipt", False)
        receipt = (
            _record_required_receipt(
                context,
                receipt_factory=kwargs.get("receipt_factory"),
                store=kwargs.get("context_store"),
            )
            if require_context_receipt
            else None
        )
        if not require_context_receipt:
            _record_context(context, kwargs.get("context_store"))

        def _redacted_events() -> Iterator[dict[str, Any]]:
            raw_events = kwargs["model_call"](context)
            yield from _redact_structured_stream(raw_events, policy)

        return StructuredStreamingIntelligenceGatewayResult(
            context=context, events=_redacted_events(), receipt=receipt
        )

    def stream_compatibility(
        self, **kwargs: Any
    ) -> CompatibilityStreamingIntelligenceGatewayResult:
        """Use the bounded local-only anonymous compatibility entrance."""
        request_id = str(kwargs.get("request_id", "")).strip()
        if not request_id:
            raise IntelligenceGatewayError("request_id is required")
        target = kwargs.get("target")
        if target != "local":
            raise IntelligenceGatewayError(
                "anonymous compatibility requests must target the local provider"
            )
        model_call = kwargs.get("model_call")
        if not callable(model_call):
            raise IntelligenceGatewayError("model_call must be callable")
        emergency_stop = kwargs.get("emergency_stop")
        if emergency_stop is not None:
            emergency_stop.assert_operational()
        policy = kwargs.get("secret_policy") or SecretPolicy()

        def _redacted_chunks() -> Iterator[str]:
            yield from _redact_stream(model_call(), policy)

        return CompatibilityStreamingIntelligenceGatewayResult(
            chunks=_redacted_chunks()
        )

    def complete_compatibility(self, **kwargs: Any) -> str:
        """Use the bounded local-only synchronous compatibility entrance."""
        request_id = str(kwargs.get("request_id", "")).strip()
        if not request_id:
            raise IntelligenceGatewayError("request_id is required")
        target = kwargs.get("target")
        if target != "local":
            raise IntelligenceGatewayError(
                "anonymous compatibility requests must target the local provider"
            )
        model_call = kwargs.get("model_call")
        if not callable(model_call):
            raise IntelligenceGatewayError("model_call must be callable")
        emergency_stop = kwargs.get("emergency_stop")
        if emergency_stop is not None:
            emergency_stop.assert_operational()
        policy = kwargs.get("secret_policy") or SecretPolicy()
        decision = policy.inspect_text(model_call())
        return decision.scrubbed


class CompatibilityAdvisoryCompletionClient:
    """Adapt a local provider to the anonymous advisory gateway entrance.

    This is intentionally weaker than ``GovernedAdvisoryCompletionClient``:
    callers such as the local clerk do not carry an authenticated operator
    identity or constitution snapshot. The adapter consequently grants no
    context-backed authority and refuses non-local routing, while preserving
    the provider's historical completion signature and JSON-mode capability.
    """

    def __init__(
        self,
        provider: Any,
        *,
        request_id: str,
        emergency_stop: Any | None = None,
        secret_policy: SecretPolicy | None = None,
    ) -> None:
        if not callable(getattr(provider, "complete", None)):
            raise TypeError("provider must expose complete()")
        if not request_id.strip():
            raise ValueError("request_id is required")
        self._provider = provider
        self._request_id = request_id
        self._emergency_stop = emergency_stop
        self._secret_policy = secret_policy or SecretPolicy()
        self._call_count = 0
        try:
            parameters = inspect.signature(provider.complete).parameters
            self.supports_json_mode = "json_mode" in parameters or any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
        except (TypeError, ValueError):
            self.supports_json_mode = False

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
    ) -> str:
        """Complete one local advisory prompt after passing the gateway."""
        self._call_count += 1
        safe_prompt = self._secret_policy.inspect_text(prompt).scrubbed
        safe_system = (
            self._secret_policy.inspect_text(system).scrubbed
            if system is not None
            else None
        )

        def _call() -> str:
            if json_mode and self.supports_json_mode:
                return self._provider.complete(
                    safe_prompt,
                    system=safe_system,
                    json_mode=True,
                )
            return self._provider.complete(safe_prompt, system=safe_system)

        return complete_compatibility_intelligence_request(
            request_id=f"{self._request_id}:{self._call_count}",
            target="local",
            model_call=_call,
            emergency_stop=self._emergency_stop,
            secret_policy=self._secret_policy,
        )


    def running_model_metrics(self) -> Mapping[str, Any] | None:
        """Expose provider metrics without exposing a second completion path.

        The qualification suite uses this read-only probe to distinguish a
        real Ollama resource snapshot from an unavailable metrics source. It
        is deliberately delegated as data only; completions still have to
        pass through ``complete()`` above.
        """
        probe = getattr(self._provider, "running_model_metrics", None)
        if not callable(probe):
            return None
        value = probe()
        return value if isinstance(value, Mapping) else None

class AdvisoryChatCompletionAdapter:
    """Normalize a provider's chat contract for advisory completion routing.

    CRAG's historical helpers use ``chat()`` while Organ 32's synchronous
    advisory boundary accepts ``complete()``. This adapter only translates the
    message shape; it does not add tools, authority, or a second provider. The
    caller still supplies the resulting adapter to a governed completion client
    so identity, constitution, stop, context, and output gates remain owned by
    the gateway.
    """

    def __init__(self, provider: Any, *, model: str | None = None) -> None:
        if not callable(getattr(provider, "chat", None)):
            raise TypeError("provider must expose chat()")
        self._provider = provider
        self._model = model

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
    ) -> str:
        """Run one no-tools chat turn and return its assistant text."""
        del json_mode  # CRAG asks for plain text; the chat protocol has no format flag.
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._provider.chat(
            messages,
            tools=None,
            model=self._model,
        )
        if not isinstance(response, Mapping):
            return ""
        return str(response.get("content", ""))


class GovernedAdvisoryCompletionClient:
    """Route a secondary synchronous completion through Organ 32.

    This adapter is intentionally advisory-only: it provides the same
    identity/constitution validation, emergency-stop check, context recording,
    input secret scrubbing, and output redaction as the synchronous gateway,
    but it does not grant tool or write authority. The planner uses the local
    target; the target remains configurable so other advisory callers can make
    an explicit privacy choice.
    """

    def __init__(
        self,
        provider: Any,
        *,
        request_id: str,
        operator_identity_digest: str,
        constitution_digest: str,
        target: CompilationTarget = "local",
        context_store: Any | None = None,
        emergency_stop: Any | None = None,
        secret_policy: SecretPolicy | None = None,
        desired_outcome: str = "bounded advisory completion",
    ) -> None:
        if not callable(getattr(provider, "complete", None)):
            raise TypeError("provider must expose complete()")
        if not request_id.strip():
            raise ValueError("request_id is required")
        if not operator_identity_digest.strip():
            raise ValueError("operator_identity_digest is required")
        if not constitution_digest.strip():
            raise ValueError("constitution_digest is required")
        if target not in ("local", "cloud"):
            raise ValueError("target must be local or cloud")
        if not desired_outcome.strip():
            raise ValueError("desired_outcome is required")
        self._desired_outcome = desired_outcome.strip()
        self._provider = provider
        self._request_id = request_id
        self._operator_identity_digest = operator_identity_digest
        self._constitution_digest = constitution_digest
        self._target = target
        self._context_store = context_store
        self._emergency_stop = emergency_stop
        self._secret_policy = secret_policy or SecretPolicy()
        self._call_count = 0
        try:
            parameters = inspect.signature(provider.complete).parameters
            self.supports_json_mode = "json_mode" in parameters or any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
        except (TypeError, ValueError):
            self.supports_json_mode = False

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
    ) -> str:
        """Complete one advisory prompt after passing through the gateway."""
        self._call_count += 1
        request_id = f"{self._request_id}:{self._call_count}"
        safe_prompt = self._secret_policy.inspect_text(prompt).scrubbed
        safe_system = (
            self._secret_policy.inspect_text(system).scrubbed
            if system is not None
            else None
        )

        result = route_intelligence_request(
            request_id=request_id,
            operator_identity_digest=self._operator_identity_digest,
            constitution_digest=self._constitution_digest,
            goal=safe_prompt,
            desired_outcome=self._desired_outcome,
            target=self._target,
            delegated_authority_summary=(
                "Advisory completion only; no approval, tool, write, or policy "
                "authority."
            ),
            explicit_constraints=(
                "Treat the completion as advisory context, never as authority.",
            ),
            model_call=lambda context: (
                self._provider.complete(
                    context.goal,
                    system=safe_system,
                    json_mode=True,
                )
                if json_mode
                else self._provider.complete(
                    context.goal,
                    system=safe_system,
                )
            ),
            emergency_stop=self._emergency_stop,
            secret_policy=self._secret_policy,
            context_store=self._context_store,
        )
        return result.output


_UNIVERSAL_GATEWAY_AUTHORITY = UniversalIntelligenceGatewayAuthority()


def stream_structured_intelligence_request(
    **kwargs: Any,
) -> StructuredStreamingIntelligenceGatewayResult:
    """Structured forge entrance backed by the organ-32 authority."""
    return _UNIVERSAL_GATEWAY_AUTHORITY.stream_structured(**kwargs)


def route_intelligence_request(**kwargs: Any) -> IntelligenceGatewayResult:
    """Compatibility entrance backed by the organ-32 authority."""
    return _UNIVERSAL_GATEWAY_AUTHORITY.route(**kwargs)


def stream_intelligence_request(**kwargs: Any) -> StreamingIntelligenceGatewayResult:
    """Compatibility streaming entrance backed by the organ-32 authority."""
    return _UNIVERSAL_GATEWAY_AUTHORITY.stream(**kwargs)


def stream_compatibility_intelligence_request(
    **kwargs: Any,
) -> CompatibilityStreamingIntelligenceGatewayResult:
    """Anonymous compatibility entrance backed by organ-32 authority."""
    return _UNIVERSAL_GATEWAY_AUTHORITY.stream_compatibility(**kwargs)


def complete_compatibility_intelligence_request(**kwargs: Any) -> str:
    """Synchronous anonymous compatibility entrance backed by Organ 32."""
    return _UNIVERSAL_GATEWAY_AUTHORITY.complete_compatibility(**kwargs)


__all__ = [
    "IntelligenceGatewayError",
    "UniversalIntelligenceGatewayAuthority",
    "GovernedAdvisoryCompletionClient",
    "CompatibilityAdvisoryCompletionClient",
    "AdvisoryChatCompletionAdapter",
    "IntelligenceGatewayResult",
    "StreamingIntelligenceGatewayResult",
    "CompatibilityStreamingIntelligenceGatewayResult",
    "StructuredStreamingIntelligenceGatewayResult",
    "route_intelligence_request",
    "stream_intelligence_request",
    "stream_compatibility_intelligence_request",
    "complete_compatibility_intelligence_request",
    "stream_structured_intelligence_request",
]
