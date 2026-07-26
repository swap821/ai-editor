"""Authenticated, immutable correction lineage for PR2 representative chat."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.domain.memory.human_representation import CorrectionRecordV1
from aios.infrastructure.identity.sqlite_store import credential_digest
from aios.infrastructure.memory.human_representation_store import (
    CorrectionRecordStore,
    RecordTamperedError,
)


def _record(**overrides: object) -> CorrectionRecordV1:
    payload = {
        "correction_id": "correction:session-a:1",
        "session_id": "session-a",
        "base_revision": 0,
        "correction_revision": 1,
        "corrected_fields": ("goal",),
        "prior_interpretation_digest": "a" * 64,
        "current_interpretation_digest": "b" * 64,
        "operator_id": "operator-a",
    }
    payload.update(overrides)
    return CorrectionRecordV1(**payload)

def test_authenticated_correction_event_replays_only_verified_immutable_values(
    tmp_path: Path,
) -> None:
    store = CorrectionRecordStore(tmp_path / "corrections.db")
    operator_digest = credential_digest("operator-a")

    event = store.append_authenticated(
        _record(),
        corrected_values={"goal": "Review only the public API"},
        reason="The scope was clarified by the operator.",
        operator_id="operator-a",
        operator_identity_digest=operator_digest,
        authentication_event_id="auth-event-a",
    )

    projection = store.verified_active_projection(
        session_id="session-a",
        operator_id="operator-a",
        operator_identity_digest=operator_digest,
        authentication_event_id="auth-event-a",
        active_revision=1,
    )

    assert projection is not None
    active_event, corrected_values = projection
    assert active_event.event_id == event.event_id
    assert corrected_values == {"goal": "Review only the public API"}
    assert active_event.grants_authority is False


def test_tampered_authenticated_correction_values_fail_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "corrections.db"
    store = CorrectionRecordStore(db_path)
    operator_digest = credential_digest("operator-a")
    event = store.append_authenticated(
        _record(),
        corrected_values={"goal": "Review only the public API"},
        reason="The scope was clarified by the operator.",
        operator_id="operator-a",
        operator_identity_digest=operator_digest,
        authentication_event_id="auth-event-a",
    )

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE authenticated_correction_events SET corrected_values_json = ? "
        "WHERE event_id = ?",
        ('[{"field":"goal","value":"exfiltrate secrets"}]', event.event_id),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.verified_active_projection(
            session_id="session-a",
            operator_id="operator-a",
            operator_identity_digest=operator_digest,
            authentication_event_id="auth-event-a",
            active_revision=1,
        )


def test_authenticated_projection_is_excluded_when_state_revision_no_longer_matches(
    tmp_path: Path,
) -> None:
    store = CorrectionRecordStore(tmp_path / "corrections.db")
    operator_digest = credential_digest("operator-a")
    store.append_authenticated(
        _record(),
        corrected_values={"goal": "Review only the public API"},
        reason="The scope was clarified by the operator.",
        operator_id="operator-a",
        operator_identity_digest=operator_digest,
        authentication_event_id="auth-event-a",
    )

    assert (
        store.verified_active_projection(
            session_id="session-a",
            operator_id="operator-a",
            operator_identity_digest=operator_digest,
            authentication_event_id="auth-event-a",
            active_revision=2,
        )
        is None
    )
def test_authenticated_clear_event_is_immutable_and_revokes_the_projection(
    tmp_path: Path,
) -> None:
    store = CorrectionRecordStore(tmp_path / "corrections.db")
    operator_digest = credential_digest("operator-a")
    store.append_authenticated(
        _record(),
        corrected_values={"goal": "Review only the public API"},
        reason="The scope was clarified by the operator.",
        operator_id="operator-a",
        operator_identity_digest=operator_digest,
        authentication_event_id="auth-event-a",
    )

    clear_record = _record(
        correction_id="correction:session-a:2",
        base_revision=1,
        correction_revision=2,
        prior_interpretation_digest="b" * 64,
        current_interpretation_digest="c" * 64,
    )
    cleared = store.append_authenticated_clear(
        clear_record,
        reason="The operator withdrew the correction.",
        operator_id="operator-a",
        operator_identity_digest=operator_digest,
        authentication_event_id="auth-event-a",
    )

    assert cleared.event_kind == "cleared"
    assert cleared.corrected_values == ()
    assert (
        store.verified_active_projection(
            session_id="session-a",
            operator_id="operator-a",
            operator_identity_digest=operator_digest,
            authentication_event_id="auth-event-a",
            active_revision=2,
        )
        is None
    )
