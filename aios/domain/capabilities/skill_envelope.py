"""GAGOS's standing skill envelope: the operator's signature for its skills.

The operator's decision (2026-11-18): he should not be asked to activate each
new skill. He signs a skill envelope once, for a period; inside it, every skill
the library calls review-ready
(:func:`aios.application.memory.institutional_skills.is_review_ready`, the one
derivation) is activated by GAGOS's hour, and the activation names the envelope
and the operator who signed it. A capability of its own kind, like the mission
envelope (:mod:`aios.domain.capabilities.envelope`):

* signed by a privileged operator (a recent strong re-authentication), never by
  GAGOS, so the principal that requests an activation is never the one that
  authorises it (INVARIANT III);
* holding a fixed number of activations; each consumes one, atomically, and
  its record names the envelope and the activation, never his click;
* ended by expiry, by his revocation, by a newer skill envelope, or by any
  engagement of the emergency stop after it was signed;
* never reaching a suspended skill: a skill the machine withdrew comes back
  only by his own re-activation (operator decision, 2026-09-29).

This module holds the terms and their rules only. It reads no store and calls
nothing; :mod:`aios.application.capabilities.skill_envelope` is the authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aios.domain.capabilities.digest import payload_digest

#: The longest a skill envelope may live, in days.
MAX_DAYS = 30
#: The most activations one skill envelope may hold.
MAX_ACTIVATIONS = 100


class SkillEnvelopeError(ValueError):
    """Terms that cannot be a skill envelope."""


def _whole(value: Any, name: str, top: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SkillEnvelopeError(f"{name} must be a whole number")
    if not 1 <= value <= top:
        raise SkillEnvelopeError(f"{name} must be 1 to {top}")
    return value


@dataclass(frozen=True)
class SkillEnvelopeTerms:
    """What the operator signs: how long, and how many activations."""

    days: int
    max_activations: int

    @classmethod
    def build(cls, *, days: int, max_activations: int) -> "SkillEnvelopeTerms":
        return cls(
            _whole(days, "days", MAX_DAYS),
            _whole(max_activations, "max_activations", MAX_ACTIVATIONS),
        )

    def as_payload(self) -> dict[str, Any]:
        return {"days": self.days, "max_activations": self.max_activations}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SkillEnvelopeTerms":
        return cls.build(
            days=payload["days"], max_activations=payload["max_activations"]
        )

    def digest(self) -> str:
        return payload_digest({"kind": "skill-envelope", **self.as_payload()})


def activation_digest(
    *,
    envelope_id: str,
    terms_digest: str,
    activation: int,
    skill_id: str,
    version: int,
) -> str:
    """The digest a skill's activation records for the place it consumed."""
    return payload_digest(
        {
            "envelope_id": envelope_id,
            "terms_digest": terms_digest,
            "activation": activation,
            "skill_id": skill_id,
            "version": version,
        }
    )


__all__ = [
    "MAX_ACTIVATIONS",
    "MAX_DAYS",
    "SkillEnvelopeError",
    "SkillEnvelopeTerms",
    "activation_digest",
]
