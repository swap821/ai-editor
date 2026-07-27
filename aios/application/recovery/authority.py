"""Organ 42's named owner: one authority over recovery and resumption.

The ledger has always named `RecoveryResumptionAuthority` as this organ's
authority owner, but no such class existed anywhere -- the ledger's
`authority_owner` field was validated by string comparison against a registry
of strings, so a name that matched nothing was structurally invisible.

The mechanism was real; only the owner was missing. `MissionTransitionJournal`
is the durable store, and this is the authority over it: the one place that
answers "what was interrupted, how far did it get, and can that record be
trusted".

It deliberately REPORTS rather than re-drives. Silently resuming a
half-promoted repair without a human decision is the unsupervised recovery
this system refuses; recovery here means telling a human exactly what state
was left behind, with evidence they can verify.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aios.domain.missions.transition_journal import (
    MISSION_TRANSITION_TERMINAL,
    MissionTransitionEntry,
)
from aios.infrastructure.missions.transition_journal_store import (
    JournalChainStatus,
    JournalTamperedError,
    MissionTransitionJournal,
)

_LOGGER = logging.getLogger(__name__)


class RecoveryResumptionAuthority:
    """The one authority over what a crash left behind."""

    def __init__(self, journal: MissionTransitionJournal) -> None:
        self.journal = journal

    @classmethod
    def from_config(
        cls, db_path: str | Path | None = None
    ) -> "RecoveryResumptionAuthority":
        """Build against the durable journal the production paths write to."""
        from aios import config

        return cls(
            MissionTransitionJournal(
                db_path
                if db_path is not None
                else config.MISSION_TRANSITION_JOURNAL_DB_PATH
            )
        )

    # -- writing -------------------------------------------------------- #

    def record_transition(self, mission_id: str, transition: str) -> bool:
        """Best-effort append. Returns whether the transition was recorded.

        Never raises. The journal is additive resumption evidence, not an
        authority over whether work may proceed, so a wiring or IO failure
        here must not fail an otherwise-valid mission.

        The swallow hides one specific hazard, so callers must journal
        MISSION_CREATED at creation time: the store refuses any first
        transition that is not MISSION_CREATED -- including the FAILED and
        ROLLED_BACK escapes -- so a path that only records its later steps
        produces a permanently empty journal while looking fully wired.
        """
        try:
            self.journal.append(mission_id, transition)
            return True
        except Exception as exc:  # noqa: BLE001 - additive, never an authority
            _LOGGER.warning(
                "mission_transition_journal_append_failed",
                extra={
                    "mission_id": mission_id,
                    "transition": transition,
                    "error": str(exc),
                },
            )
            return False

    # -- reading -------------------------------------------------------- #

    def interrupted_missions(self) -> tuple[str, ...]:
        """Missions whose latest recorded transition is not terminal -- the
        set a restart must resume or explicitly fail closed on, rather than
        silently forget."""
        return tuple(self.journal.resume_pending())

    def transition_history(self, mission_id: str) -> tuple[MissionTransitionEntry, ...]:
        return self.journal.history(mission_id)

    def last_transition(self, mission_id: str) -> str | None:
        return self.journal.current_state(mission_id)

    def is_complete(self, mission_id: str) -> bool:
        state = self.journal.current_state(mission_id)
        return state is not None and state in MISSION_TRANSITION_TERMINAL

    def verify_journal(self) -> JournalChainStatus:
        """Prove the journal has not been altered. Raises JournalTamperedError
        if a row was edited, deleted, reordered or inserted."""
        return self.journal.verify_chain()

    # -- the startup surface -------------------------------------------- #

    def recovery_report(self) -> dict[str, Any]:
        """What a restart needs to know, in one call.

        Never raises: a recovery scan must not be able to prevent the system
        from starting. `integrity` distinguishes the three honestly different
        outcomes -- verified, tampered, and could-not-check -- rather than
        collapsing the last two into a reassuring default.
        """
        report: dict[str, Any] = {
            "interrupted_mission_ids": [],
            "interrupted_count": 0,
            "integrity": "unavailable",
            "verified_entries": 0,
            "unverifiable_legacy_entries": 0,
        }
        try:
            interrupted = self.interrupted_missions()
            report["interrupted_mission_ids"] = list(interrupted)
            report["interrupted_count"] = len(interrupted)
        except Exception as exc:  # noqa: BLE001 - must never block startup
            report["error"] = str(exc)
            return report

        try:
            status = self.verify_journal()
        except JournalTamperedError as exc:
            report["integrity"] = "tampered"
            report["error"] = str(exc)
            return report
        except Exception as exc:  # noqa: BLE001 - must never block startup
            report["error"] = str(exc)
            return report

        report["integrity"] = "verified" if status.fully_verified else "partial"
        report["verified_entries"] = status.verified
        report["unverifiable_legacy_entries"] = status.unverifiable_legacy
        return report


__all__ = ["RecoveryResumptionAuthority"]
