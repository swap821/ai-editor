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


def _draft_amendment(client, *, proposal_id: str, proposed_diff: str, rollback_plan: str = "revert") -> None:
    client.post("/api/v1/governance/lessons/propose", json=_propose_lesson_body())
    resp = client.post(
        "/api/v1/governance/lessons/lesson-1/draft-amendment",
        json={
            "proposal_id": proposal_id,
            "target_articles": ["article-9-reauth-policy"],
            "proposed_diff": proposed_diff,
            "migration_plan": "roll out behind a flag",
            "rollback_plan": rollback_plan,
        },
    )
    assert resp.status_code == 200, resp.text


def test_check_simulations_runs_all_nine_for_real_and_is_ready_for_a_clean_proposal(
    client,
) -> None:
    _draft_amendment(
        client, proposal_id="amend-clean", proposed_diff="cache reauth for a short trusted window"
    )

    resp = client.post(
        "/api/v1/governance/lessons/check-simulations",
        json={"proposal_id": "amend-clean"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready"] is True
    assert body["reason"] == ""
    checked_names = {r["check_name"] for r in body["results"]}
    assert checked_names == set(ADVERSARIAL_SIMULATION_CHECKS)
    assert all(r["passed"] for r in body["results"])


def test_check_simulations_catches_a_risky_proposal_a_caller_never_disclosed(
    client,
) -> None:
    """The whole point of running simulations for real: a caller cannot
    simply assert `passed: True` for a proposal that actually reduces
    provider diversity and blocks rollback."""
    _draft_amendment(
        client,
        proposal_id="amend-risky",
        proposed_diff="remove ollama and require openai only for all requests",
        rollback_plan="cannot be undone once cutover completes",
    )

    resp = client.post(
        "/api/v1/governance/lessons/check-simulations",
        json={"proposal_id": "amend-risky"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready"] is False
    assert "provider_lock_in" in body["reason"]
    results_by_name = {r["check_name"]: r for r in body["results"]}
    assert results_by_name["provider_lock_in"]["passed"] is False
    assert results_by_name["reduced_human_reversibility"]["passed"] is False
    # Checks unrelated to this proposal's risky language still pass.
    assert results_by_name["capability_replay"]["passed"] is True


def test_check_simulations_unknown_proposal_is_404(client) -> None:
    resp = client.post(
        "/api/v1/governance/lessons/check-simulations",
        json={"proposal_id": "no-such-proposal"},
    )
    assert resp.status_code == 404
