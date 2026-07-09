from __future__ import annotations

from pathlib import Path

from aios.learning.meta_loop import (
    MetaLoopSnapshot,
    assess_meta_loop,
    collect_meta_loop_evidence,
)
from aios.policy.engine import PolicyEngine, PolicyStatus
from aios.runtime.hibernation import HibernationReport


def _hibernation_report(**overrides: object) -> HibernationReport:
    data: dict[str, object] = {
        "mode": "hibernation",
        "local_only": True,
        "writes_performed": False,
        "cloud_calls": 0,
        "compaction": {"dry_run": True, "semantic_unverified_chat_removed": 3},
        "pheromones": {"dry_run": True, "signals_seen": 2, "decay_performed": False},
        "project_passport": {"activation": "proposal/evidence"},
        "audit_summary": {"exists": True, "tables": {"audit_log": 4}, "error": ""},
        "proposals": ["review stale local lessons"],
        "resource_status": {"mode": "hibernation", "cloud_allowed": False},
    }
    data.update(overrides)
    return HibernationReport(**data)  # type: ignore[arg-type]


def test_meta_loop_assessment_is_local_proposal_evidence_only() -> None:
    snapshot = MetaLoopSnapshot(
        reflections=[
            {"lesson": "poll exact GitHub run IDs before reporting green", "confidence": 0.87}
        ],
        mistakes=[
            {
                "error_type": "ci_polling",
                "lesson_text": "do not trust stale CI state",
                "occurrence_count": 3,
                "verification_status": "verified",
            }
        ],
        skills=[
            {
                "goal_pattern": "land a guarded architecture slice",
                "status": "candidate",
                "success_count": 2,
                "failure_count": 1,
            }
        ],
        audit_events=[{"risk": "YELLOW", "summary": "approval evidence pending"}],
        policies=[
            {
                "policy_id": "p1",
                "status": "proposed",
                "constraint": "agents must always record CI evidence",
            }
        ],
        hibernation=_hibernation_report().to_dict(),
        council_deliberations=[
            {
                "risk": "YELLOW",
                "payload": {
                    "synthesis": {
                        "status": "needs_review",
                        "security_veto": False,
                    }
                },
            }
        ],
    )

    assessment = assess_meta_loop(snapshot)

    assert assessment.activation == "proposal/evidence"
    assert assessment.authority == "proposal/evidence"
    assert assessment.local_only is True
    assert assessment.cloud_calls == 0
    assert assessment.writes_performed is False
    assert assessment.policy_mutations == 0
    assert assessment.self_apply_attempted is False
    assert assessment.can_authorize is False
    assert assessment.safety_status == "advisory"
    assert {source.name for source in assessment.sources} >= {
        "reflection",
        "mistake",
        "skill",
        "audit",
        "policy",
        "hibernation",
        "council",
    }
    assert assessment.proposals
    assert all(proposal.authority == "proposal/evidence" for proposal in assessment.proposals)
    assert all(proposal.requires_human_review is True for proposal in assessment.proposals)
    assert all(proposal.can_auto_apply is False for proposal in assessment.proposals)


def test_meta_loop_collects_policy_evidence_without_mutating_policy_engine(
    tmp_path: Path,
) -> None:
    engine = PolicyEngine(db_path=tmp_path / "policy.db")
    policy_id = engine.propose(
        "agents must always keep meta-loop output advisory",
        "queen-reflect",
    )
    before = [(policy.policy_id, policy.status) for policy in engine.policy_chain()]

    snapshot = collect_meta_loop_evidence(
        policy_engine=engine,
        hibernation_report=_hibernation_report(),
    )
    assessment = assess_meta_loop(snapshot)

    after = [(policy.policy_id, policy.status) for policy in engine.policy_chain()]
    assert before == after == [(policy_id, PolicyStatus.PROPOSED)]
    assert assessment.policy_mutations == 0
    assert any(proposal.kind == "policy_review" for proposal in assessment.proposals)


def test_meta_loop_blocks_unsafe_hibernation_evidence_without_authorizing_action() -> None:
    snapshot = collect_meta_loop_evidence(
        hibernation_report=_hibernation_report(
            local_only=False,
            cloud_calls=1,
            writes_performed=True,
        )
    )

    assessment = assess_meta_loop(snapshot)

    assert assessment.safety_status == "blocked"
    assert assessment.local_only is True
    assert assessment.cloud_calls == 0
    assert assessment.writes_performed is False
    assert assessment.can_authorize is False
    assert any("hibernation" in blocker.lower() for blocker in assessment.blockers)
    assert all(proposal.can_auto_apply is False for proposal in assessment.proposals)


def test_meta_loop_redacts_secret_like_evidence() -> None:
    snapshot = MetaLoopSnapshot(
        audit_events=[
            {
                "risk": "RED",
                "summary": "operator pasted sk-test-1234567890abcdef1234567890abcdef",
            }
        ]
    )

    payload = assess_meta_loop(snapshot).as_dict()

    assert "sk-test-1234567890abcdef1234567890abcdef" not in str(payload)
    assert "<REDACTED:" in str(payload)
