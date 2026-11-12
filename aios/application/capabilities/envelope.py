"""Organ 9's envelope authority: GAGOS's daily envelope, signed by the operator.

The terms and their rules are :mod:`aios.domain.capabilities.envelope`; this
authority signs an envelope for a privileged operator, admits GAGOS's missions
into it one slot at a time, and says plainly why it refuses one.

What it will not do:

* sign for anyone but a privileged operator (a recent strong
  re-authentication) with a recorded authentication event;
* admit a mission whose originator is the operator who signed: the principal
  that requests is never the one that authorises (INVARIANT III);
* admit anything with no emergency stop wired, with the stop engaged, or once
  the stop has engaged at any time since the envelope was signed -- a stop
  ends the envelope, and only a new signature starts another;
* admit past the envelope's slots, its expiry, its folders or its kinds.
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

from aios.application.capabilities.authority import EmergencyStopHardWiringAuthority
from aios.domain.capabilities.envelope import (
    EnvelopeError,
    EnvelopeTerms,
    normalise_path,
    slot_digest,
)
from aios.infrastructure.capabilities.envelope_store import EnvelopeStore

_MISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BOUNDARY = "gagos-envelope"


class EnvelopeRefused(RuntimeError):
    """The envelope authority refused; the message says why."""


@dataclass(frozen=True)
class Envelope:
    envelope_id: str
    operator_id: str
    terms: EnvelopeTerms
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
            "missionsUsed": self.used,
            "missionsLeft": max(self.terms.max_missions - self.used, 0),
        }


@dataclass(frozen=True)
class EnvelopeSlot:
    """One mission's consumed slot: what its approval records."""

    envelope_id: str
    terms_digest: str
    slot: int
    of: int
    mission_id: str
    originator: str
    kind: str
    files: tuple[str, ...]
    slot_digest: str

    def approval_reason(self) -> str:
        return (
            f"Approved within the operator's envelope {self.envelope_id} "
            f"(terms {self.terms_digest[:12]}), slot {self.slot} of {self.of}"
        )


