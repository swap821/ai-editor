"""Durable, idempotent mission transition journal store (Slice 35)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from aios.domain.missions.transition_journal import (
    MISSION_TRANSITION_ESCAPES,
    MISSION_TRANSITION_ORDER,
    MISSION_TRANSITION_TERMINAL,
    MissionTransitionEntry,
)
from aios.infrastructure.storage.migrations import apply_migrations


class MissionTransitionError(RuntimeError):
    """Raised when an out-of-order or post-terminal transition is attempted."""


class JournalTamperedError(RuntimeError):
    """A journal row no longer matches its own recorded digest, or the chain
    linking rows does not join up -- a row was altered, deleted, reordered or
    inserted outside this store."""


@dataclass(frozen=True)
class JournalChainStatus:
    """Outcome of walking the whole journal chain.

    ``unverifiable_legacy`` counts rows written before the chain existed
    (organ 42, migration 0023). They carry no digest and cannot be
    retro-signed without inventing evidence, so they are reported rather than
    counted as verified.
    """

    verified: int
    unverifiable_legacy: int

    @property
    def fully_verified(self) -> bool:
        return self.unverifiable_legacy == 0


def _entry_digest(
    *,
    mission_id: str,
    transition: str,
    sequence: int,
    recorded_at: str,
    previous_entry_digest: str | None,
) -> str:
    """The one place a journal entry digest is computed.

    Deliberately a single function used by both the writer and the verifier:
    organ 38's chain shipped broken because the caller hashed
    ``model_dump_json()`` while the store hashed sorted-key ``json.dumps`` --
    different bytes, so no link ever joined up. Deriving both sides here makes
    that class of mismatch impossible rather than merely fixed once.
    """
    payload = {
        "mission_id": mission_id,
        "transition": transition,
        "sequence": sequence,
        "recorded_at": recorded_at,
        "previous_entry_digest": previous_entry_digest,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class MissionTransitionJournal:
    """Append-only, idempotent journal: re-appending a mission's current
    transition is a no-op; any other out-of-order transition is refused."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # `with sqlite3.Connection` is a TRANSACTION scope, not a closing
        # scope -- it commits but never closes. Every other method here
        # already wraps `_connect()` in `closing()`; this one did not, so
        # constructing a journal leaked an open handle for the life of the
        # process. On Windows an open handle blocks renaming any parent
        # directory, which breaks the disaster-recovery restore path.
        # `apply_migrations` does not commit -- it leaves that to its caller,
        # which is why the commit here is explicit rather than implied by the
        # context manager (matching `append()`'s style in this same file).
        with closing(self._connect()) as conn:
            apply_migrations(conn, scope="missions")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def append(self, mission_id: str, transition: str) -> MissionTransitionEntry:
        with closing(self._connect()) as conn:
            current_row = conn.execute(
                "SELECT transition, sequence FROM mission_execution_transitions "
                "WHERE mission_id = ? ORDER BY sequence DESC LIMIT 1",
                (mission_id,),
            ).fetchone()
            current = current_row["transition"] if current_row else None

            if current == transition:
                # Idempotent no-op: the exact same transition was already
                # recorded -- a retried recovery step must be safe to run
                # twice, so return the existing entry unchanged.
                return MissionTransitionEntry(
                    mission_id=mission_id,
                    transition=transition,
                    sequence=current_row["sequence"],
                )

            self._validate_next(current, transition)
            next_sequence = (current_row["sequence"] + 1) if current_row else 0
            entry = MissionTransitionEntry(
                mission_id=mission_id, transition=transition, sequence=next_sequence
            )
            # Organ 42: link to the journal-wide head, not this mission's head.
            # A per-mission chain would not notice a whole mission's rows being
            # dropped; a journal-wide one does. The predecessor is read here
            # rather than accepted from a caller, so a caller cannot choose its
            # own predecessor and fork the chain.
            head = conn.execute(
                "SELECT entry_digest FROM mission_execution_transitions "
                "WHERE entry_digest IS NOT NULL ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            previous_entry_digest = head["entry_digest"] if head else None
            digest = _entry_digest(
                mission_id=mission_id,
                transition=transition,
                sequence=next_sequence,
                recorded_at=entry.recorded_at,
                previous_entry_digest=previous_entry_digest,
            )
            conn.execute(
                "INSERT INTO mission_execution_transitions "
                "(mission_id, transition, sequence, recorded_at, "
                "previous_entry_digest, entry_digest) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    mission_id,
                    transition,
                    next_sequence,
                    entry.recorded_at,
                    previous_entry_digest,
                    digest,
                ),
            )
            conn.commit()
            return entry

    def verify_chain(self) -> JournalChainStatus:
        """Walk the whole journal, proving every row AND every link.

        Per-row digests alone would not catch a deleted, reordered or inserted
        row -- only that each surviving row matches its own content. Checking
        that each row's ``previous_entry_digest`` equals the preceding row's
        ``entry_digest`` is what makes this a chain.

        This matters beyond audit: resumption reads this journal to decide how
        far a mission actually got, so a silently altered row would misdirect
        recovery, not merely misreport it.
        """
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT mission_id, transition, sequence, recorded_at, "
                "previous_entry_digest, entry_digest "
                "FROM mission_execution_transitions ORDER BY rowid ASC"
            ).fetchall()

        verified = 0
        legacy = 0
        expected_previous: str | None = None
        for position, row in enumerate(rows):
            if row["entry_digest"] is None:
                # Pre-chain row (migration 0023). Counted and reported, never
                # silently treated as verified.
                legacy += 1
                continue
            recomputed = _entry_digest(
                mission_id=row["mission_id"],
                transition=row["transition"],
                sequence=row["sequence"],
                recorded_at=row["recorded_at"],
                previous_entry_digest=row["previous_entry_digest"],
            )
            if recomputed != row["entry_digest"]:
                raise JournalTamperedError(
                    f"journal row {position} (mission_id={row['mission_id']!r}, "
                    f"transition={row['transition']!r}) does not match its own "
                    "digest -- the row was altered outside this store"
                )
            # The genesis row must claim NO predecessor. Without this the
            # first surviving row would be link-checked against nothing, and
            # truncating the HEAD of the chain -- deleting an entire early
            # mission, say -- would go undetected while every remaining row
            # still verified against itself.
            if row["previous_entry_digest"] != expected_previous:
                claimed = row["previous_entry_digest"]
                detail = (
                    f"row claims predecessor {claimed!r} but the preceding row's "
                    f"digest is {expected_previous!r}"
                    if verified
                    else f"first row claims predecessor {claimed!r}, so the rows "
                    "before it were removed"
                )
                raise JournalTamperedError(
                    f"journal chain broken at row {position} "
                    f"(mission_id={row['mission_id']!r}): {detail} -- a row was "
                    "deleted, reordered, or inserted"
                )
            expected_previous = row["entry_digest"]
            verified += 1

        return JournalChainStatus(verified=verified, unverifiable_legacy=legacy)

    @staticmethod
    def _validate_next(current: str | None, transition: str) -> None:
        if current is None:
            if transition != MISSION_TRANSITION_ORDER[0]:
                raise MissionTransitionError(
                    f"first transition for a mission must be "
                    f"{MISSION_TRANSITION_ORDER[0]!r}, got {transition!r}"
                )
            return
        if current in MISSION_TRANSITION_TERMINAL:
            raise MissionTransitionError(
                f"mission is already in terminal state {current!r}; "
                f"cannot transition to {transition!r}"
            )
        if transition in MISSION_TRANSITION_ESCAPES:
            return
        current_index = MISSION_TRANSITION_ORDER.index(current)
        expected_next = MISSION_TRANSITION_ORDER[current_index + 1]
        if transition != expected_next:
            raise MissionTransitionError(
                f"out-of-order transition: mission is at {current!r}, "
                f"expected {expected_next!r} or an escape "
                f"{MISSION_TRANSITION_ESCAPES}, got {transition!r}"
            )

    def current_state(self, mission_id: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT transition FROM mission_execution_transitions "
                "WHERE mission_id = ? ORDER BY sequence DESC LIMIT 1",
                (mission_id,),
            ).fetchone()
        return row["transition"] if row else None

    def history(self, mission_id: str) -> tuple[MissionTransitionEntry, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT mission_id, transition, sequence, recorded_at "
                "FROM mission_execution_transitions WHERE mission_id = ? ORDER BY sequence",
                (mission_id,),
            ).fetchall()
        return tuple(
            MissionTransitionEntry(
                mission_id=row["mission_id"],
                transition=row["transition"],
                sequence=row["sequence"],
                recorded_at=row["recorded_at"],
            )
            for row in rows
        )

    def is_terminal(self, mission_id: str) -> bool:
        state = self.current_state(mission_id)
        return state is not None and state in MISSION_TRANSITION_TERMINAL

    def resume_pending(self) -> tuple[str, ...]:
        """Mission ids whose latest recorded transition is not terminal --
        exactly the set a restart must resume or explicitly fail closed,
        rather than silently forgetting."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT mission_id, transition FROM mission_execution_transitions t1
                WHERE sequence = (
                    SELECT MAX(sequence) FROM mission_execution_transitions t2
                    WHERE t2.mission_id = t1.mission_id
                )
                """
            ).fetchall()
        return tuple(
            row["mission_id"]
            for row in rows
            if row["transition"] not in MISSION_TRANSITION_TERMINAL
        )


__all__ = [
    "JournalChainStatus",
    "JournalTamperedError",
    "MissionTransitionError",
    "MissionTransitionJournal",
]
