"""Phase 5 — Test suite for durable VerificationAuthority persistence.

Tests:
1. Verification result creation and immediate SQLite persistence.
2. Cross-instance / process-restart retrieval of verification records.
3. Authoritative verification checks (is_authoritative) on reloaded instances.
4. Workspace and diff freshness verification (is_current) on reloaded instances.
5. Querying mission verification results (list_results_for_mission) from durable SQLite database.
6. Rejection of forged / altered verification results on reloaded instances.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from aios.application.evidence.verification import VerificationAuthority
from aios.domain.evidence import (
    VerificationObservation,
    VerificationPlanV1,
    VerificationResult,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "verification_operational.db"


def _plan() -> VerificationPlanV1:
    return VerificationPlanV1(
        intended_behavior="verify component stability",
        targets=("target_file.py",),
        required_tests=("pytest",),
        minimum_strength=1,
    )


def _observation(*, exit_code: int = 0) -> VerificationObservation:
    return VerificationObservation(
        command="pytest",
        exit_code=exit_code,
        stdout="1 passed",
        stderr="",
        passed_count=1 if exit_code == 0 else 0,
        failed_count=0 if exit_code == 0 else 1,
        tool_version="pytest-8.0",
        observed_at="2026-07-19T10:00:00Z",
    )


def test_verification_durable_persistence_and_reload(db_path: Path) -> None:
    # Instance 1: perform verification
    authority1 = VerificationAuthority(database_path=db_path)
    result1 = authority1.verify(
        mission_id="mission-dur-1",
        action_id="action-dur-1",
        worker_id="worker-dur-1",
        target="target_file.py",
        plan=_plan(),
        workspace_digest="ws-digest-1",
        diff_digest="diff-digest-1",
        environment_digest="env-digest-1",
        observation=_observation(exit_code=0),
    )

    assert result1.verification_id.startswith("verification-")
    assert result1.passed is True

    # Instance 2: reload from same database_path (simulating process restart)
    authority2 = VerificationAuthority(database_path=db_path)
    reloaded = authority2.get(result1.verification_id)

    assert reloaded is not None
    assert reloaded.verification_id == result1.verification_id
    assert reloaded.mission_id == "mission-dur-1"
    assert reloaded.target == "target_file.py"
    assert reloaded.passed is True
    assert reloaded.workspace_digest == "ws-digest-1"
    assert reloaded.diff_digest == "diff-digest-1"

    # Reloaded authority must recognize reloaded result as authoritative
    assert authority2.is_authoritative(reloaded) is True
    assert authority2.is_authoritative(result1) is True


def test_is_authoritative_rejects_forged_results(db_path: Path) -> None:
    authority1 = VerificationAuthority(database_path=db_path)
    result1 = authority1.verify(
        mission_id="mission-dur-2",
        action_id="action-dur-2",
        worker_id="worker-dur-2",
        target="target_file.py",
        plan=_plan(),
        workspace_digest="ws-digest-2",
        diff_digest="diff-digest-2",
        environment_digest="env-digest-2",
        observation=_observation(exit_code=0),
    )

    authority2 = VerificationAuthority(database_path=db_path)

    # Forged result with unknown verification_id
    forged = result1.model_copy(update={"verification_id": "verification-fake-999"})
    assert authority2.is_authoritative(forged) is False

    # Forged result altering passed status or digests
    tampered = result1.model_copy(update={"passed": False})
    assert authority2.is_authoritative(tampered) is False


def test_is_current_freshness_on_reloaded_instance(db_path: Path) -> None:
    authority1 = VerificationAuthority(database_path=db_path)
    result1 = authority1.verify(
        mission_id="mission-dur-3",
        action_id="action-dur-3",
        worker_id="worker-dur-3",
        target="target_file.py",
        plan=_plan(),
        workspace_digest="ws-fresh-1",
        diff_digest="diff-fresh-1",
        environment_digest="env-fresh-1",
        observation=_observation(exit_code=0),
    )

    authority2 = VerificationAuthority(database_path=db_path)
    reloaded = authority2.get(result1.verification_id)
    assert reloaded is not None

    # Matching workspace and diff digests within 300s window -> current
    assert authority2.is_current(
        reloaded,
        workspace_digest="ws-fresh-1",
        diff_digest="diff-fresh-1",
        now="2026-07-19T10:02:00Z",
        freshness_seconds=300,
    ) is True

    # Mismatched workspace digest -> not current
    assert authority2.is_current(
        reloaded,
        workspace_digest="ws-stale-2",
        diff_digest="diff-fresh-1",
        now="2026-07-19T10:02:00Z",
        freshness_seconds=300,
    ) is False


def test_list_results_for_mission_durable(db_path: Path) -> None:
    authority1 = VerificationAuthority(database_path=db_path)
    r1 = authority1.verify(
        mission_id="mission-multi",
        action_id="action-1",
        worker_id="w-1",
        target="target_file.py",
        plan=_plan(),
        workspace_digest="ws-1",
        diff_digest="diff-1",
        environment_digest="env-1",
        observation=_observation(exit_code=0),
    )
    r2 = authority1.verify(
        mission_id="mission-multi",
        action_id="action-2",
        worker_id="w-1",
        target="target_file.py",
        plan=_plan(),
        workspace_digest="ws-2",
        diff_digest="diff-2",
        environment_digest="env-1",
        observation=_observation(exit_code=0),
    )

    authority2 = VerificationAuthority(database_path=db_path)
    mission_results = authority2.list_results_for_mission("mission-multi")

    assert len(mission_results) == 2
    ids = {r.verification_id for r in mission_results}
    assert r1.verification_id in ids
    assert r2.verification_id in ids
