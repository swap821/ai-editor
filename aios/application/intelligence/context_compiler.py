"""Compile one `RepresentativeContextV1` for a single model request
(Slice 29). This is the one place free-text fields get privacy-reviewed
before a provider-neutral context is handed to any intelligence adapter --
see `aios.runtime.intelligence_gateway` (Slice 27) for where the actual
provider call happens, and `aios.domain.governance.constitution` (Slice 26)
/ `aios.domain.memory.human_representation` (Slice 28) for the source
contracts this composes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any, Literal

from aios.domain.intelligence.representative_context import (
    PreferenceProjection,
    RepresentativeContextV1,
)
from aios.domain.memory.human_representation import (
    CorrectionRecordV1,
    OperatorPreferenceV1,
    ProjectPassportV1,
)
from aios.runtime.secret_policy import SecretPolicy

CompilationTarget = Literal["local", "cloud"]

#: Fields never included in a cloud projection regardless of content --
#: raw memory reference identifiers can themselves identify local-only
#: stored content, so they are withheld structurally, not merely scrubbed.
_CLOUD_FORBIDDEN_FIELDS: tuple[str, ...] = ("relevant_memory_refs",)


def _canonical_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _scrub(text: str, secret_policy: SecretPolicy) -> tuple[str, bool]:
    decision = secret_policy.inspect_text(text)
    return decision.scrubbed, decision.detected


def compile_representative_context(
    *,
    request_id: str,
    operator_identity_digest: str,
    constitution_digest: str,
    goal: str,
    desired_outcome: str,
    target: CompilationTarget,
    delegated_authority_summary: str,
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
) -> RepresentativeContextV1:
    """Compile a raw request + the current human-representation state into
    one immutable, digested `RepresentativeContextV1`.

    `target="cloud"` scrubs every free-text field through `SecretPolicy` and
    withholds `_CLOUD_FORBIDDEN_FIELDS` entirely; `target="local"` passes
    text through unscrubbed and permits those fields. This function does not
    decide *whether* cloud is allowed at all -- that is the existing
    `PrivacyPolicy`/`PrivacyDecision` boundary in `aios.domain.privacy.
    contracts`. It only decides what a context compiled *for* the already-
    permitted target may contain.
    """
    policy = secret_policy or SecretPolicy()
    uncertainty: list[str] = []

    # Only an active, non-superseded/rejected preference is ever projected;
    # a contradicted or superseded preference must never be silently used.
    active_only = [pref for pref in active_preferences if pref.status == "active"]

    current_decisions_list = list(current_decisions)
    if latest_correction is not None:
        # The human correction must be visible in the compiled packet, even
        # though it never grants authority by itself (CorrectionRecordV1.
        # grants_authority is pinned False).
        current_decisions_list.append(
            f"human correction applied (revision {latest_correction.correction_revision}"
            f", fields={list(latest_correction.corrected_fields)})"
        )

    if project_passport is not None and project_passport_stale:
        uncertainty.append(
            "project passport is stale relative to the commit under evaluation"
        )

    if target == "cloud":
        goal_out, goal_detected = _scrub(goal, policy)
        outcome_out, outcome_detected = _scrub(desired_outcome, policy)
        constraints_out = []
        constraints_detected = False
        for item in explicit_constraints:
            scrubbed, detected = _scrub(item, policy)
            constraints_out.append(scrubbed)
            constraints_detected = constraints_detected or detected
        decisions_out = []
        decisions_detected = False
        for item in current_decisions_list:
            scrubbed, detected = _scrub(item, policy)
            decisions_out.append(scrubbed)
            decisions_detected = decisions_detected or detected

        preferences_out = []
        preferences_detected = False
        for pref in active_only:
            value_text = str(pref.value)
            scrubbed_value, detected = _scrub(value_text, policy)
            preferences_detected = preferences_detected or detected
            preferences_out.append(
                PreferenceProjection(
                    domain=pref.domain,
                    key=pref.key,
                    value=scrubbed_value if detected else pref.value,
                    confidence=pref.confidence,
                )
            )

        any_redaction = (
            goal_detected
            or outcome_detected
            or constraints_detected
            or decisions_detected
            or preferences_detected
        )
        cloud_allowed_fields = tuple(
            name
            for name in (
                "goal",
                "desired_outcome",
                "explicit_constraints",
                "current_decisions",
                "approved_preferences",
                "project_passport_digest",
                "communication_mode",
            )
            if name not in _CLOUD_FORBIDDEN_FIELDS
        )
        forbidden_fields = _CLOUD_FORBIDDEN_FIELDS
        if any_redaction:
            uncertainty.append("one or more fields were redacted for the cloud target")

        goal_final, outcome_final = goal_out, outcome_out
        constraints_final = tuple(constraints_out)
        decisions_final = tuple(decisions_out)
        preferences_final = tuple(preferences_out)
        memory_refs_final: tuple[str, ...] = ()
    else:
        cloud_allowed_fields = ()
        forbidden_fields = ()
        goal_final, outcome_final = goal, desired_outcome
        constraints_final = tuple(explicit_constraints)
        decisions_final = tuple(current_decisions_list)
        preferences_final = tuple(
            PreferenceProjection(
                domain=pref.domain,
                key=pref.key,
                value=pref.value,
                confidence=pref.confidence,
            )
            for pref in active_only
        )
        memory_refs_final = tuple(relevant_memory_refs)

    digest_payload: dict[str, Any] = {
        "request_id": request_id,
        "operator_identity_digest": operator_identity_digest,
        "constitution_digest": constitution_digest,
        "goal": goal_final,
        "desired_outcome": outcome_final,
        "explicit_constraints": list(constraints_final),
        "current_decisions": list(decisions_final),
        "approved_preferences": [
            {"domain": p.domain, "key": p.key, "value": p.value, "confidence": p.confidence}
            for p in preferences_final
        ],
        "project_passport_digest": (
            project_passport.passport_digest if project_passport is not None else None
        ),
        "relevant_memory_refs": list(memory_refs_final),
        "privacy_classification": target,
        "cloud_allowed_fields": list(cloud_allowed_fields),
        "forbidden_fields": list(forbidden_fields),
        "delegated_authority_summary": delegated_authority_summary,
        "permitted_tools": list(permitted_tools),
        "evidence_requirements": list(evidence_requirements),
        "communication_mode": communication_mode,
        "uncertainty": sorted(uncertainty),
    }
    context_digest = _canonical_digest(digest_payload)

    return RepresentativeContextV1(
        request_id=request_id,
        operator_identity_digest=operator_identity_digest,
        constitution_digest=constitution_digest,
        goal=goal_final,
        desired_outcome=outcome_final,
        explicit_constraints=constraints_final,
        current_decisions=decisions_final,
        approved_preferences=preferences_final,
        project_passport_digest=(
            project_passport.passport_digest if project_passport is not None else None
        ),
        relevant_memory_refs=memory_refs_final,
        privacy_classification=target,
        cloud_allowed_fields=cloud_allowed_fields,
        forbidden_fields=forbidden_fields,
        delegated_authority_summary=delegated_authority_summary,
        permitted_tools=tuple(permitted_tools),
        evidence_requirements=tuple(evidence_requirements),
        communication_mode=communication_mode,
        uncertainty=tuple(sorted(uncertainty)),
        context_digest=context_digest,
    )


__all__ = ["CompilationTarget", "compile_representative_context"]
