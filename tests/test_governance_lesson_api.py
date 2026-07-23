"""HTTP-level coverage for the Constitutional Learning Organ's routes
(organ 46) -- aios/api/routes/governance.py's lesson propose/draft-amendment/
check-simulations surface.

`TestClient` is globally patched by conftest.py to bootstrap a privileged
Human Sovereign session for loopback clients and to automatically retry a
428 capability challenge with the issued token.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import get_governance_amendment_store
from aios.api.main import app
from aios.domain.governance.learning import ADVERSARIAL_SIMULATION_CHECKS
from aios.infrastructure.governance.sqlite_store import GovernanceAmendmentStore


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    store = GovernanceAmendmentStore(tmp_path / "amendments.db")
    app.dependency_overrides[get_governance_amendment_store] = lambda: store
    try:
        with TestClient(app, client=("127.0.0.1", 12346)) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _propose_lesson_body(**overrides: object) -> dict:
    body = {
        "lesson_id": "lesson-1",
        "problem_class": "approval_friction",
        "evidence_refs": ["incident-42"],
        "observed_harm": "operators waited too long for routine approvals",
        "current_rule": "every YELLOW action requires fresh reauth",
        "proposed_improvement": "cache reauth for a short trusted window",
        "confidence": 0.7,
    }
    body.update(overrides)
    return body


def test_propose_lesson_persists_and_returns_the_real_lesson(client) -> None:
    resp = client.post(
        "/api/v1/governance/lessons/propose", json=_propose_lesson_body()
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["lesson_id"] == "lesson-1"
    assert body["status"] == "proposed"
    assert body["amendment_proposal_id"] is None

    fetched = client.get("/api/v1/governance/lessons/lesson-1")
    assert fetched.status_code == 200
    assert fetched.json()["lesson_id"] == "lesson-1"


def test_get_unknown_lesson_is_404(client) -> None:
    resp = client.get("/api/v1/governance/lessons/no-such-lesson")
    assert resp.status_code == 404


def test_draft_amendment_from_lesson_produces_a_real_amendment_proposal(
    client,
) -> None:
    client.post("/api/v1/governance/lessons/propose", json=_propose_lesson_body())

    resp = client.post(
        "/api/v1/governance/lessons/lesson-1/draft-amendment",
        json={
            "proposal_id": "amend-from-lesson-1",
            "target_articles": ["article-9-reauth-policy"],
            "proposed_diff": "cache reauth for a short trusted window",
            "migration_plan": "roll out behind a flag",
            "rollback_plan": "flip the flag back",
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["lesson"]["status"] == "amendment_drafted"
    assert body["lesson"]["amendment_proposal_id"] == "amend-from-lesson-1"
    assert body["proposal"]["proposal_id"] == "amend-from-lesson-1"
    assert body["proposal"]["proposer_type"] == "model"

    # The lesson's own history now shows both revisions.
    history = client.get("/api/v1/governance/lessons/lesson-1/history")
    statuses = [item["status"] for item in history.json()["items"]]
    assert statuses == ["proposed", "amendment_drafted"]

    # The drafted proposal is a real, independently fetchable amendment.
    proposal = client.get("/api/v1/governance/amendments/amend-from-lesson-1")
    assert proposal.status_code == 200
    assert proposal.json()["status"] == "proposed"


def test_draft_amendment_refuses_an_authority_reducing_proposed_diff(client) -> None:
    client.post("/api/v1/governance/lessons/propose", json=_propose_lesson_body())

    resp = client.post(
        "/api/v1/governance/lessons/lesson-1/draft-amendment",
        json={
            "proposal_id": "amend-bad",
            "target_articles": ["article-9"],
            "proposed_diff": "auto-approve routine actions without human review",
            "migration_plan": "roll out",
            "rollback_plan": "revert",
        },
    )

    assert resp.status_code == 409
    assert "authority-reduction" in resp.json()["detail"]


def test_draft_amendment_from_unknown_lesson_is_404(client) -> None:
    resp = client.post(
        "/api/v1/governance/lessons/no-such-lesson/draft-amendment",
        json={
            "proposal_id": "amend-x",
            "target_articles": ["article-1"],
            "proposed_diff": "do a thing",
            "migration_plan": "roll out",
            "rollback_plan": "revert",
        },
    )
    assert resp.status_code == 404


def test_check_simulations_ready_when_all_nine_pass(client) -> None:
    resp = client.post(
        "/api/v1/governance/lessons/check-simulations",
        json={
            "results": [
                {"check_name": name, "passed": True}
                for name in ADVERSARIAL_SIMULATION_CHECKS
            ]
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ready": True, "reason": ""}


def test_check_simulations_not_ready_when_one_is_missing(client) -> None:
    incomplete = list(ADVERSARIAL_SIMULATION_CHECKS)[:-1]

    resp = client.post(
        "/api/v1/governance/lessons/check-simulations",
        json={
            "results": [
                {"check_name": name, "passed": True} for name in incomplete
            ]
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready"] is False
    assert "missing" in body["reason"]


def test_check_simulations_not_ready_when_one_failed(client) -> None:
    results = [
        {"check_name": name, "passed": name != "provider_lock_in"}
        for name in ADVERSARIAL_SIMULATION_CHECKS
    ]

    resp = client.post(
        "/api/v1/governance/lessons/check-simulations",
        json={"results": results},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready"] is False
    assert "provider_lock_in" in body["reason"]
