"""The skill envelope authority: the operator's standing signature for skills.

The terms and their rules are :mod:`aios.domain.capabilities.skill_envelope`;
this authority signs a skill envelope for a privileged operator, admits
GAGOS's skill activations into it one at a time, and says plainly why it
refuses one. The skill's own rules -- a candidate, review-ready, never a
suspended skill -- are the learning service's
(:meth:`aios.application.learning.service.LearningService.activate_skill_within_envelope`),
which asks this authority for the place only once they hold.

What it will not do, as the mission envelope will not
(:mod:`aios.application.capabilities.envelope`):

* sign for anyone but a privileged operator (a recent strong
  re-authentication) with a recorded authentication event;
* admit an activation whose originator is the operator who signed: the
  principal that requests is never the one that authorises (INVARIANT III);
* admit anything with no emergency stop wired, with the stop engaged, or once
  the stop has engaged at any time since the envelope was signed;
* admit past the envelope's activations or its expiry, or the same skill
  version twice.
"""

from __future__ import annotations

import re
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aios.application.capabilities.envelope import EnvelopeRefused, stop_generation
from aios.domain.capabilities.skill_envelope import (
    SkillEnvelopeError,
    SkillEnvelopeTerms,
    activation_digest,
)
from aios.infrastructure.capabilities.skill_envelope_store import SkillEnvelopeStore

_SKILL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,255}$")
_BOUNDARY = "gagos-skill-envelope"


class SkillEnvelopeRefused(EnvelopeRefused):
    """The skill envelope authority refused; the message says why."""


@dataclass(frozen=True)
class SkillEnvelope:
    envelope_id: str
    operator_id: str
    terms: SkillEnvelopeTerms
    terms_digest: str
    stop_generation: int
    issued_at: float
    expires_at: float
    revoked_at: float | None
    revoked_reason: str | None
    used: int

    def describe(self) -> dict[str, Any]:
        return {
            "envelopeId": self.envelope_id,
            "terms": self.terms.as_payload(),
            "termsDigest": self.terms_digest,
            "issuedAt": self.issued_at,
            "expiresAt": self.expires_at,
            "activationsUsed": self.used,
            "activationsLeft": max(self.terms.max_activations - self.used, 0),
        }


@dataclass(frozen=True)
class SkillEnvelopeAdmission:
    """One skill activation's consumed place: what its record names."""

    envelope_id: str
    terms_digest: str
    activation: int
    of: int
    skill_id: str
    version: int
    originator: str
    operator_id: str
    authentication_event_id: str
    activation_digest: str

    def reason(self) -> str:
        return (
            f"Activated within the operator's skill envelope {self.envelope_id} "
            f"(terms {self.terms_digest[:12]}), activation {self.activation} of {self.of}"
        )


