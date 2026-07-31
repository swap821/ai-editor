"""Unit tests for aios.application.models.privacy_audit.PrivacyAuditTracker."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.application.models.privacy_audit import (
    PrivacyAuditRecord,
    PrivacyAuditTamperedError,
    PrivacyAuditTracker,
    PrivacyAuditUnavailableError,
)


def test_record_and_recent_newest_first():
    tracker = PrivacyAuditTracker()
    tracker.record("gemini", {"redacted_paths": 1})
    tracker.record("bedrock", {"redacted_paths": 0, "redacted_secrets": 2})

    records = tracker.recent()

    assert [r.provider for r in records] == ["bedrock", "gemini"]
    assert records[0].audit == {"redacted_paths": 0, "redacted_secrets": 2}


def test_recent_respects_limit():
    tracker = PrivacyAuditTracker()
    for i in range(5):
        tracker.record("gemini", {"n": i})

    assert len(tracker.recent(limit=2)) == 2


def test_recent_empty_when_nothing_recorded():
    tracker = PrivacyAuditTracker()
    assert tracker.recent() == []


def test_max_records_bounds_the_buffer():
    tracker = PrivacyAuditTracker(max_records=3)
    for i in range(10):
        tracker.record("gemini", {"n": i})

    records = tracker.recent(limit=100)
    assert len(records) == 3
    # newest-first: the 3 most recently recorded (n=9, 8, 7)
    assert [r.audit["n"] for r in records] == [9, 8, 7]


def test_record_copies_the_audit_dict_defensively():
    tracker = PrivacyAuditTracker()
    audit = {"redacted_paths": 1}
    tracker.record("gemini", audit)
    audit["redacted_paths"] = 999

    assert tracker.recent()[0].audit == {"redacted_paths": 1}


def test_record_never_raises_on_a_falsy_audit():
    tracker = PrivacyAuditTracker()
    tracker.record("gemini", {})
    tracker.record("bedrock", None)  # type: ignore[arg-type]

    records = tracker.recent()
    assert len(records) == 2
    assert all(isinstance(r.audit, dict) for r in records)


def test_privacy_audit_record_has_a_real_timestamp():
    record = PrivacyAuditRecord(provider="gemini", audit={})
    assert record.recorded_at
    assert "T" in record.recorded_at


def test_durable_tracker_survives_restart(tmp_path: Path) -> None:
    """Phase 3 condition 3: privacy audits must not die with the process."""
    db = tmp_path / "privacy.db"
    writer = PrivacyAuditTracker(database_path=db, max_records=10)
    writer.record("gemini", {"redacted_paths": 2})
    writer.record("bedrock", {"redacted_secrets": 1})

    assert writer.durable_status()["durable"] is True

    reader = PrivacyAuditTracker(database_path=db, max_records=10)
    records = reader.recent()

    assert [r.provider for r in records] == ["bedrock", "gemini"]
    assert records[0].audit == {"redacted_secrets": 1}
    assert reader.verify_durable_chain()["status"] == "verified"
    assert reader.verify_durable_chain()["verified"] == 2


def test_durable_tracker_detects_tampered_row(tmp_path: Path) -> None:
    """Phase 3 condition 4: silent disk edits must not be trusted."""
    db = tmp_path / "privacy.db"
    tracker = PrivacyAuditTracker(database_path=db)
    tracker.record("gemini", {"redacted_paths": 1})

    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "UPDATE privacy_audits SET audit_json = ? WHERE provider = ?",
            ('{"redacted_paths": 999}', "gemini"),
        )
        conn.commit()

    with pytest.raises(PrivacyAuditTamperedError):
        PrivacyAuditTracker(database_path=db).recent()


def test_process_local_mode_reports_not_durable() -> None:
    tracker = PrivacyAuditTracker()
    status = tracker.durable_status()
    assert status["durable"] is False
    assert status["reason"]


def test_durable_load_failure_surfaces_unavailable_not_empty_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "privacy.db"
    tracker = PrivacyAuditTracker(database_path=db)
    tracker.record("gemini", {"redacted_paths": 1})

    def _boom(self, *, limit: int) -> list[PrivacyAuditRecord]:  # noqa: ANN001
        raise OSError("disk offline")

    monkeypatch.setattr(PrivacyAuditTracker, "_load_verified_rows", _boom)

    broken = PrivacyAuditTracker(database_path=db)
    assert broken.is_projection_available() is False

    with pytest.raises(PrivacyAuditUnavailableError):
        broken.recent()
