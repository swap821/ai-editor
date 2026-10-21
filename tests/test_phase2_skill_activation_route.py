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

from aios.api.deps import get_learning_service, get_memory_authority
from aios.api.main import app
from aios.application.learning.service import (
    LearningService,
    SkillActivationAuthorization,
    SkillActivationDenied,
)
from aios.domain.capabilities.proof import ConsumedCapabilityProof
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


class _Signer:
    """The skills adapter's signing seam, recording what the route asked it to sign."""

    def __init__(self) -> None:
        self.signed: list[tuple[str, int, str]] = []

    def attest_activation(self, skill_id: str, version: int, *, approver: str) -> bool:
        self.signed.append((skill_id, version, approver))
        return True


@pytest.fixture()
def signer():
    fake = _Signer()

    class _Authority:
        adapters = {"skills": fake}

    app.dependency_overrides[get_memory_authority] = lambda: _Authority()
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_memory_authority, None)


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


def test_an_active_skill_is_confirmed_and_signed_not_reactivated(
    library, signer
) -> None:
    """2026-10-21: three skills were activated on a backend without the live
    key -- active, unsigned, inert -- and an active skill is not activatable
    again. The same capability-backed act now confirms it, and it is signed."""
    for state in ("human_reviewed", "active"):
        library.transition_state("arc-migrated", 1, state)
    before = library.get("arc-migrated", 1).model_dump()
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        response = client.post(ROUTE, json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["state"], body["signed"]) == (
        "already_active",
        "active",
        True,
    )
    assert [(sid, ver) for sid, ver, _ in signer.signed] == [("arc-migrated", 1)]
    assert library.get("arc-migrated", 1).model_dump() == before, "nothing changes"


def test_confirming_an_active_skill_needs_the_same_capability(library, signer) -> None:
    for state in ("human_reviewed", "active"):
        library.transition_state("arc-migrated", 1, state)
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        response = client.post(
            ROUTE, json={}, headers={"X-AIOS-No-Auto-Capability": "1"}
        )
    assert response.status_code == 428, response.text
    assert signer.signed == [], "no capability, no signature"


def _proof(route: str) -> ConsumedCapabilityProof:
    return ConsumedCapabilityProof(
        capability_id="cap-1",
        token_digest="token-digest",
        operator_id="operator-1",
        device_id="device-1",
        authentication_event_id="auth-1",
        session_id="session-1",
        action_type="skill_activation",
        route=route,
        http_method="POST",
        payload_digest="payload-digest",
        resource_digest="resource-digest",
        mission_id=None,
        contract_digest=None,
        policy_version="1.0",
        scope="skill-activation",
        verification_requirement="route_policy_v1",
        consumed_at=1.0,
        expires_at=9_999_999_999.0,
        revoked_at=None,
    )


def _service(library) -> LearningService:
    from aios.api.deps import get_learning_service as dep

    return app.dependency_overrides[dep]()


def test_only_an_active_skill_can_be_confirmed(library) -> None:
    auth = SkillActivationAuthorization(
        proof=_proof(ROUTE), skill_id="arc-migrated", version=1
    )
    with pytest.raises(SkillActivationDenied, match="only an active skill"):
        _service(library).confirm_activation(auth)
    assert library.get("arc-migrated", 1).state == "candidate"


def test_a_confirmation_checks_the_proof_as_activation_does(library) -> None:
    for state in ("human_reviewed", "active"):
        library.transition_state("arc-migrated", 1, state)
    other = "/api/v1/skills/arc-other/versions/1/activate"
    auth = SkillActivationAuthorization(
        proof=_proof(other), skill_id="arc-migrated", version=1
    )
    with pytest.raises(SkillActivationDenied, match="route mismatch"):
        _service(library).confirm_activation(auth)
