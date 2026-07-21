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

from collections.abc import Callable, Sequence
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


class IntelligenceGatewayError(RuntimeError):
    """Raised when the gateway itself refuses a request (not a provider error)."""


@dataclass(frozen=True, slots=True)
class IntelligenceGatewayResult:
    """The final, redacted result of one gateway-routed model call."""

    context: RepresentativeContextV1
    output: str
    secrets_redacted: bool


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
    """
    if not operator_identity_digest.strip():
        raise IntelligenceGatewayError("operator_identity_digest is required")
    if not constitution_digest.strip():
        raise IntelligenceGatewayError("constitution_digest is required")
    if emergency_stop is not None:
        emergency_stop.assert_operational()

    policy = secret_policy or SecretPolicy()
    context = compile_representative_context(
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

    raw_output = model_call(context)
    decision = policy.inspect_text(raw_output)
    return IntelligenceGatewayResult(
        context=context,
        output=decision.scrubbed,
        secrets_redacted=decision.detected,
    )


__all__ = [
    "IntelligenceGatewayError",
    "IntelligenceGatewayResult",
    "route_intelligence_request",
]
