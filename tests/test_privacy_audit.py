"""Unit tests for aios.application.models.privacy_audit.PrivacyAuditTracker."""

from __future__ import annotations

from aios.application.models.privacy_audit import PrivacyAuditRecord, PrivacyAuditTracker


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
