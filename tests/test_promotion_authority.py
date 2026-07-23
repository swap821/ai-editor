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
from aios.domain.promotion.contracts import PromotionAuthorization

from tests.helpers import consume_real_capability_proof


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
        authorization=(
            PromotionAuthorization(
                proof=consume_real_capability_proof(
                    project.parent / "proof-caps.db",
                    mission_id="mission-1",
                    contract_digest=contract_digest,
                ),
                promotion_attempt_id="promotion-attempt-1",
                mission_id="mission-1",
                action_id="action-1",
                worker_id="worker-1",
                executor_job_id="worker-1",
                contract_digest=contract_digest,
                workspace_digest=str(diff["workspace_digest"]),
                diff_digest=str(diff["diff_digest"]),
                project_root_identity=str(project.resolve()),
                required_targets=("app.txt",),
            )
            if requires_capability
            else None
        ),
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
        consume_capability=lambda req: (
            calls.append(
                req.authorization.proof.capability_id if req.authorization else ""
            )
            or True
        ),
        apply_staged_diff=lambda _: calls.append("apply"),
        smoke_test=lambda _: calls.append("smoke") or True,
        restore_checkpoint=lambda *_: calls.append("restore") or True,
        mark_completed=lambda *_: calls.append("complete"),
    )
    assert result.status is PromotionStatus.PROMOTED
    assert calls[0] == "checkpoint"
    assert calls[1].startswith("capability:")
    assert calls[2:] == ["apply", "smoke", "complete"]
    assert result.evidence_ids


def test_manager_apply_changes_only_after_authority_gate(staged) -> None:
    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(manager, project, lease, verification=verification)
    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: "checkpoint-apply",
        apply_staged_diff=lambda _: manager.apply(lease),
        smoke_test=lambda _: (
            (project / "app.txt").read_text(encoding="utf-8") == "after\n"
        ),
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
        apply_staged_diff=lambda _: (
            calls.append("apply") or (_ for _ in ()).throw(RuntimeError("apply failed"))
        ),
        smoke_test=lambda _: True,
        restore_checkpoint=lambda checkpoint, _: calls.append(checkpoint) or True,
    )
    assert result.status is PromotionStatus.ROLLED_BACK
    assert result.restored is True
    assert calls == ["apply", "snapshot-exact"]


def test_apply_or_smoke_failure_restores_exact_bytes_via_real_checkpoint_authority(
    staged,
) -> None:
    """Organ 41: prior coverage of the restore path only ever used lambda
    stubs for create_checkpoint/restore_checkpoint, never the real,
    production CheckpointAuthority-backed adapters
    (aios.api.deps.get_checkpoint_creator/get_checkpoint_restorer, the exact
    callables POST /api/v1/maintenance/repairs/run wires into promote()).
    This proves a genuine filesystem round trip: promote() checkpoints the
    real pre-promotion bytes, applies a real diff, fails its smoke test, and
    restores -- with no stub standing in for the persistence path at any
    step."""
    from aios.api.deps import get_checkpoint_creator, get_checkpoint_restorer

    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(manager, project, lease, verification=verification)
    original_bytes = (project / "app.txt").read_bytes()
    assert b"before" in original_bytes

    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=get_checkpoint_creator(),
        apply_staged_diff=lambda _: manager.apply(lease),
        smoke_test=lambda _: False,
        restore_checkpoint=get_checkpoint_restorer(),
    )

    assert result.status is PromotionStatus.ROLLED_BACK
    assert result.restored is True
    assert result.checkpoint_id is not None
    assert (project / "app.txt").read_bytes() == original_bytes


def test_successful_promotion_produces_an_authoritative_post_promotion_receipt(
    staged,
) -> None:
    """Organ 41: the receipt is real, not fabricated -- project_digest must
    match the actual post-apply project tree (via the same tree_digest()
    verify_baseline() itself uses), and promotion_id must match between the
    receipt and the durable record it's stored alongside."""
    from aios.application.workspaces.staged import tree_digest

    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(manager, project, lease, verification=verification)

    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: "checkpoint-receipt",
        apply_staged_diff=lambda _: manager.apply(lease),
        smoke_test=lambda _: (
            (project / "app.txt").read_text(encoding="utf-8") == "after\n"
        ),
        restore_checkpoint=lambda *_: True,
    )

    assert result.status is PromotionStatus.PROMOTED
    receipt = result.post_promotion_receipt
    assert receipt is not None
    assert receipt.passed is True
    assert receipt.mission_id == "mission-1"
    assert receipt.action_id == "action-1"
    assert receipt.diff_digest == request.diff_digest
    assert receipt.verifier_id == "promotion-authority"
    # The real, post-apply project tree digest -- not a placeholder.
    assert receipt.project_digest == tree_digest(project.resolve())


def test_receipt_survives_the_real_durable_store_round_trip(staged, tmp_path) -> None:
    """The receipt is a nested Pydantic model on PromotionResult -- prove it
    actually survives the real JSON serialize/persist/deserialize round trip
    through the durable SQLite store, not just in-memory."""
    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(manager, project, lease, verification=verification)
    authority = PromotionAuthority(
        manager, verification, database_path=tmp_path / "promotions.db"
    )

    result = authority.promote(
        request,
        create_checkpoint=lambda _: "checkpoint-durable",
        apply_staged_diff=lambda _: manager.apply(lease),
        smoke_test=lambda _: (
            (project / "app.txt").read_text(encoding="utf-8") == "after\n"
        ),
        restore_checkpoint=lambda *_: True,
    )
    assert result.post_promotion_receipt is not None

    # Force a read from the durable record, not the in-memory cache, by
    # constructing a fresh authority instance over the same db file.
    fresh_authority = PromotionAuthority(
        manager, verification, database_path=tmp_path / "promotions.db"
    )
    reloaded = fresh_authority.get_authoritative_terminal_promotion("mission-1")
    assert reloaded is not None
    assert reloaded.post_promotion_receipt is not None
    assert reloaded.post_promotion_receipt.project_digest == (
        result.post_promotion_receipt.project_digest
    )
    assert reloaded.post_promotion_receipt.promotion_id == (
        result.post_promotion_receipt.promotion_id
    )


def test_rejected_or_rolled_back_promotion_carries_no_receipt(staged) -> None:
    manager, project, lease = staged
    verification = VerificationAuthority()
    request = _request(manager, project, lease, verification=verification)

    result = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: "checkpoint-fail",
        apply_staged_diff=lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
        smoke_test=lambda _: True,
        restore_checkpoint=lambda *_: True,
    )

    assert result.status is PromotionStatus.ROLLED_BACK
    assert result.post_promotion_receipt is None


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
        smoke_test=lambda _: (
            (project / "app.txt").read_text(encoding="utf-8") == "after\n"
        ),
        restore_checkpoint=lambda *_: True,
    )
    assert result.status is PromotionStatus.PROMOTED
    assert not (project / ".git").exists()
