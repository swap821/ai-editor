"""Tests for durable maintenance finding storage."""

from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.repository import MaintenanceFindingRepository


def _finding() -> MaintenanceFinding:
    return MaintenanceFinding(
        finding_id="find-1",
        fingerprint="fp-1",
        scanner_id="scanner",
        scanner_version="1",
        kind="dead_code",
        severity="medium",
        confidence=0.9,
        evidence_quality="deterministic",
        target_id="src/example.py",
        target_digest="target-1",
        source_digest="source-1",
        first_seen="2026-07-18T00:00:00Z",
        last_seen="2026-07-18T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="unused function",
    )


def test_finding_survives_repository_restart(tmp_path) -> None:
    database = tmp_path / "maintenance.db"
    first = MaintenanceFindingRepository(database)
    first.save(_finding())

    second = MaintenanceFindingRepository(database)
    restored = second.get("fp-1")

    assert restored is not None
    assert restored.finding_id == "find-1"
    assert restored.status == "OPEN"
    assert restored.occurrence_count == 1
