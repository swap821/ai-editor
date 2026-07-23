"""Organ 39: gathers a real, independent second opinion on a completed
mission's King recommendation and synthesizes a durable `DeliberationRecord`.

`aios.application.intelligence.deliberation` (Slice 34) already has three
correct, tested, pure functions (`should_trigger_deliberation`,
`verify_independence`, `synthesize_deliberation`) but -- confirmed by grep --
zero production callers anywhere: nothing ever gathers a real `ModelPosition`
from an actual provider. This module is that gather step.

Deliberately decoupled from `CouncilOrchestrator.run()`'s own control flow:
`maybe_deliberate()` is a best-effort side call the orchestrator makes
AFTER a mission's `KingReport` already exists, wrapped in the orchestrator's
own try/except so a deliberation failure (a flaky second provider, a
malformed response) can never affect the mission's own recommendation or
completion -- the same "advisory only, never blocks completion" posture
`reason_king()` already established for the King's own reasoning.

Trigger flags are derived ONLY from data the mission itself already
computed (the King's clamped recommendation, real Queen verdict
disagreement) -- never a new heuristic invented here.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Callable, Optional, Sequence

from aios.application.intelligence.deliberation import (
    DeliberationError,
    should_trigger_deliberation,
    synthesize_deliberation,
    verify_independence,
)
from aios.domain.intelligence.deliberation import (
    DeliberationRecord,
    DeliberationRole,
    ModelPosition,
)
from aios.runtime.contracts import KingReport

logger = logging.getLogger(__name__)

#: Block-tier recommendations (matches king_reasoning.py's own _CAUTION_RANK
#: >= 1 boundary) -- a real, already-computed signal, not a new heuristic.
_BLOCK_TIER_RECOMMENDATIONS = frozenset({"revise", "rollback", "reject"})

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_DISSENT_ROLES = (
    DeliberationRole(role="primary", provider_requirements=(), independence_required=True),
    DeliberationRole(role="critic", provider_requirements=(), independence_required=True),
)


#: Blocking verdicts, matching build_king_report()'s own definition
#: (aios/runtime/king_report.py) exactly -- not raw string inequality.
#: Queens legitimately use different non-blocking vocabulary for the same
#: "fine, proceed" outcome (e.g. reflection.py's "allow_with_approval"
#: alongside plain "allow" elsewhere), so any two different verdict
#: STRINGS is not itself disagreement.
_BLOCKING_VERDICTS = frozenset({"deny", "defer"})


def _derive_trigger(report: KingReport) -> tuple[bool, tuple[str, ...]]:
    """Real signals only: the King's own clamped recommendation is block-tier,
    or the real Queen verdicts genuinely split -- some blocking, some not."""
    verdicts = report.council_summary.get("council_verdicts", [])
    verdict_values = [
        v.get("verdict") for v in verdicts if isinstance(v, dict) and v.get("verdict")
    ]
    blocking = any(v in _BLOCKING_VERDICTS for v in verdict_values)
    non_blocking = any(v not in _BLOCKING_VERDICTS for v in verdict_values)
    return should_trigger_deliberation(
        high_consequence=report.recommendation in _BLOCK_TIER_RECOMMENDATIONS,
        conflicting_evidence=blocking and non_blocking,
    )


def _build_dissent_prompt(report: KingReport) -> str:
    return (
        "You are an independent reviewer for an AI council. Another reviewer "
        f"(the King) recommended '{report.recommendation}' for this mission.\n"
        f"Mission: {report.mission}\n"
        f"King's summary: {report.human_summary}\n\n"
        "Independently assess this mission. Reply with EXACTLY one JSON object "
        "(no other text) with these keys:\n"
        '  "answer": your own recommendation, one of '
        '"approve"|"observe"|"revise"|"rollback"|"reject"\n'
        '  "confidence": your confidence in that answer, a number from 0.0 to 1.0\n'
        '  "security_concerns": a list of strings, any real security concerns '
        "you see (empty list if none)\n"
        '  "unresolved_questions": a list of strings, any real open questions '
        "(empty list if none)"
    )


def _parse_dissent_position(
    raw: str, *, provider: str, exact_model_id: str
) -> Optional[ModelPosition]:
    """Parse the dissent reviewer's JSON reply into a real ModelPosition.
    Fail-closed: any parse/validation failure returns None (matches
    reason_king()'s own "unparseable output -> ignore" posture) -- a
    malformed dissent never fabricates a position."""
    if not raw:
        return None
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    answer = payload.get("answer")
    confidence = payload.get("confidence")
    if not isinstance(answer, str) or not answer.strip():
        return None
    if not isinstance(confidence, (int, float)):
        return None
    confidence = max(0.0, min(1.0, float(confidence)))
    concerns = payload.get("security_concerns")
    questions = payload.get("unresolved_questions")
    try:
        return ModelPosition(
            role="critic",
            provider=provider,
            exact_model_id=exact_model_id,
            answer=answer.strip(),
            confidence=confidence,
            security_concerns=tuple(concerns) if isinstance(concerns, list) else (),
            unresolved_questions=tuple(questions) if isinstance(questions, list) else (),
        )
    except Exception:  # noqa: BLE001 - a malformed field must never raise here
        return None


def maybe_deliberate(
    report: KingReport,
    *,
    mission_id: str,
    king_provider: str,
    king_exact_model_id: str,
    dissent_complete: Optional[Callable[[str], str]],
    dissent_provider: str,
    dissent_exact_model_id: str,
) -> Optional[DeliberationRecord]:
    """Gather a real, independent second opinion and synthesize a durable
    `DeliberationRecord`, or return None when deliberation isn't warranted,
    no dissent reviewer is configured, or the dissent call fails/is
    unparseable. Never raises -- the caller wraps this best-effort anyway,
    but every internal failure already degrades to None on its own.
    """
    if dissent_complete is None:
        return None
    triggered, reasons = _derive_trigger(report)
    if not triggered:
        return None

    king_position = ModelPosition(
        role="primary",
        provider=king_provider,
        exact_model_id=king_exact_model_id,
        answer=report.recommendation,
        confidence=1.0 if report.recommendation in _BLOCK_TIER_RECOMMENDATIONS else 0.5,
        security_concerns=(),
    )

    try:
        raw = dissent_complete(_build_dissent_prompt(report))
    except Exception:  # noqa: BLE001 - a flaky dissent provider must never raise
        logger.warning("Deliberation dissent call failed", exc_info=True)
        return None

    dissent_position = _parse_dissent_position(
        raw, provider=dissent_provider, exact_model_id=dissent_exact_model_id
    )
    if dissent_position is None:
        return None

    positions: Sequence[ModelPosition] = (king_position, dissent_position)
    violations = verify_independence(positions, _DISSENT_ROLES)
    if violations:
        logger.warning("Deliberation independence violated: %s", violations)
        return None

    try:
        return synthesize_deliberation(
            deliberation_id=f"deliberation-{uuid.uuid4().hex}",
            trigger_reasons=reasons,
            positions=positions,
            final_disposition=report.recommendation,
            mission_id=mission_id,
        )
    except DeliberationError:
        return None


__all__ = ["maybe_deliberate"]
