"""Slice 35: durable mission execution transition journal.

Docker is not running in this environment (verified: `docker ps` fails to
connect to the daemon), so a live private-Executor proof cannot be produced
here -- that gap is recorded honestly in the organ ledger, not faked. What
*is* achievable without Docker, and is what this test file proves, is the
durable transition journal itself: idempotent appends, out-of-order
refusal, and restart-safe resumption at every point in the brief's failure
matrix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.domain.missions.transition_journal import MISSION_TRANSITION_ORDER
from aios.infrastructure.missions.transition_journal_store import (
    MissionTransitionError,
    MissionTransitionJournal,
)


def _journal(tmp_path: Path) -> MissionTransitionJournal:
    return MissionTransitionJournal(tmp_path / "journal.db")


# --- basic sequencing --------------------------------------------------


def test_first_transition_must_be_mission_created(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    with pytest.raises(MissionTransitionError):
        journal.append("mission-1", "APPROVED")
    journal.append("mission-1", "MISSION_CREATED")
    assert journal.current_state("mission-1") == "MISSION_CREATED"


def test_full_happy_path_sequence(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    for transition in MISSION_TRANSITION_ORDER:
        journal.append("mission-1", transition)
    assert journal.current_state("mission-1") == "COMPLETED"
    assert journal.is_terminal("mission-1") is True
    assert len(journal.history("mission-1")) == len(MISSION_TRANSITION_ORDER)


def test_out_of_order_transition_is_refused(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append("mission-1", "MISSION_CREATED")
    journal.append("mission-1", "APPROVED")
    with pytest.raises(MissionTransitionError):
        journal.append("mission-1", "PROMOTED")


def test_transition_after_terminal_state_is_refused(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append("mission-1", "MISSION_CREATED")
    journal.append("mission-1", "FAILED")
    with pytest.raises(MissionTransitionError):
        journal.append("mission-1", "APPROVED")


# --- idempotency --------------------------------------------------------


def test_repeated_append_of_current_transition_is_idempotent(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    journal.append("mission-1", "MISSION_CREATED")
    first = journal.append("mission-1", "APPROVED")
    second = journal.append("mission-1", "APPROVED")
    third = journal.append("mission-1", "APPROVED")
    assert first.sequence == second.sequence == third.sequence
    assert len(journal.history("mission-1")) == 2  # MISSION_CREATED + APPROVED only


def test_idempotent_retry_does_not_create_ambiguous_lineage(
    tmp_path: Path,
) -> None:
    """A retried recovery step (e.g. the process that recorded
    EXECUTION_SUBMITTED crashes and a supervisor retries the same append)
    must never fork the journal into two different next-states."""
    journal = _journal(tmp_path)
    journal.append("mission-1", "MISSION_CREATED")
    journal.append("mission-1", "APPROVED")
    journal.append("mission-1", "WORKSPACE_CREATED")
    journal.append("mission-1", "EXECUTION_SUBMITTED")
    # simulate the retry of the same step after a crash
    journal.append("mission-1", "EXECUTION_SUBMITTED")
    assert journal.current_state("mission-1") == "EXECUTION_SUBMITTED"
    assert len(journal.history("mission-1")) == 4


# --- failure matrix: crash at every stage, restart resumes correctly ------


@pytest.mark.parametrize(
    "crash_after",
    [
        "MISSION_CREATED",  # before workspace creation
        "WORKSPACE_CREATED",  # during/after executor submission
        "EXECUTION_SUBMITTED",  # during executor call
        "EXECUTION_COMPLETED",  # after executor return
        "VERIFIED",  # during/after verification
        "CHECKPOINT_CREATED",  # after checkpoint
        "PROMOTION_STARTED",  # during file replacement
        "PROMOTED",  # after promotion but before smoke test
        "POST_PROMOTION_VERIFIED",  # before final mission completion
    ],
)
def test_restart_resumes_from_authoritative_state_at_every_crash_point(
    tmp_path: Path, crash_after: str
) -> None:
    db_path = tmp_path / "journal.db"
    journal = MissionTransitionJournal(db_path)
    crash_index = MISSION_TRANSITION_ORDER.index(crash_after)
    for transition in MISSION_TRANSITION_ORDER[: crash_index + 1]:
        journal.append("mission-1", transition)

    # Simulate a process restart: a brand-new journal instance over the
    # same durable file must see exactly the same current state.
    restarted = MissionTransitionJournal(db_path)
    assert restarted.current_state("mission-1") == crash_after
    assert "mission-1" in restarted.resume_pending()

    # Resumption must be able to continue forward from exactly this point.
    if crash_index + 1 < len(MISSION_TRANSITION_ORDER):
        next_transition = MISSION_TRANSITION_ORDER[crash_index + 1]
        restarted.append("mission-1", next_transition)
        assert restarted.current_state("mission-1") == next_transition


def test_crash_during_rollback_is_a_valid_escape_from_any_non_terminal_state(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    journal.append("mission-1", "MISSION_CREATED")
    journal.append("mission-1", "APPROVED")
    journal.append("mission-1", "WORKSPACE_CREATED")
    journal.append("mission-1", "EXECUTION_SUBMITTED")
    journal.append("mission-1", "EXECUTION_COMPLETED")
    journal.append("mission-1", "VERIFIED")
    journal.append("mission-1", "CHECKPOINT_CREATED")
    journal.append("mission-1", "PROMOTION_STARTED")
    journal.append("mission-1", "ROLLED_BACK")
    assert journal.current_state("mission-1") == "ROLLED_BACK"
    assert journal.is_terminal("mission-1") is True


def test_resume_pending_only_lists_non_terminal_missions(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append("mission-1", "MISSION_CREATED")
    journal.append("mission-1", "APPROVED")

    for transition in MISSION_TRANSITION_ORDER:
        journal.append("mission-2", transition)

    pending = journal.resume_pending()
    assert "mission-1" in pending
    assert "mission-2" not in pending


def test_multiple_missions_maintain_independent_lineages(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append("mission-1", "MISSION_CREATED")
    journal.append("mission-2", "MISSION_CREATED")
    journal.append("mission-1", "APPROVED")
    assert journal.current_state("mission-1") == "APPROVED"
    assert journal.current_state("mission-2") == "MISSION_CREATED"
