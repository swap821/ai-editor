"""Universal Intelligence Gateway pipeline (Slice 30).

This is the non-provider-specific half of "one universal gateway": identity/
constitution validation, representative-context compilation (Slice 29),
emergency-stop enforcement (Slice 27), and output secret redaction. It takes
the actual provider call as a caller-supplied `model_call` callback rather
than constructing a client itself -- so this module never needs to appear in
`tests/architecture/test_intelligence_boundary.py`'s allow-list, and adding a
new provider never requires touching this file.

Full scope note: this pipeline is not yet the mandatory entrance for every
model interaction in the codebase. See `docs/architecture/GAGOS_54_ORGANS.md`
organ 32 for the itemized list of call sites that still bypass it (ordinary
conversation, the agentic forge, Council Queens' currently-unwired LLM slots,
maintenance/skill-compilation, and reconciling this against the two other
pre-existing "gateway"-shaped implementations,
`aios.runtime.intelligence_gateway.IntelligenceGateway` and
`aios.application.models.hiring_service.IntelligenceHiringService`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from aios.application.intelligence.context_compiler import (
    CompilationTarget,
    compile_representative_context,
)
from aios.domain.intelligence.representative_context import RepresentativeContextV1
from aios.domain.memory.human_representation import (
    CorrectionRecordV1,
    OperatorPreferenceV1,
    ProjectPassportV1,
)
from aios.runtime.secret_policy import SecretPolicy

_LOGGER = logging.getLogger(__name__)


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
    plus a lazy, per-chunk-redacted stream of text. ``context`` is available
    right away specifically so a caller can emit a "route"/metadata frame
    before the first text chunk, matching the existing chat SSE wire shape.
    """

    context: RepresentativeContextV1
    chunks: Iterator[str]


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

    return compile_representative_context(
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


def route_intelligence_request(
    *,
    request_id: str,
    operator_identity_digest: str,
    constitution_digest: str,
    goal: str,
    desired_outcome: str,
    target: CompilationTarget,
    delegated_authority_summary: str,
    model_call: Callable[[RepresentativeContextV1], str],
    explicit_constraints: Sequence[str] = (),
    current_decisions: Sequence[str] = (),
    active_preferences: Sequence[OperatorPreferenceV1] = (),
    project_passport: ProjectPassportV1 | None = None,
    project_passport_stale: bool = False,
    relevant_memory_refs: Sequence[str] = (),
    permitted_tools: Sequence[str] = (),
    evidence_requirements: Sequence[str] = (),
    communication_mode: str = "direct",
    latest_correction: CorrectionRecordV1 | None = None,
    secret_policy: SecretPolicy | None = None,
    emergency_stop: Any | None = None,
    context_store: Any | None = None,
) -> IntelligenceGatewayResult:
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
    policy = secret_policy or SecretPolicy()
    context = _validate_and_compile(
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
        policy=policy,
        emergency_stop=emergency_stop,
    )
    _record_context(context, context_store)

    raw_output = model_call(context)
    decision = policy.inspect_text(raw_output)
    return IntelligenceGatewayResult(
        context=context,
        output=decision.scrubbed,
        secrets_redacted=decision.detected,
    )


def stream_intelligence_request(
    *,
    request_id: str,
    operator_identity_digest: str,
    constitution_digest: str,
    goal: str,
    desired_outcome: str,
    target: CompilationTarget,
    delegated_authority_summary: str,
    model_call: Callable[[RepresentativeContextV1], Iterable[str]],
    explicit_constraints: Sequence[str] = (),
    current_decisions: Sequence[str] = (),
    active_preferences: Sequence[OperatorPreferenceV1] = (),
    project_passport: ProjectPassportV1 | None = None,
    project_passport_stale: bool = False,
    relevant_memory_refs: Sequence[str] = (),
    permitted_tools: Sequence[str] = (),
    evidence_requirements: Sequence[str] = (),
    communication_mode: str = "direct",
    latest_correction: CorrectionRecordV1 | None = None,
    secret_policy: SecretPolicy | None = None,
    emergency_stop: Any | None = None,
    context_store: Any | None = None,
) -> StreamingIntelligenceGatewayResult:
    """Streaming counterpart to `route_intelligence_request()` for text-chunk
    model calls (chat's token-by-token reply). Same upfront governance --
    identity/constitution validation, emergency-stop check, representative-
    context compilation -- computed eagerly before any chunk is produced, so
    a refused request never starts a stream at all.

    Each chunk is redacted independently as it is produced, not after the
    full reply is buffered -- true token-by-token streaming is the entire
    point of this variant. This is an honest, real limitation, not a silent
    gap: per-chunk redaction cannot catch a secret whose bytes are split
    across a chunk boundary, so it is strictly an improvement over zero
    redaction (`aios.api.main._stream_chat_chunks`'s current behavior today),
    not an equivalent guarantee to `route_intelligence_request()`'s
    whole-text scan. A caller that needs the stronger guarantee should use
    the non-streaming pipeline instead.

    Organ 32 scope note: this variant covers plain-text chunk streams
    (chat's shape). The agentic forge's `ToolAgent.run()` yields structured
    tool-call events (`dict[str, Any]`), a genuinely different shape this
    variant does not cover -- deliberately not attempted in the same pass,
    per the operator-confirmed "streaming variant only" scope decision.

    `context_store` (organ 31): same durable, best-effort audit record as
    `route_intelligence_request()`, written once the context is compiled and
    before the first chunk is pulled.
    """
    policy = secret_policy or SecretPolicy()
    context = _validate_and_compile(
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
        policy=policy,
        emergency_stop=emergency_stop,
    )
    _record_context(context, context_store)

    def _redacted_chunks() -> Iterator[str]:
        for chunk in model_call(context):
            text = str(chunk)
            if text:
                yield policy.redact_text(text)

    return StreamingIntelligenceGatewayResult(context=context, chunks=_redacted_chunks())


__all__ = [
    "IntelligenceGatewayError",
    "IntelligenceGatewayResult",
    "StreamingIntelligenceGatewayResult",
    "route_intelligence_request",
    "stream_intelligence_request",
]
