from __future__ import annotations

from pathlib import Path

import pytest

from aios.application.evidence.verification import VerificationAuthority
from aios.application.promotion.authority import PromotionAuthority
from aios.application.workspaces.staged import StagedWorkspaceManager
from aios.domain.evidence import (
    EvidenceBundle,
    EvidenceCommand,
    VerificationObservation,
    VerificationPlanV1,
)
from aios.domain.missions.mission_state import MissionState
from aios.domain.promotion import PromotionRequest, PromotionStatus


@pytest.fixture
def staged(tmp_path: Path) -> tuple[StagedWorkspaceManager, Path, object]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.txt").write_text("before\n", encoding="utf-8")
    manager = StagedWorkspaceManager(
        tmp_path / "staged",
        enrolled_roots=(project,),
    )
    lease = manager.stage("mission-1", project)
    (Path(lease.workspace_path) / "app.txt").write_text("after\n", encoding="utf-8")
    return manager, project, lease


def _request(
    manager: StagedWorkspaceManager,
    project: Path,
    lease: object,
    *,
    verification: VerificationAuthority,
    required_strength: int = 3,
    current_state: MissionState = MissionState.VERIFYING,
    requires_capability: bool = False,
    contract_digest: str = "contract-1",
    authoritative_contract_digest: str = "contract-1",
) -> PromotionRequest:
    diff = manager.diff(lease)  # type: ignore[arg-type]
    observation = VerificationObservation(
        command="pytest app.txt",
        exit_code=0,
        stdout="1 passed",
        passed_count=1,
        tool_version="pytest-1",
    )
    result = verification.verify(
        mission_id="mission-1",
        action_id="action-1",
        worker_id="worker-1",
        target="app.txt",
        plan=VerificationPlanV1(
            intended_behavior="app remains valid",
            targets=("app.txt",),
            minimum_strength=required_strength,
        ),
        workspace_digest=str(diff["workspace_digest"]),
        diff_digest=str(diff["diff_digest"]),
        environment_digest="environment-1",
        observation=observation,
    )
    bundle = EvidenceBundle(
        mission_id="mission-1",
        worker_id="worker-1",
        contract_digest=contract_digest,
        workspace_digest=str(diff["workspace_digest"]),
        diff_digest=str(diff["diff_digest"]),
        executor_job_id="worker-1",
        environment_digest="environment-1",
        commands=(
            EvidenceCommand(
                command=observation.command,
                return_code=observation.exit_code,
                stdout_digest="stdout-1",
                stderr_digest="stderr-1",
                tool_version=observation.tool_version,
                observed_at=observation.observed_at,
            ),
        ),
        verification_strength=result.strength,
        targets_exercised=("app.txt",),
        started_at=observation.observed_at,
        ended_at=observation.observed_at,
    )
    return PromotionRequest(
        mission_id="mission-1",
        action_id="action-1",
        worker_id="worker-1",
        executor_job_id="worker-1",
        environment_digest="environment-1",
        project_root=str(project),
        lease=lease,
        current_state=current_state,
        contract_digest=contract_digest,
        authoritative_contract_digest=authoritative_contract_digest,
        policy_version="policy-1",
        authoritative_policy_version="policy-1",
        workspace_digest=str(diff["workspace_digest"]),
        diff_digest=str(diff["diff_digest"]),
        verification_results=(result,),
        evidence_bundle=bundle,
        required_targets=("app.txt",),
        required_strength=required_strength,
        requires_capability=requires_capability,
        capability_id="cap-1" if requires_capability else None,
        capability_digest="cap-digest" if requires_capability else None,
        authoritative_capability_digest="cap-digest" if requires_capability else None,
    )


def test_promotion_requires_current_mission_and_strong_fresh_evidence(staged) -> None:
    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(
        manager,
        project,
        lease,
        verification=verification,
        current_state=MissionState.RUNNING,
    )
    applied: list[str] = []
    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: "checkpoint-1",
        apply_staged_diff=lambda _: applied.append("applied"),
        smoke_test=lambda _: True,
        restore_checkpoint=lambda *_: True,
    )
    assert result.status is PromotionStatus.REJECTED
    assert "mission_not_verifying" in result.reason_codes
    assert applied == []