class EnvelopeAuthority:
    """Sign, admit into, and revoke GAGOS's daily envelope."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        emergency_stop: Any | None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = EnvelopeStore(db_path)
        self.emergency_stop = emergency_stop
        self.clock = clock

    # -- the stop ---------------------------------------------------------

    def _stop_generation(self) -> int:
        """The stop's generation now; refuses when no stop is wired or it is
        engaged. An envelope is never ungoverned: not even a test fixture's
        deliberate "ungoverned" stands in for a real latch here."""
        stop = self.emergency_stop
        state = getattr(stop, "state", None)
        if stop is None or not callable(state):
            raise EnvelopeRefused("no emergency stop is wired, so no envelope can hold")
        try:
            EmergencyStopHardWiringAuthority.assert_operational(
                stop, boundary=_BOUNDARY
            )
            # ONE snapshot decides both: engaged, and which generation. Codex's
            # review of 58834665: read apart, a stop engaged between the check
            # and the read was recorded as the envelope's own generation, so
            # the envelope survived the stop's clearing.
            snapshot = state()
        except Exception as exc:  # noqa: BLE001 - every stop failure refuses
            raise EnvelopeRefused(f"the emergency stop forbids it: {exc}") from exc
        if getattr(snapshot, "engaged", True):
            raise EnvelopeRefused("the emergency stop forbids it: it is engaged")
        return int(snapshot.generation)

    # -- reading ----------------------------------------------------------

    def _from_row(self, row: dict[str, Any]) -> Envelope:
        return Envelope(
            envelope_id=row["envelope_id"],
            operator_id=row["operator_id"],
            terms=EnvelopeTerms.from_payload(row["terms"]),
            terms_digest=row["terms_digest"],
            stop_generation=int(row["stop_generation"]),
            issued_at=float(row["issued_at"]),
            expires_at=float(row["expires_at"]),
            revoked_at=row["revoked_at"],
            revoked_reason=row["revoked_reason"],
            used=self.store.used(row["envelope_id"]),
        )

    def _why_not_live(self, envelope: Envelope | None) -> str | None:
        if envelope is None:
            return "the operator has not signed an envelope"
        if envelope.revoked_at is not None:
            return f"the envelope was ended: {envelope.revoked_reason}"
        if self.clock() >= envelope.expires_at:
            return "the envelope has expired"
        try:
            generation = self._stop_generation()
        except EnvelopeRefused as exc:
            return str(exc)
        if generation != envelope.stop_generation:
            return "the emergency stop engaged after the envelope was signed"
        return None

    def live(self) -> Envelope | None:
        """The envelope GAGOS may work in now, or None."""
        row = self.store.latest()
        envelope = self._from_row(row) if row else None
        return envelope if self._why_not_live(envelope) is None else None

    def status(self) -> dict[str, Any]:
        """For the operator: the live envelope, or why there is none."""
        row = self.store.latest()
        envelope = self._from_row(row) if row else None
        why = self._why_not_live(envelope)
        if why is None and envelope is not None:
            return {"live": True, **envelope.describe()}
        return {"live": False, "reason": why}

    # -- the operator's acts ------------------------------------------------

    def sign(self, terms: EnvelopeTerms, *, principal: Any) -> Envelope:
        """Sign *terms* for a privileged operator; any earlier envelope ends."""
        if str(getattr(principal, "principal_type", "")) != "operator":
            raise EnvelopeRefused("only the operator signs an envelope")
        if getattr(principal, "authentication_level", "") != "privileged":
            raise EnvelopeRefused(
                "signing an envelope needs a recent strong re-authentication"
            )
        event = str(getattr(principal, "authentication_event_id", "") or "")
        if not event:
            raise EnvelopeRefused("signing an envelope needs a recorded authentication")
        generation = self._stop_generation()
        now = self.clock()
        row = {
            "envelope_id": f"envelope-{uuid.uuid4().hex[:16]}",
            "operator_id": str(principal.principal_id),
            "authentication_event_id": event,
            "session_id": str(getattr(principal, "session_id", "") or ""),
            "terms": terms.as_payload(),
            "terms_digest": terms.digest(),
            "stop_generation": generation,
            "issued_at": now,
            "expires_at": now + terms.hours * 3600,
        }
        self.store.insert(row, now=now)
        return self._from_row({**row, "revoked_at": None, "revoked_reason": None})

    def revoke(
        self, *, principal: Any, reason: str = "revoked by the operator"
    ) -> bool:
        """End the current envelope; True when one was live to end."""
        if str(getattr(principal, "principal_type", "")) != "operator":
            raise EnvelopeRefused("only the operator ends an envelope")
        row = self.store.latest()
        if row is None:
            return False
        return self.store.revoke(row["envelope_id"], now=self.clock(), reason=reason)

    # -- GAGOS's requests ---------------------------------------------------

    def admit(
        self,
        *,
        mission_id: str,
        files: list[str] | tuple[str, ...],
        kind: str,
        originator: str,
    ) -> EnvelopeSlot:
        """Take one slot of the live envelope for a GAGOS mission, or
        :class:`EnvelopeRefused` saying why it is outside."""
        if not _MISSION_ID.match(str(mission_id or "")):
            raise EnvelopeRefused(f"not a mission id: {mission_id!r}")
        originator = str(originator or "").strip()
        if not originator:
            raise EnvelopeRefused("a mission names who originates it")
        row = self.store.latest()
        envelope = self._from_row(row) if row else None
        why = self._why_not_live(envelope)
        if why is not None or envelope is None:
            raise EnvelopeRefused(why or "no live envelope")
        if originator == envelope.operator_id:
            raise EnvelopeRefused(
                "the operator who signed the envelope cannot originate inside it"
            )
        why = envelope.terms.refusal(list(files), kind)
        if why is not None:
            raise EnvelopeRefused(why)
        if self.store.slot(mission_id) is not None:
            raise EnvelopeRefused(f"{mission_id} already holds a slot")
        normalised = sorted({normalise_path(f) for f in files})

        def digest(slot: int) -> str:
            return slot_digest(
                envelope_id=envelope.envelope_id,
                terms_digest=envelope.terms_digest,
                slot=slot,
                mission_id=mission_id,
                kind=kind,
                files=normalised,
            )

        try:
            slot = self.store.reserve(
                envelope_id=envelope.envelope_id,
                max_slots=envelope.terms.max_missions,
                clock=self.clock,
                mission_id=mission_id,
                originator=originator,
                kind=kind,
                files=normalised,
                digest_for=digest,
            )
        except sqlite3.IntegrityError as exc:
            raise EnvelopeRefused(f"{mission_id} already holds a slot") from exc
        if slot == "ended":
            raise EnvelopeRefused("the envelope ended while the slot was being taken")
        if slot == "full":
            raise EnvelopeRefused(
                f"the envelope's {envelope.terms.max_missions} missions are used"
            )
        # A stop engaged while the slot was being taken voids it (Codex's
        # review): the slot stays spent, and held_slot refuses it for ever,
        # because the envelope's generation no longer matches the stop's.
        why = self._why_not_live(envelope)
        if why is not None:
            raise EnvelopeRefused(f"{why}; the slot just taken is void")
        if not isinstance(slot, int):
            raise EnvelopeRefused(f"the envelope's store answered {slot!r}")
        return EnvelopeSlot(
            envelope_id=envelope.envelope_id,
            terms_digest=envelope.terms_digest,
            slot=slot,
            of=envelope.terms.max_missions,
            mission_id=mission_id,
            originator=originator,
            kind=kind,
            files=tuple(normalised),
            slot_digest=digest(slot),
        )

    def held_slot(self, mission_id: str) -> EnvelopeSlot:
        """The slot *mission_id* holds, while its envelope is still live --
        what a later approval checks; else :class:`EnvelopeRefused`."""
        row = self.store.slot(mission_id)
        if row is None:
            raise EnvelopeRefused(f"{mission_id} holds no envelope slot")
        stored = self.store.envelope(row["envelope_id"])
        envelope = self._from_row(stored) if stored else None
        why = self._why_not_live(envelope)
        if why is not None or envelope is None:
            raise EnvelopeRefused(why or "its envelope is gone")
        expected = slot_digest(
            envelope_id=envelope.envelope_id,
            terms_digest=envelope.terms_digest,
            slot=int(row["slot"]),
            mission_id=mission_id,
            kind=row["kind"],
            files=row["files"],
        )
        if expected != row["slot_digest"]:
            raise EnvelopeRefused(f"{mission_id}'s slot does not match its record")
        return EnvelopeSlot(
            envelope_id=envelope.envelope_id,
            terms_digest=envelope.terms_digest,
            slot=int(row["slot"]),
            of=envelope.terms.max_missions,
            mission_id=mission_id,
            originator=row["originator"],
            kind=row["kind"],
            files=tuple(row["files"]),
            slot_digest=row["slot_digest"],
        )


__all__ = [
    "Envelope",
    "EnvelopeAuthority",
    "EnvelopeError",
    "EnvelopeRefused",
    "EnvelopeSlot",
]
