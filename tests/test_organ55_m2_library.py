"""Organ 55's M2 sees the institutional skill library, and judges it by the operator's act.

In pilot mode (Phase 2 slice 2.4) recall trusts ACTIVE institutional skills,
but M2 read only the legacy stores. For a library skill, "earned" is not a
strength label: activation is capability-backed, so an ACTIVE skill is earned
exactly when a CONSUMED capability exists for its own activation route. One
without it became active without the operator -- the false success M2 exists
to catch.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from aios.application.governance.governance_observation import (
    GovernanceObservationCollector,
    MemoryUnreadable,
    VerifiedMemoryReader,
)
from aios.domain.learning.repository import SkillRepository
from aios.infrastructure.capabilities.sqlite_store import CapabilityStore
from aios.memory.db import init_memory_db
from tests.helpers import seed_skill
from tests.test_phase2_institutional_store import _record
from tools.governance_conformance_runner import _adjudicate_m2


def _capability(
    path: Path, route: str, *, consumed: bool = True, revoked: bool = False
) -> None:
    CapabilityStore(path)  # the real schema
    now = time.time()
    conn = sqlite3.connect(path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(capabilities)")]
        values = {c: f"x-{c}" for c in cols}
        values.update(
            capability_id=f"cap-{route}-{consumed}-{revoked}",
            token_digest=f"digest-{route}-{consumed}-{revoked}",
            action_type="skill_activation",
            route=route,
            http_method="POST",
            issued_at=now,
            expires_at=now + 600,
            consumed_at=now if consumed else None,
            revoked_at=now if revoked else None,
            mission_id=None,
            contract_digest=None,
            action_payload_json=None,
        )
        conn.execute(
            f"INSERT INTO capabilities ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
            tuple(values.values()),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def stores(tmp_path: Path):
    memory = tmp_path / "memory.db"
    init_memory_db(memory)
    library = tmp_path / "operational.db"
    capabilities = tmp_path / "capabilities.db"
    return memory, library, capabilities


def _reader(stores) -> VerifiedMemoryReader:
    memory, library, capabilities = stores
    return VerifiedMemoryReader(
        memory, library_path=library, capability_path=capabilities
    )


def _activate(library: Path, skill_id: str) -> None:
    seed_skill(SkillRepository(library), _record(skill_id=skill_id, state="active"))


class TestLibrarySkillsAreJudgedByTheOperatorsAct:
    def test_an_active_skill_with_a_consumed_activation_capability_is_earned(
        self, stores
    ) -> None:
        _, library, capabilities = stores
        _activate(library, "arc-good")
        _capability(capabilities, "/api/v1/skills/arc-good/versions/1/activate")
        (row,) = [
            r for r in _reader(stores)._rows() if r["store"] == "institutional_skills"
        ]
        assert (row["id"], row["earned"]) == ("arc-good@v1", True)

    def test_an_active_skill_without_one_is_not_earned(self, stores) -> None:
        _, library, capabilities = stores
        _activate(library, "arc-self-made")
        _capability(capabilities, "/api/v1/skills/some-other-skill/versions/1/activate")
        (row,) = [
            r for r in _reader(stores)._rows() if r["store"] == "institutional_skills"
        ]
        assert row["earned"] is False

    @pytest.mark.parametrize("consumed,revoked", [(False, False), (True, True)])
    def test_an_unconsumed_or_revoked_capability_does_not_count(
        self, stores, consumed, revoked
    ) -> None:
        _, library, capabilities = stores
        _activate(library, "arc-x")
        _capability(
            capabilities,
            "/api/v1/skills/arc-x/versions/1/activate",
            consumed=consumed,
            revoked=revoked,
        )
        (row,) = [
            r for r in _reader(stores)._rows() if r["store"] == "institutional_skills"
        ]
        assert row["earned"] is False

    def test_a_candidate_is_not_trusted_memory(self, stores) -> None:
        _, library, _ = stores
        SkillRepository(library).save(_record(skill_id="arc-candidate"))
        assert not [
            r for r in _reader(stores)._rows() if r["store"] == "institutional_skills"
        ]


class TestItNeverConcludesFromWhatItCouldNotRead:
    def test_an_absent_library_is_legitimately_empty(self, stores) -> None:
        memory, library, _ = stores
        assert not library.exists()
        assert _reader(stores)._rows() == []
        assert not library.exists(), "reading must not create the library"

    def test_active_skills_with_no_capability_store_are_unread(self, stores) -> None:
        _, library, capabilities = stores
        _activate(library, "arc-y")
        assert not capabilities.exists()
        with pytest.raises(MemoryUnreadable, match="cannot be decided"):
            _reader(stores)._rows()

    def test_an_unreadable_library_is_unread(self, stores) -> None:
        _, library, _ = stores
        library.write_bytes(b"this is not a sqlite database" * 64)
        with pytest.raises(MemoryUnreadable, match="institutional skill library"):
            _reader(stores)._rows()


class TestM2FailsOnASelfActivatedSkill:
    def test_a_skill_made_active_without_the_operator_fails_m2(self, stores) -> None:
        memory, library, capabilities = stores
        SkillRepository(library).save(_record(skill_id="arc-sneaky"))
        _capability(capabilities, "/api/v1/skills/unrelated/versions/1/activate")
        collector = GovernanceObservationCollector(memory_reader=_reader(stores))
        snapshot = collector.begin()
        repository = SkillRepository(library)
        repository.transition_state("arc-sneaky", 1, "human_reviewed")
        repository.transition_state("arc-sneaky", 1, "active")  # no consumed capability
        observation = collector.collect(snapshot)
        assert "memory" in observation.collected
        verdict = _adjudicate_m2(observation)
        assert verdict.outcome == "failed"
        assert any(w["id"] == "arc-sneaky@v1" for w in verdict.evidence["writes"])


def test_the_real_activation_route_leaves_an_earned_skill(tmp_path: Path) -> None:
    """End to end: activate through the mounted route (real action guard,
    real consumed capability in the configured store), then M2 reads it."""
    from fastapi.testclient import TestClient

    from aios import config
    from aios.api.deps import get_learning_service
    from aios.api.main import app
    from aios.application.learning.service import LearningService
    from aios.application.missions.mission_service import MissionService
    from aios.core.autonomy import UNGOVERNED_FIXTURE
    from aios.domain.learning.trajectory_repository import TrajectoryRepository
    from aios.infrastructure.missions.sqlite_mission_repository import (
        SqliteMissionRepository,
    )

    library = tmp_path / "operational.db"
    repository = SkillRepository(library)
    repository.save(_record(skill_id="arc-real"))
    service = LearningService(
        mission_service=MissionService(
            SqliteMissionRepository(tmp_path / "missions.db"),
            emergency_stop=UNGOVERNED_FIXTURE,
        ),
        trajectory_repository=TrajectoryRepository(library),
        skill_repository=repository,
        emergency_stop=UNGOVERNED_FIXTURE,
    )
    app.dependency_overrides[get_learning_service] = lambda: service
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.post(
                "/api/v1/skills/arc-real/versions/1/activate", json={}
            )
    finally:
        app.dependency_overrides.pop(get_learning_service, None)
    assert response.status_code == 200, response.text
    memory = tmp_path / "memory.db"
    init_memory_db(memory)
    reader = VerifiedMemoryReader(
        memory, library_path=library, capability_path=Path(config.CAPABILITY_DB_PATH)
    )
    (row,) = [r for r in reader._rows() if r["store"] == "institutional_skills"]
    assert (row["id"], row["earned"]) == ("arc-real@v1", True)
