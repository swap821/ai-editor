"""Tests for durable maintenance finding storage."""

from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.repository import MaintenanceFindingRepository


def _finding(
    *,
    fingerprint: str = "fp-1",
    finding_id: str = "find-1",
    status: str = "OPEN",
    occurrence_count: int = 1,
) -> MaintenanceFinding:
    return MaintenanceFinding(
        finding_id=finding_id,
        fingerprint=fingerprint,
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
        occurrence_count=occurrence_count,
        status=status,
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


def test_list_findings_returns_empty_tuple_for_empty_repository(tmp_path) -> None:
    repository = MaintenanceFindingRepository(tmp_path / "maintenance.db")

    assert repository.list_findings() == ()


def test_list_findings_returns_one_persisted_finding(tmp_path) -> None:
    repository = MaintenanceFindingRepository(tmp_path / "maintenance.db")
    finding = _finding()
    repository.save(finding)

    assert repository.list_findings() == (finding,)


def test_list_findings_returns_multiple_findings_in_stable_fingerprint_order(
    tmp_path,
) -> None:
    repository = MaintenanceFindingRepository(tmp_path / "maintenance.db")
    second = _finding(fingerprint="fp-2", finding_id="find-2")
    first = _finding(fingerprint="fp-1")
    repository.save(second)
    repository.save(first)

    assert [finding.fingerprint for finding in repository.list_findings()] == [
        "fp-1",
        "fp-2",
    ]


def test_list_findings_survives_restart(tmp_path) -> None:
    database = tmp_path / "maintenance.db"
    MaintenanceFindingRepository(database).save(
        _finding(fingerprint="fp-restart", finding_id="find-restart")
    )

    restored = MaintenanceFindingRepository(database).list_findings()

    assert len(restored) == 1
    assert restored[0].fingerprint == "fp-restart"


def test_list_findings_reflects_update_to_existing_fingerprint(tmp_path) -> None:
    repository = MaintenanceFindingRepository(tmp_path / "maintenance.db")
    repository.save(_finding(occurrence_count=1))
    updated = _finding(occurrence_count=2).model_copy(
        update={"last_seen": "2026-07-18T01:00:00Z"}
    )
    repository.save(updated)

    listed = repository.list_findings()

    assert len(listed) == 1
    assert listed[0].occurrence_count == 2
    assert listed[0].last_seen == "2026-07-18T01:00:00Z"


def test_reopened_finding_state_survives_restart(tmp_path) -> None:
    database = tmp_path / "maintenance.db"
    repository = MaintenanceFindingRepository(database)
    repository.save(_finding(status="HUMAN_SUPPRESSED"))
    repository.save(_finding(status="REOPENED", occurrence_count=2))

    restored = MaintenanceFindingRepository(database).list_findings()

    assert len(restored) == 1
    assert restored[0].status == "REOPENED"
    assert restored[0].occurrence_count == 2
