"""Multi-Model Deliberation and Dissent application logic (Slice 34).

Three small, deterministic pieces: deciding *whether* deliberation is
warranted at all (never for every trivial task), checking that roles
marked `independence_required` actually come from different providers, and
synthesizing a `DeliberationRecord` whose `unresolved_minority_concerns` is
*derived* from every position's reported security concerns -- so a
synthesis step can summarise disagreement but can never silently drop a
minority finding.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from aios.domain.intelligence.deliberation import (
    DeliberationRecord,
    DeliberationRole,
    ModelPosition,
)


class DeliberationError(RuntimeError):
    """Raised when a deliberation cannot proceed truthfully."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def should_trigger_deliberation(
    *,
    high_consequence: bool = False,
    low_primary_confidence: bool = False,
    architectural_change: bool = False,
    security_sensitive_change: bool = False,
    conflicting_evidence: bool = False,
    expensive_promotion: bool = False,
    constitutional_proposal: bool = False,
) -> tuple[bool, tuple[str, ...]]:
    """Whether this task warrants the cost of independent deliberation, and
    exactly why -- not a single opaque bool, so the decision is auditable."""
    reasons = tuple(
        name
        for name, flag in (
            ("high_consequence", high_consequence),
            ("low_primary_confidence", low_primary_confidence),
            ("architectural_change", architectural_change),
            ("security_sensitive_change", security_sensitive_change),
            ("conflicting_evidence", conflicting_evidence),
            ("expensive_promotion", expensive_promotion),
            ("constitutional_proposal", constitutional_proposal),
        )
        if flag
    )
    return bool(reasons), reasons


def verify_independence(
    positions: Sequence[ModelPosition], roles: Sequence[DeliberationRole]
) -> tuple[str, ...]:
    """Return every independence violation: two positions in roles that both
    require independence but share the same provider."""
    role_by_name = {role.role: role for role in roles}
    violations: list[str] = []
    provider_to_role: dict[str, str] = {}
    for position in positions:
        role = role_by_name.get(position.role)
        if role is None or not role.independence_required:
            continue
        if position.provider in provider_to_role:
            violations.append(
                f"{position.role} and {provider_to_role[position.provider]} "
                f"both use provider {position.provider!r}, violating "
                "independence_required"
            )
        else:
            provider_to_role[position.provider] = position.role
    return tuple(violations)


def _detect_disagreements(positions: Sequence[ModelPosition]) -> tuple[str, ...]:
    distinct_answers = {position.answer.strip().lower() for position in positions}
    if len(distinct_answers) <= 1:
        return ()
    return tuple(
        f"{position.role} ({position.provider}/{position.exact_model_id}): "
        f"{position.answer}"
        for position in positions
    )


def synthesize_deliberation(
    *,
    deliberation_id: str,
    trigger_reasons: Sequence[str],
    positions: Sequence[ModelPosition],
    final_disposition: str,
    mission_id: str | None = None,
    resolved_security_concerns: Sequence[str] = (),
    minimum_participants: int = 2,
) -> DeliberationRecord:
    """Build the durable deliberation record. Refuses (rather than silently
    degrading to a single-model "deliberation") if fewer than
    `minimum_participants` real positions were actually gathered -- this is
    the truthful-degradation path for a cloud outage or an unreachable
    required participant."""
    if len(positions) < minimum_participants:
        raise DeliberationError(
            f"deliberation requires at least {minimum_participants} independent "
            f"positions, got {len(positions)}"
        )

    disagreements = _detect_disagreements(positions)
    all_security_concerns = sorted(
        {concern for position in positions for concern in position.security_concerns}
    )
    resolved = set(resolved_security_concerns)
    unresolved_minority_concerns = tuple(
        concern for concern in all_security_concerns if concern not in resolved
    )
    created_at = _utc_now()

    digest_payload = {
        "deliberation_id": deliberation_id,
        "mission_id": mission_id,
        "trigger_reasons": sorted(trigger_reasons),
        "positions": [position.as_dict() for position in positions],
        "disagreements": list(disagreements),
        "unresolved_minority_concerns": list(unresolved_minority_concerns),
        "final_disposition": final_disposition,
    }
    digest = _canonical_digest(digest_payload)

    return DeliberationRecord(
        deliberation_id=deliberation_id,
        mission_id=mission_id,
        trigger_reasons=tuple(trigger_reasons),
        positions=tuple(positions),
        disagreements=disagreements,
        unresolved_minority_concerns=unresolved_minority_concerns,
        final_disposition=final_disposition,
        created_at=created_at,
        deliberation_digest=digest,
    )


def blocks_promotion(record: DeliberationRecord) -> bool:
    """A minority security concern that was never resolved blocks promotion
    until it is -- resolving means re-synthesizing with it listed in
    `resolved_security_concerns`, never silently ignoring it."""
    return bool(record.unresolved_minority_concerns)


__all__ = [
    "DeliberationError",
    "blocks_promotion",
    "should_trigger_deliberation",
    "synthesize_deliberation",
    "verify_independence",
]
