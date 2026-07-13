from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios.application.memory.authority import MemoryAuthority, MemoryPromotionDenied
from aios.domain.evidence import EvidenceRecord, EvidenceType, VerificationResult
from aios.domain.memory import (
    MemoryHit,
    MemoryProposal,
    MemoryPromotionActor,
    MemoryRecallContext,
)
from aios.infrastructure.memory import MemoryAuthorityStore
from aios.infrastructure.storage.migrations import apply_migrations


def _evidence(
    *,
    evidence_id: str = "evidence-1",
    strength: int = 4,
    mission_id: str = "mission-1",
    action_id: str = "action-1",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        mission_id=mission_id,
        action_id=action_id,
        worker_id="worker-1",
        evidence_type=EvidenceType.TEST,
        source="executor",
        content_reference=f"inline:{evidence_id}",
        content_digest=f"digest-{evidence_id}",
        redaction_status="redacted_or_clean",
        environment_digest="env-1",
        tool_version="pytest-1",
        trust_level="verified",
        verification_strength=strength,
    )


def _proposal(
    *,
    proposal_id: str = "proposal-1",
    evidence_ids: tuple[str, ...] = ("evidence-1",),
    project_id: str | None = "project-1",
    required_strength: int = 3,
) -> MemoryProposal:
    return MemoryProposal(
        proposal_id=proposal_id,
        memory_type="skill",
        content_reference="procedural_skills:42",
        content_digest="content-digest-1",
        project_id=project_id,
        source_principal="worker:worker-1",
        source_mission_id="mission-1",
        source_action_id="action-1",
        evidence_ids=evidence_ids,
        required_strength=required_strength,
        policy_version="policy-1",
        confidence_basis="target-specific verification",
    )


def _authority(tmp_path: Path) -> MemoryAuthority:
    return MemoryAuthority(store=MemoryAuthorityStore(tmp_path / "memory.db"))


def test_weak_evidence_cannot_promote(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    proposal = _proposal()
    authority.propose(proposal)

    decision = authority.verify(proposal, (_evidence(strength=2),))
    assert not decision.verified
    assert "VERIFICATION_STRENGTH_TOO_WEAK" in decision.reason_codes
    with pytest.raises(MemoryPromotionDenied):
        authority.promote(
            proposal,
            MemoryPromotionActor(
                actor_id="operator-1",
                actor_type="operator",
                authentication_event_id="auth-1",
                operator_approval=True,
            ),
            evidence=(_evidence(strength=2),),
        )


def test_promotion_is_evidence_bound_and_single_use(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    proposal = _proposal()
    authority.propose(proposal)
    evidence = _evidence()
    record = authority.promote(
        proposal,
        MemoryPromotionActor(
            actor_id="operator-1",
            actor_type="operator",
            authentication_event_id="auth-1",
            operator_approval=True,
        ),
        evidence=(evidence,),
    )

    assert record.provenance.evidence_ids == ("evidence-1",)
    assert record.provenance.operator_approval == "operator-1"
    assert record.provenance.project_id == "project-1"
    assert authority.store.get_record(record.record_id) == record
    with pytest.raises(MemoryPromotionDenied, match="already been resolved"):
        authority.promote(
            proposal,
            MemoryPromotionActor(
                actor_id="operator-1",
                actor_type="operator",
                authentication_event_id="auth-1",
                operator_approval=True,
            ),
            evidence=(evidence,),
        )


def test_changed_proposal_and_missing_lineage_fail_closed(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    proposal = _proposal(evidence_ids=())
    authority.propose(proposal)
    with pytest.raises(MemoryPromotionDenied):
        authority.promote(
            proposal,
            MemoryPromotionActor(
                actor_id="operator-1",
                actor_type="operator",
                authentication_event_id="auth-1",
                operator_approval=True,
            ),
            evidence=(_evidence(),),
        )

    changed = _proposal().model_copy(update={"content_digest": "tampered"})
    authority.propose(_proposal(proposal_id="proposal-2"))
    with pytest.raises(Exception, match="changed"):
        authority.promote(
            changed.model_copy(update={"proposal_id": "proposal-2"}),
            MemoryPromotionActor(
                actor_id="operator-1",
                actor_type="operator",
                authentication_event_id="auth-1",
                operator_approval=True,
            ),
            evidence=(_evidence(),),
        )


def test_verification_result_can_supply_authoritative_evidence(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    proposal = _proposal(evidence_ids=("verification-1",))
    authority.propose(proposal)
    verification = VerificationResult(
        verification_id="verification-1",
        mission_id="mission-1",
        action_id="action-1",
        target="tests/test_target.py",
        passed=True,
        strength=4,
        required_strength=3,
        evidence_ids=("verification-1",),
        workspace_digest="workspace-1",
        diff_digest="diff-1",
        environment_digest="env-1",
        command="pytest tests/test_target.py",
        output_digest="output-1",
        tool_version="pytest-1",
    )
    record = authority.promote(
        proposal,
        MemoryPromotionActor(
            actor_id="operator-1",
            actor_type="operator",
            authentication_event_id="auth-1",
            operator_approval=True,
        ),
        evidence=(verification,),
    )
    assert record.provenance.verification_strength == 4


def test_policy_actor_cannot_promote_operator_required_proposal(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    proposal = _proposal()
    authority.propose(proposal)
    with pytest.raises(MemoryPromotionDenied, match="operator approval"):
        authority.promote(
            proposal,
            MemoryPromotionActor(actor_id="policy-1", actor_type="policy"),
            evidence=(_evidence(),),
        )


def test_project_scoped_registry_recall_does_not_cross_projects(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    proposal = _proposal()
    authority.propose(proposal)
    record = authority.promote(
        proposal,
        MemoryPromotionActor(
            actor_id="operator-1",
            actor_type="operator",
            authentication_event_id="auth-1",
            operator_approval=True,
        ),
        evidence=(_evidence(),),
    )
    assert authority.recall("ignored", MemoryRecallContext(project_id="project-1"))[0].record_id == record.record_id
    assert authority.recall("ignored", MemoryRecallContext(project_id="project-2")) == ()


def test_router_chooses_one_specialized_adapter() -> None:
    class Adapter:
        memory_types = ("semantic",)

        def __init__(self) -> None:
            self.calls = 0

        def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
            self.calls += 1
            return (
                MemoryHit(
                    memory_type="semantic",
                    content_reference="semantic:1",
                    text=query,
                    verification_status="verified",
                    source="test",
                ),
            )

        def rebuild_derived_indexes(self) -> None:
            return None

    class Episodic(Adapter):
        memory_types = ("episodic",)

    semantic = Adapter()
    episodic = Episodic()
    authority = MemoryAuthority(
        store=MemoryAuthorityStore(":memory:"),
        adapters={"semantic": semantic, "episodic": episodic},
    )
    hits = authority.recall("hello", MemoryRecallContext(session_id="session-1"))
    assert hits and episodic.calls == 1
    assert semantic.calls == 0


def test_versioned_memory_migration_records_digest(tmp_path: Path) -> None:
    db_path = tmp_path / "migration.db"
    conn = sqlite3.connect(db_path)
    try:
        assert apply_migrations(conn, scope="memory") == [(2, "memory_provenance_v1")]
        assert apply_migrations(conn, scope="memory") == []
        row = conn.execute(
            "SELECT version, digest FROM schema_migrations WHERE version = 2"
        ).fetchone()
        assert row[0] == 2
        assert len(row[1]) == 64
    finally:
        conn.close()
