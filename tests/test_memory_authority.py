from __future__ import annotations

import sqlite3
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
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.facts import FactWriteResult


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


def test_consolidator_refuses_implicit_legacy_stores() -> None:
    """Consolidation must not open a parallel memory graph by default."""
    with pytest.raises(
        RuntimeError, match="MemoryAuthority or explicit memory stores"
    ):
        MemoryConsolidator()


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
    assert (
        authority.recall("ignored", MemoryRecallContext(project_id="project-1"))[
            0
        ].record_id
        == record.record_id
    )
    assert (
        authority.recall("ignored", MemoryRecallContext(project_id="project-2")) == ()
    )


def test_recall_trust_preserves_unverified_and_advisory_status(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    assert (
        authority.trust_level(
            MemoryHit(
                memory_type="chat",
                content_reference="chat:1",
                verification_status="unverified",
                source="test",
            )
        )
        == "unknown"
    )
    advisory = MemoryHit(
        memory_type="pheromone",
        content_reference="pheromone:1",
        verification_status="advisory",
        source="test",
        advisory=True,
    )
    assert authority.trust_level(advisory) == "advisory"
    assert not authority.is_trusted(advisory)


def test_memory_search_event_uses_authority_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aios.api.routes.memory import MemorySearchRequest, memory_search

    hit = MemoryHit(
        memory_type="chat",
        content_reference="chat:unverified",
        text="unverified recall",
        verification_status="unverified",
        source="test",
    )

    class FakeAuthority:
        def recall(
            self, _query: str, _context: MemoryRecallContext
        ) -> tuple[MemoryHit, ...]:
            return (hit,)

        @staticmethod
        def trust_level(_hit: MemoryHit) -> str:
            return "unknown"

        @staticmethod
        def is_trusted(_hit: MemoryHit) -> bool:
            return False

    class FakeBus:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def append(self, _event_type: str, _event_id: str, payload: dict) -> None:
            self.events.append(payload)

    bus = FakeBus()
    monkeypatch.setattr("aios.api.main.get_cortex_bus", lambda: bus)
    result = memory_search(
        MemorySearchRequest(query="unverified", top_k=1),
        authority=FakeAuthority(),
    )

    assert result["results"][0]["verification_status"] == "unverified"
    assert bus.events[0]["trust"] == "unknown"


def test_specialized_recall_reads_route_through_authority_adapters(
    tmp_path: Path,
) -> None:
    class Facts:
        memory_types = ("fact",)

        def search(self, _query: str) -> list[dict[str, str]]:
            return [{"subject": "operator", "predicate": "uses", "object": "GAGOS"}]

        def facts_for(self, _subject: str) -> list[dict[str, str]]:
            return [{"subject": "operator"}]

        def neighbors(self, _subject: str) -> list[dict[str, str]]:
            return []

        def traverse_weighted(self, _subject: str) -> list[object]:
            return []

        def rebuild_derived_indexes(self) -> None:
            return None

    class Skills:
        memory_types = ("skill",)

        def relevant_verified(self, _query: str, _limit: int) -> list[dict[str, str]]:
            return [{"goal_pattern": "ship", "steps": []}]

        def rebuild_derived_indexes(self) -> None:
            return None

    class Lessons:
        memory_types = ("lesson",)

        def recall_relevant(
            self, _query: str, _task_id: str, _limit: int
        ) -> list[dict[str, str]]:
            return [{"lesson_text": "verify first"}]

        def recurring(self, limit: int = 3) -> list[dict[str, str]]:
            return []

        def rebuild_derived_indexes(self) -> None:
            return None

    class Development:
        memory_types = ("development",)

        def task_profile(self) -> dict[str, tuple[int, float]]:
            return {}

        def rebuild_derived_indexes(self) -> None:
            return None

    authority = MemoryAuthority(
        store=MemoryAuthorityStore(tmp_path / "memory.db"),
        adapters={
            "facts": Facts(),
            "skills": Skills(),
            "lessons": Lessons(),
            "development": Development(),
        },
    )

    assert authority.facts_search("GAGOS")[0]["object"] == "GAGOS"
    assert authority.facts_for("operator")
    assert authority.recall_skills("ship", 1)[0]["goal_pattern"] == "ship"
    assert (
        authority.recall_lessons("verify", "session", 1)[0]["lesson_text"]
        == "verify first"
    )
    assert authority.self_model() == ""


def test_trusted_workflow_event_uses_canonical_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aios.api.routes.memory import MemorySearchRequest, memory_search

    hit = MemoryHit(
        memory_type="workflow",
        content_reference="workflow:trusted",
        text="verified workflow",
        verification_status="verified",
        source="test",
    )

    class FakeAuthority:
        def recall(
            self, _query: str, _context: MemoryRecallContext
        ) -> tuple[MemoryHit, ...]:
            return (hit,)

        @staticmethod
        def trust_level(_hit: MemoryHit) -> str:
            return "verified"

        @staticmethod
        def is_trusted(_hit: MemoryHit) -> bool:
            return True

    class FakeBus:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def append(self, _event_type: str, _event_id: str, payload: dict) -> None:
            self.events.append(payload)

    bus = FakeBus()
    monkeypatch.setattr("aios.api.main.get_cortex_bus", lambda: bus)
    memory_search(
        MemorySearchRequest(query="workflow", top_k=1),
        authority=FakeAuthority(),
    )

    assert bus.events[1]["phase"] == "wonder"


def test_router_chooses_one_specialized_adapter() -> None:
    class Adapter:
        memory_types = ("semantic",)

        def __init__(self) -> None:
            self.calls = 0

        def recall(
            self, query: str, context: MemoryRecallContext
        ) -> tuple[MemoryHit, ...]:
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


def test_migration_digest_falls_back_when_source_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aios.infrastructure.storage import migrations

    conn = sqlite3.connect(":memory:")

    def unavailable_source(_migration: object) -> str:
        raise OSError("source unavailable")

    monkeypatch.setattr(migrations.inspect, "getsource", unavailable_source)

    assert migrations.apply_migrations(conn, scope="memory") == [
        (2, "memory_provenance_v1")
    ]
    digest = conn.execute(
        "SELECT digest FROM schema_migrations WHERE version = 2"
    ).fetchone()[0]
    assert len(digest) == 64


def test_specialized_write_operations_dispatch_through_authority() -> None:
    class Facts:
        memory_types = ("fact",)

        def strengthen_or_propose(self, *args, **kwargs):
            return ("fact", args, kwargs)

        def rebuild_derived_indexes(self) -> None:
            return None

    class Skills:
        memory_types = ("skill",)

        def record_attempt(self, *args, **kwargs):
            return 7

        def record_reuse(self, *args, **kwargs):
            return [8]

        def rebuild_derived_indexes(self) -> None:
            return None

    class Lessons:
        memory_types = ("lesson",)

        def record_or_increment(self, *args, **kwargs):
            return (9, True)

        def get(self, mistake_id):
            return mistake_id

        def promote(self, mistake_id, **kwargs):
            return None

        def pending_command_pairs(self, task_id):
            return [(1, task_id)]

        def rebuild_derived_indexes(self) -> None:
            return None

    class Development:
        memory_types = ("development",)

        def record(self, *args, **kwargs):
            return 10

        def rebuild_derived_indexes(self) -> None:
            return None

    class Consolidation:
        memory_types = ("promotion",)

        def consolidate_lesson(self, mistake_id):
            return mistake_id

        def rebuild_derived_indexes(self) -> None:
            return None

    authority = MemoryAuthority(
        store=MemoryAuthorityStore(":memory:"),
        adapters={
            "facts": Facts(),
            "skills": Skills(),
            "lessons": Lessons(),
            "development": Development(),
            "consolidation": Consolidation(),
        },
    )

    assert authority.facts_strengthen_or_propose("s", "p", "o")[0] == "fact"
    assert authority.record_skill_attempt("goal", ["step"], success=True) == 7
    assert authority.record_skill_reuse([7], success=True) == [8]
    assert authority.record_lesson_or_increment(
        "task", "error", "root", "fix", "lesson", -0.1
    ) == (9, True)
    assert authority.lesson_get(9) == 9
    assert authority.pending_lesson_commands("task") == [(1, "task")]
    assert authority.record_development("task", "unverified") == 10
    assert authority.consolidate_lesson(9) == 9


def test_consolidator_routes_fact_reconciliation_and_supersession_through_authority(
    tmp_path: Path,
) -> None:
    class Facts:
        db_path = tmp_path / "facts.db"

        def add_fact(self, *args, **kwargs):
            raise AssertionError("direct fact promotion bypassed authority")

        def facts_for(self, *args, **kwargs):
            raise AssertionError("direct fact recall bypassed authority")

        def reconcile(self, *args, **kwargs):
            raise AssertionError("direct fact reconciliation bypassed authority")

    class Semantic:
        db_path = tmp_path / "semantic.db"

        def add(self, *args, **kwargs):
            raise AssertionError("direct semantic promotion bypassed authority")

        def promote(self, *args, **kwargs):
            raise AssertionError("direct semantic verification bypassed authority")

        def supersede_text(self, *args, **kwargs):
            raise AssertionError("direct semantic supersession bypassed authority")

    class Authority:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        @staticmethod
        def owns_store(name: str, store: object) -> bool:
            return name in {"facts", "semantic"}

        def facts_add_fact(self, *args, **kwargs) -> FactWriteResult:
            self.calls.append(("facts_add_fact", (args, kwargs)))
            return FactWriteResult(True, 1, "committed")

        def facts_for(self, subject: str, predicate: str) -> list[dict[str, str]]:
            self.calls.append(("facts_for", (subject, predicate)))
            return [{"subject": subject, "predicate": predicate, "object": "old"}]

        def facts_reconcile(self, *args, **kwargs) -> FactWriteResult:
            self.calls.append(("facts_reconcile", (args, kwargs)))
            return FactWriteResult(True, 2, "reconciled")

        def semantic_add_verified(self, *args, **kwargs) -> int:
            self.calls.append(("semantic_add_verified", (args, kwargs)))
            return 3

        def semantic_supersede_text(self, text: str) -> int:
            self.calls.append(("semantic_supersede_text", text))
            return 1

    authority = Authority()
    consolidator = MemoryConsolidator(
        tmp_path / "memory.db",
        semantic=Semantic(),
        mistakes=object(),
        facts=Facts(),
        memory_authority=authority,
    )

    assert consolidator.promote_fact(
        "service", "host", "local", approved_by="op"
    ).committed
    assert (
        consolidator.reconcile_fact(
            "service", "host", "remote", approved_by="op"
        ).reason
        == "reconciled"
    )
    assert [name for name, _ in authority.calls] == [
        "facts_add_fact",
        "semantic_add_verified",
        "facts_for",
        "facts_reconcile",
        "semantic_supersede_text",
        "semantic_add_verified",
    ]


def test_consolidator_bulk_run_routes_status_reads_through_authority(
    tmp_path: Path,
) -> None:
    class Lessons:
        db_path = tmp_path / "lessons.db"

        def get(self, *args, **kwargs):
            raise AssertionError("direct lesson read bypassed authority")

    class Facts:
        db_path = tmp_path / "facts.db"

    class Semantic:
        db_path = tmp_path / "semantic.db"

        def add(self, *args, **kwargs):
            raise AssertionError("direct semantic promotion bypassed authority")

        def promote(self, *args, **kwargs):
            raise AssertionError("direct semantic verification bypassed authority")

        def supersede_text(self, *args, **kwargs):
            raise AssertionError("direct semantic supersession bypassed authority")

    verified_lesson = {
        "id": 1,
        "error_type": "timeout",
        "root_cause": "slow dependency",
        "lesson_text": "bound the wait",
        "verification_status": "verified",
    }
    superseded_lesson = {
        **verified_lesson,
        "id": 2,
        "verification_status": "superseded",
    }
    active_fact = {
        "id": 3,
        "subject": "service",
        "predicate": "host",
        "object": "local",
        "approved_by": "operator",
    }
    superseded_fact = {
        **active_fact,
        "id": 4,
        "object": "remote",
        "status": "superseded",
    }

    class Authority:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        @staticmethod
        def owns_store(name: str, store: object) -> bool:
            return name in {"lessons", "facts", "semantic"}

        def lessons_by_status(self, status: str) -> list[dict[str, object]]:
            self.calls.append(("lessons_by_status", status))
            return [verified_lesson] if status == "verified" else [superseded_lesson]

        def facts_by_status(self, status: str) -> list[dict[str, object]]:
            self.calls.append(("facts_by_status", status))
            return [active_fact] if status == "active" else [superseded_fact]

        def lesson_get(self, mistake_id: int) -> dict[str, object]:
            self.calls.append(("lesson_get", mistake_id))
            return verified_lesson

        def semantic_supersede_text(self, text: str) -> int:
            self.calls.append(("semantic_supersede_text", text))
            return 1

        def semantic_add_verified(self, *args, **kwargs) -> int:
            self.calls.append(("semantic_add_verified", (args, kwargs)))
            return 10 if kwargs["memory_type"] == "lesson" else 11

    authority = Authority()
    result = MemoryConsolidator(
        tmp_path / "memory.db",
        semantic=Semantic(),
        mistakes=Lessons(),
        facts=Facts(),
        memory_authority=authority,
    ).run()

    assert result == {
        "verified_lessons_consolidated": 1,
        "active_facts_consolidated": 1,
        "superseded_memories": 2,
        "semantic_ids": [10, 11],
    }
    assert [name for name, _ in authority.calls] == [
        "lessons_by_status",
        "lessons_by_status",
        "facts_by_status",
        "facts_by_status",
        "semantic_supersede_text",
        "semantic_supersede_text",
        "lesson_get",
        "semantic_add_verified",
        "semantic_add_verified",
    ]


def test_default_confidence_calibration_routes_memory_reads_through_authority(
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    from aios.api.turn_pipeline import _calibrate_default_confidence

    class Lessons:
        db_path = tmp_path / "lessons.db"

        def relevant_verified(self, *args, **kwargs):
            raise AssertionError("direct lesson calibration read bypassed authority")

    class Development:
        db_path = tmp_path / "development.db"

        def relevant_success_rate(self, *args, **kwargs):
            raise AssertionError(
                "direct development calibration read bypassed authority"
            )

    class Skills:
        db_path = tmp_path / "skills.db"

        def relevant_verified(self, *args, **kwargs):
            raise AssertionError("direct skill calibration read bypassed authority")

    class Reflector:
        mistakes = Lessons()

    class Authority:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        @staticmethod
        def owns_store(name: str, store: object) -> bool:
            return name in {"lessons", "development", "skills"}

        def recall_verified_lessons(self, query: str, limit: int):
            self.calls.append(("recall_verified_lessons", (query, limit)))
            return [
                {
                    "mistake_id": 7,
                    "confidence_delta": -0.1,
                    "relevance": 1.0,
                }
            ]

        def development_success_rate(self, query: str):
            self.calls.append(("development_success_rate", query))
            return SimpleNamespace(attempts=4, success_rate=0.75, relevance=1.0)

        def recall_skills(self, query: str, limit: int):
            self.calls.append(("recall_skills", (query, limit)))
            return [{"skill_id": 8, "strength": 0.2, "relevance": 1.0}]

    authority = Authority()
    final, evidence = _calibrate_default_confidence(
        "ship the fix",
        0.5,
        reflector=Reflector(),
        development=Development(),
        skills=Skills(),
        authority=authority,
    )

    assert final == 0.675
    assert evidence["lesson_ids"] == [7]
    assert evidence["skill_ids"] == [8]
    assert [name for name, _ in authority.calls] == [
        "recall_verified_lessons",
        "development_success_rate",
        "recall_skills",
    ]


def test_reflection_recall_routes_pending_and_relevant_lessons_through_authority(
    tmp_path: Path,
) -> None:
    from aios.agents.reflection_agent import ReflectionAgent

    class Lessons:
        db_path = tmp_path / "lessons.db"

        def pending_for_task(self, *args, **kwargs):
            raise AssertionError("direct pending lesson read bypassed authority")

        def relevant_verified(self, *args, **kwargs):
            raise AssertionError("direct verified lesson read bypassed authority")

    class Authority:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def pending_lessons_for_task(self, task_id: str, limit: int):
            self.calls.append(("pending_lessons_for_task", (task_id, limit)))
            return [{"id": 3, "error_type": "PathNotFound", "lesson_text": "verify"}]

        def recall_lessons(self, query: str, task_id: str, limit: int):
            self.calls.append(("recall_lessons", (query, task_id, limit)))
            return [{"mistake_id": 3, "lesson_text": "verify"}]

    authority = Authority()
    agent = ReflectionAgent(object(), mistakes=Lessons(), memory_authority=authority)

    assert agent.recall_pending("session", 1)[0]["mistake_id"] == 3
    assert agent.recall_relevant("query", "session", 1)[0]["mistake_id"] == 3
    assert [name for name, _ in authority.calls] == [
        "pending_lessons_for_task",
        "recall_lessons",
    ]