def test_contract_or_baseline_change_refuses_without_checkpoint(staged) -> None:
    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(
        manager,
        project,
        lease,
        verification=verification,
        authoritative_contract_digest="different-contract",
    )
    checkpoints: list[str] = []
    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: checkpoints.append("created") or "checkpoint-1",
        apply_staged_diff=lambda _: pytest.fail("must not apply"),
        smoke_test=lambda _: True,
        restore_checkpoint=lambda *_: True,
    )
    assert result.status is PromotionStatus.REJECTED
    assert checkpoints == []

    (project / "app.txt").write_text("changed outside mission\n", encoding="utf-8")
    request = _request(
        manager,
        project,
        lease,
        verification=verification,
    )
    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: checkpoints.append("created") or "checkpoint-1",
        apply_staged_diff=lambda _: pytest.fail("must not apply"),
        smoke_test=lambda _: True,
        restore_checkpoint=lambda *_: True,
    )
    assert result.status is PromotionStatus.REJECTED
    assert "project_baseline_changed" in result.reason_codes


def test_success_is_checkpointed_capability_bound_and_observed(staged) -> None:
    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(
        manager,
        project,
        lease,
        verification=verification,
        requires_capability=True,
    )
    calls: list[str] = []
    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: calls.append("checkpoint") or "checkpoint-1",
        consume_capability=lambda req: calls.append(req.capability_id or "") or True,
        apply_staged_diff=lambda _: calls.append("apply"),
        smoke_test=lambda _: calls.append("smoke") or True,
        restore_checkpoint=lambda *_: calls.append("restore") or True,
        mark_completed=lambda *_: calls.append("complete"),
    )
    assert result.status is PromotionStatus.PROMOTED
    assert calls == ["checkpoint", "cap-1", "apply", "smoke", "complete"]
    assert result.evidence_ids


def test_manager_apply_changes_only_after_authority_gate(staged) -> None:
    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(manager, project, lease, verification=verification)
    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: "checkpoint-apply",
        apply_staged_diff=lambda _: manager.apply(lease),
        smoke_test=lambda _: (project / "app.txt").read_text(encoding="utf-8")
        == "after\n",
        restore_checkpoint=lambda *_: True,
    )
    assert result.status is PromotionStatus.PROMOTED
    assert (project / "app.txt").read_text(encoding="utf-8") == "after\n"


def test_apply_or_smoke_failure_restores_exact_checkpoint(staged) -> None:
    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(manager, project, lease, verification=verification)
    calls: list[object] = []
    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: "snapshot-exact",
        apply_staged_diff=lambda _: calls.append("apply")
        or (_ for _ in ()).throw(RuntimeError("apply failed")),
        smoke_test=lambda _: True,
        restore_checkpoint=lambda checkpoint, _: calls.append(checkpoint) or True,
    )
    assert result.status is PromotionStatus.ROLLED_BACK
    assert result.restored is True
    assert calls == ["apply", "snapshot-exact"]


def test_forged_lease_cannot_reach_promotion_callback(staged) -> None:
    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(manager, project, lease, verification=verification)
    forged = request.model_copy(
        update={
            "lease": lease.model_copy(
                update={"workspace_path": str(project.parent / "outside")}
            )
        }
    )
    applied: list[str] = []
    result = PromotionAuthority(manager, verification).promote(
        forged,
        create_checkpoint=lambda _: "checkpoint-forged",
        apply_staged_diff=lambda _: applied.append("applied"),
        smoke_test=lambda _: True,
        restore_checkpoint=lambda *_: True,
    )
    assert result.status is PromotionStatus.REJECTED
    assert "workspace_lease_mismatch" in result.reason_codes
    assert applied == []


def test_promotion_ignores_council_rollback_git_pointer(staged) -> None:
    manager, project, lease = staged
    (Path(lease.workspace_path) / ".git").write_text(
        "gitdir: runtime/rollback.git\n", encoding="utf-8"
    )
    verification = VerificationAuthority()
    request = _request(manager, project, lease, verification=verification)
    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: "checkpoint-git-pointer",
        apply_staged_diff=lambda _: manager.apply(lease),
        smoke_test=lambda _: (project / "app.txt").read_text(encoding="utf-8")
        == "after\n",
        restore_checkpoint=lambda *_: True,
    )
    assert result.status is PromotionStatus.PROMOTED
    assert not (project / ".git").exists()
