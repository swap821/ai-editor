from __future__ import annotations

from aios.application.evidence import EvidenceAuthority, VerificationAuthority
from aios.core.verification_strength import VerificationStrength
from aios.domain.evidence import VerificationObservation, VerificationPlanV1


def _plan() -> VerificationPlanV1:
    return VerificationPlanV1(
        intended_behavior="target behavior remains correct",
        targets=("src/main.py", "other.py"),
        required_tests=("python -m pytest",),
        minimum_strength=int(VerificationStrength.STRONG),
    )


def test_evidence_is_redacted_and_bound_to_mission() -> None:
    records = []
    authority = EvidenceAuthority(sink=records.append)
    record = authority.record(
        mission_id="mission-1",
        action_id="action-1",
        worker_id="worker-1",
        evidence_type="test",
        source="test",
        content="Bearer " + "a" * 32,
        environment_digest="env-1",
        tool_version="pytest 9",
        metadata={"output": "Bearer " + "b" * 32},
    )
    assert record.mission_id == "mission-1"
    assert record.content_reference.startswith("inline:")
    assert "Bearer " + "b" * 32 not in str(record.metadata)
    assert records == [record]


def test_verification_is_target_specific_and_weak_evidence_cannot_promote() -> None:
    authority = VerificationAuthority()
    weak = authority.verify(
        mission_id="mission-1",
        action_id="action-1",
        worker_id="worker-1",
        target="src/main.py",
        plan=_plan(),
        workspace_digest="workspace-1",
        diff_digest="diff-1",
        environment_digest="env-1",
        observation=VerificationObservation(
            command="echo ok", exit_code=0, stdout="ok", tool_version="echo 1"
        ),
    )
    strong = authority.verify(
        mission_id="mission-1",
        action_id="action-1",
        worker_id="worker-1",
        target="other.py",
        plan=_plan(),
        workspace_digest="workspace-1",
        diff_digest="diff-1",
        environment_digest="env-1",
        observation=VerificationObservation(
            command="python -m pytest",
            exit_code=0,
            stdout="1 passed",
            passed_count=1,
            tool_version="pytest 9",
        ),
    )
    assert weak.strength == int(VerificationStrength.WEAK)
    assert weak.meets_requirement is False
    assert strong.meets_requirement is True
    assert authority.promotion_strength([strong, weak]) == 0


def test_stale_workspace_or_diff_invalidates_verification() -> None:
    authority = VerificationAuthority()
    result = authority.verify(
        mission_id="mission-1",
        action_id="action-1",
        worker_id="worker-1",
        target="src/main.py",
        plan=_plan(),
        workspace_digest="workspace-1",
        diff_digest="diff-1",
        environment_digest="env-1",
        observation=VerificationObservation(
            command="python -m pytest", exit_code=0, stdout="1 passed", tool_version="pytest 9"
        ),
    )
    assert authority.is_current(
        result, workspace_digest="workspace-1", diff_digest="diff-1", now=result.observed_at
    )
    assert not authority.is_current(
        result, workspace_digest="workspace-2", diff_digest="diff-1", now=result.observed_at
    )
