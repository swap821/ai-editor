"""Phase 2 slice 2.4: the operator's activation route works end to end, and only it.

Activation is the operator's act. Every other test of it builds a capability
proof by hand and calls the service; none drove the mounted route through the
real action guard (authenticated, re-authenticated session -> 428 capability
challenge -> retry with the server-issued token -> consumed proof). This pins
that path on a migrated candidate, because it is the one the operator will use
for the pilot.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import get_learning_service
from aios.api.main import app
from aios.application.learning.service import LearningService
from aios.application.missions.mission_service import MissionService
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.domain.learning.repository import SkillRecord, SkillRepository
from aios.domain.learning.trajectory_repository import TrajectoryRepository
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)

ROUTE = "/api/v1/skills/arc-migrated/versions/1/activate"


@pytest.fixture()
def library(tmp_path: Path):
    db = tmp_path / "operational.db"
    repository = SkillRepository(db)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    repository.save(
        SkillRecord(
            skill_id="arc-migrated",
            version=1,
            problem_signature="run the parser tests",
            applicability_conditions={},
            known_exclusions=[],
            required_inputs=[],
            required_project_state={},
            procedure=json.dumps(["verify: command=pytest tests/test_parser.py -q"]),
            allowed_tools=["verify"],
            allowed_scope_pattern="",
            expected_observations=[],
            verification_plan=None,
            escalation_conditions=[],
            source_trajectory_ids=[],
            confidence=0.8,
            success_count=4,
            failure_count=0,
            last_validated_versions=[],
            state="candidate",
            created_at=now,
            updated_at=now,
            provenance={
                "source": "migrated",
                "legacy_id": "41",
                "review_ready": "true",
            },
        )
    )
    service = LearningService(
        mission_service=MissionService(
            SqliteMissionRepository(tmp_path / "missions.db"),
            emergency_stop=UNGOVERNED_FIXTURE,
        ),
        trajectory_repository=TrajectoryRepository(db),
        skill_repository=repository,
        emergency_stop=UNGOVERNED_FIXTURE,
    )
    app.dependency_overrides[get_learning_service] = lambda: service
    try:
        yield repository
    finally:
        app.dependency_overrides.pop(get_learning_service, None)


def test_the_operator_route_activates_a_migrated_candidate(library) -> None:
    """Real middleware: authenticated operator session, the 428 challenge, and
    the retry with the server-issued capability (the harness replays it)."""
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        response = client.post(ROUTE, json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["state"], body["source"]) == (
        "active",
        "capability_backed_human_activation",
    )
    assert library.get("arc-migrated", 1).state == "active"


def test_without_the_capability_nothing_is_activated(library) -> None:
    """The first request only earns a challenge; the handler never runs."""
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        response = client.post(
            ROUTE, json={}, headers={"X-AIOS-No-Auto-Capability": "1"}
        )
    assert response.status_code == 428, response.text
    assert response.json()["detail"]["approvalToken"]
    assert library.get("arc-migrated", 1).state == "candidate"


def test_an_anonymous_caller_cannot_activate(library) -> None:
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        client.cookies.clear()
        response = client.post(ROUTE, json={})
    assert response.status_code in {401, 403}, response.text
    assert library.get("arc-migrated", 1).state == "candidate"