class SkillEnvelopeAuthority:
    """Sign, admit into, and revoke GAGOS's standing skill envelope."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        emergency_stop: Any | None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = SkillEnvelopeStore(db_path)
        self.emergency_stop = emergency_stop
        self.clock = clock

    def _stop_generation(self) -> int:
        try:
            return stop_generation(self.emergency_stop, boundary=_BOUNDARY)
        except EnvelopeRefused as exc:
            raise SkillEnvelopeRefused(str(exc)) from exc

    # -- reading ----------------------------------------------------------

    def _from_row(self, row: dict[str, Any]) -> SkillEnvelope:
        return SkillEnvelope(
            envelope_id=row["envelope_id"],
            operator_id=row["operator_id"],
            terms=SkillEnvelopeTerms.from_payload(row["terms"]),
            terms_digest=row["terms_digest"],
            stop_generation=int(row["stop_generation"]),
            issued_at=float(row["issued_at"]),
            expires_at=float(row["expires_at"]),
            revoked_at=row["revoked_at"],
            revoked_reason=row["revoked_reason"],
            used=self.store.used(row["envelope_id"]),
        )

    def _why_not_live(self, envelope: SkillEnvelope | None) -> str | None:
        if envelope is None:
            return "the operator has not signed a skill envelope"
        if envelope.revoked_at is not None:
            return f"the skill envelope was ended: {envelope.revoked_reason}"
        if self.clock() >= envelope.expires_at:
            return "the skill envelope has expired"
        try:
            generation = self._stop_generation()
        except SkillEnvelopeRefused as exc:
            return str(exc)
        if generation != envelope.stop_generation:
            return "the emergency stop engaged after the skill envelope was signed"
        return None

    def live(self) -> SkillEnvelope | None:
        """The skill envelope GAGOS may activate in now, or None."""
        row = self.store.latest()
        envelope = self._from_row(row) if row else None
        return envelope if self._why_not_live(envelope) is None else None

    def status(self) -> dict[str, Any]:
        """For the operator: the live skill envelope, or why there is none."""
        row = self.store.latest()
        envelope = self._from_row(row) if row else None
        why = self._why_not_live(envelope)
        if why is None and envelope is not None:
            return {"live": True, **envelope.describe()}
        return {"live": False, "reason": why}

    # -- the operator's acts ------------------------------------------------

    def sign(self, terms: SkillEnvelopeTerms, *, principal: Any) -> SkillEnvelope:
        """Sign *terms* for a privileged operator; any earlier one ends."""
        if str(getattr(principal, "principal_type", "")) != "operator":
            raise SkillEnvelopeRefused("only the operator signs a skill envelope")
        if getattr(principal, "authentication_level", "") != "privileged":
            raise SkillEnvelopeRefused(
                "signing a skill envelope needs a recent strong re-authentication"
            )
        event = str(getattr(principal, "authentication_event_id", "") or "")
        if not event:
            raise SkillEnvelopeRefused(
                "signing a skill envelope needs a recorded authentication"
            )
        generation = self._stop_generation()
        now = self.clock()
        row = {
            "envelope_id": f"skill-envelope-{uuid.uuid4().hex[:16]}",
            "operator_id": str(principal.principal_id),
            "authentication_event_id": event,
            "session_id": str(getattr(principal, "session_id", "") or ""),
            "terms": terms.as_payload(),
            "terms_digest": terms.digest(),
            "stop_generation": generation,
            "issued_at": now,
            "expires_at": now + terms.days * 86400,
        }
        self.store.insert(row, now=now)
        return self._from_row({**row, "revoked_at": None, "revoked_reason": None})

    def revoke(
        self, *, principal: Any, reason: str = "revoked by the operator"
    ) -> bool:
        """End the current skill envelope; True when one was live to end."""
        if str(getattr(principal, "principal_type", "")) != "operator":
            raise SkillEnvelopeRefused("only the operator ends a skill envelope")
        row = self.store.latest()
        if row is None:
            return False
        return self.store.revoke(row["envelope_id"], now=self.clock(), reason=reason)

    # -- GAGOS's requests ---------------------------------------------------

    def admit(
        self, *, skill_id: str, version: int, originator: str
    ) -> SkillEnvelopeAdmission:
        """Take one activation of the live skill envelope for *skill_id* at
        *version*, or :class:`SkillEnvelopeRefused` saying why it is outside."""
        if not _SKILL_ID.match(str(skill_id or "")):
            raise SkillEnvelopeRefused(f"not a skill id: {skill_id!r}")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise SkillEnvelopeRefused(f"not a skill version: {version!r}")
        originator = str(originator or "").strip()
        if not originator:
            raise SkillEnvelopeRefused("an activation names who originates it")
        row = self.store.latest()
        envelope = self._from_row(row) if row else None
        why = self._why_not_live(envelope)
        if why is not None or envelope is None:
            raise SkillEnvelopeRefused(why or "no live skill envelope")
        if originator == envelope.operator_id:
            raise SkillEnvelopeRefused(
                "the operator who signed the skill envelope cannot originate inside it"
            )

        def digest(activation: int) -> str:
            return activation_digest(
                envelope_id=envelope.envelope_id,
                terms_digest=envelope.terms_digest,
                activation=activation,
                skill_id=skill_id,
                version=version,
            )

        try:
            activation = self.store.reserve(
                envelope_id=envelope.envelope_id,
                max_activations=envelope.terms.max_activations,
                clock=self.clock,
                skill_id=skill_id,
                version=version,
                originator=originator,
                digest_for=digest,
            )
        except sqlite3.IntegrityError as exc:
            raise SkillEnvelopeRefused(
                f"{skill_id}@{version} is already activated inside this envelope"
            ) from exc
        if activation == "ended":
            raise SkillEnvelopeRefused(
                "the skill envelope ended while the activation was being taken"
            )
        if activation == "taken":
            raise SkillEnvelopeRefused(
                f"{skill_id}@{version} is already activated inside this envelope"
            )
        if activation == "full":
            raise SkillEnvelopeRefused(
                f"the skill envelope's {envelope.terms.max_activations} activations are used"
            )
        # A stop engaged while the place was being taken voids it: the place
        # stays spent, and the activation is refused.
        why = self._why_not_live(envelope)
        if why is not None:
            raise SkillEnvelopeRefused(f"{why}; the activation just taken is void")
        if not isinstance(activation, int):
            raise SkillEnvelopeRefused(
                f"the skill envelope's store answered {activation!r}"
            )
        signer = self.store.envelope(envelope.envelope_id) or {}
        return SkillEnvelopeAdmission(
            envelope_id=envelope.envelope_id,
            terms_digest=envelope.terms_digest,
            activation=activation,
            of=envelope.terms.max_activations,
            skill_id=skill_id,
            version=version,
            originator=originator,
            operator_id=envelope.operator_id,
            authentication_event_id=str(signer.get("authentication_event_id", "")),
            activation_digest=digest(activation),
        )


__all__ = [
    "SkillEnvelope",
    "SkillEnvelopeAdmission",
    "SkillEnvelopeAuthority",
    "SkillEnvelopeError",
    "SkillEnvelopeRefused",
]
