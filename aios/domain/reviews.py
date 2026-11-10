"""One vocabulary for a review of a change (2026-11-10).

The consistency plan of 2026-11-04 asked for the council's Critique queen and
GAGOS's workshop reviewer to share one verdict schema. They ask different
questions -- the queen, deterministically, whether a passing verification was
earned; the reviewer, a model, whether a change does what it should and
nothing else -- so neither replaces the other. What they share is here: one
schema a reviewer answers in, one reading of it, and one mapping of a queen's
verdict onto the same words, so the workshop can carry the council's word next
to its reviewer's (advisory only: Codex's design conditions of 2026-11-02, "a
council cross-check is advisory and cannot replace dual review or grant
authority").

Pure: no I/O, no imports from other layers.
"""

from __future__ import annotations

import json
from typing import Any

#: What a deciding reviewer may say.
REVIEW_VERDICTS: tuple[str, ...] = ("accept", "reject")
#: What an advisory reviewer may say: also that it would wait for more.
ADVISORY_VERDICTS: tuple[str, ...] = ("accept", "defer", "reject")

#: The schema a deciding reviewer answers in (its CLI is held to it).
REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(REVIEW_VERDICTS)},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}

#: A council queen's verdict, in the review vocabulary.
_QUEEN_TO_REVIEW: dict[str, str] = {
    "allow": "accept",
    "allow_with_approval": "defer",
    "defer": "defer",
    "deny": "reject",
}


def parse_review(raw: object) -> tuple[str, str]:
    """``(verdict, reason)`` from a deciding reviewer's structured output, or
    ``ValueError`` when it is not one."""
    value = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(value, dict):
        raise ValueError("review is not an object")
    verdict, reason = value.get("verdict"), value.get("reason")
    if verdict not in REVIEW_VERDICTS or not isinstance(reason, str):
        raise ValueError(f"review has no valid verdict: {value!r}"[:300])
    return verdict, reason.strip()


def queen_review(verdict: Any) -> tuple[str, str]:
    """A council queen's verdict (anything with ``verdict`` and ``reason``, such
    as :class:`aios.runtime.contracts.QueenVerdict`) as ``(advisory verdict,
    reason)``. An unknown queen word is ``defer``: it never reads as consent."""
    word = _QUEEN_TO_REVIEW.get(str(getattr(verdict, "verdict", "")), "defer")
    return word, str(getattr(verdict, "reason", "") or "").strip()


__all__ = [
    "ADVISORY_VERDICTS",
    "REVIEW_SCHEMA",
    "REVIEW_VERDICTS",
    "parse_review",
    "queen_review",
]
