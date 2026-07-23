"""HTTP-level coverage for the Constitutional Amendment Authority's routes
(organ 45) -- aios/api/routes/governance.py's propose/critique/simulate/
reject/ratify/activate surface.

`TestClient` is globally patched by conftest.py to bootstrap a privileged
Human Sovereign session for loopback clients and to automatically retry a
428 capability challenge with the issued token -- these tests exercise the
real two-phase YELLOW protocol end to end, not a mocked shortcut.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import get_governance_amendment_store
from aios.api.main import app
from aios.infrastructure.governance.sqlite_store import GovernanceAmendmentStore


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    store = GovernanceAmendmentStore(tmp_path / "amendments.db")
    app.dependency_overrides[get_governance_amendment_store] = lambda: store
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _propose_body(**overrides: object) -> dict:
    body = {
        "proposal_id": "amend-1",
        "target_articles": ["article-3-provider-routing"],
        "proposed_diff": "prefer local providers under budget pressure",
        "motivation": "reduce cloud spend",
        "migration_plan": "roll out behind a flag",
        "rollback_plan": "flip the flag back",
    }
    body.update(overrides)
    return body


def test_propose_amendment_persists_and_returns_the_real_proposal(client) -> None:
    resp = client.post("/api/v1/governance/amendments/propose", json=_propose_body())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["proposal_id"] == "amend-1"
    assert body["status"] == "proposed"
    assert body["proposer_type"] == "human"
    assert body["proposed_by"], "proposed_by must be derived from the real principal"

    fetched = client.get("/api/v1/governance/amendments/amend-1")
    assert fetched.status_code == 200
    assert fetched.json()["proposal_id"] == "amend-1"


def test_get_unknown_amendment_is_404(client) -> None:
    resp = client.get("/api/v1/governance/amendments/no-such-proposal")
    assert resp.status_code == 404


def test_critique_and_simulate_advance_status_without_ratifying(client) -> None:
    client.post("/api/v1/governance/amendments/propose", json=_propose_body())

    critiqued = client.post(
        "/api/v1/governance/amendments/amend-1/critique",
        json={"critique_text": "consider latency impact"},
    )
    assert critiqued.status_code == 200, critiqued.text
    assert critiqued.json()["status"] == "critiqued"
    assert "consider latency impact" in critiqued.json()["critiques"]

    simulated = client.post(
        "/api/v1/governance/amendments/amend-1/simulate",
        json={"simulation_note": "dry run shows a 12% cost drop"},
    )
    assert simulated.status_code == 200, simulated.text
    assert simulated.json()["status"] == "simulated"

    history = client.get("/api/v1/governance/amendments/amend-1/history")
    assert history.status_code == 200
    statuses = [item["status"] for item in history.json()["items"]]
    assert statuses == ["proposed", "critiqued", "simulated"]


def test_reject_amendment(client) -> None:
    client.post("/api/v1/governance/amendments/propose", json=_propose_body())

    resp = client.post(
        "/api/v1/governance/amendments/amend-1/reject",
        json={"reason": "insufficient evidence"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"


def test_ratify_amendment_consumes_a_real_exact_capability(client) -> None:
    client.post("/api/v1/governance/amendments/propose", json=_propose_body())

    resp = client.post("/api/v1/governance/amendments/amend-1/ratify", json={})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ratified"
    assert body["ratified_by_operator_id"]
    assert body["ratification_capability_digest"]


def test_ratify_a_foundation_law_touching_proposal_is_refused(client) -> None:
    client.post(
        "/api/v1/governance/amendments/propose",
        json=_propose_body(
            proposal_id="amend-foundation",
            target_articles=["article-1-self-approval"],
            proposed_diff="allow limited no model self-approval under supervision",
        ),
    )

    resp = client.post(
        "/api/v1/governance/amendments/amend-foundation/ratify", json={}
    )

    assert resp.status_code == 409
    assert "foundation" in resp.json()["detail"].lower()


def test_ratify_unknown_proposal_is_404(client) -> None:
    resp = client.post("/api/v1/governance/amendments/no-such-proposal/ratify", json={})
    assert resp.status_code == 404


def test_activate_requires_ratification_first(client) -> None:
    client.post("/api/v1/governance/amendments/propose", json=_propose_body())

    resp = client.post("/api/v1/governance/amendments/amend-1/activate", json={})

    assert resp.status_code == 409
    assert "ratif" in resp.json()["detail"].lower()


def test_ratify_then_activate_chains_a_real_next_constitution_snapshot(client) -> None:
    client.post("/api/v1/governance/amendments/propose", json=_propose_body())
    client.post("/api/v1/governance/amendments/amend-1/ratify", json={})

    resp = client.post("/api/v1/governance/amendments/amend-1/activate", json={})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["proposal"]["status"] == "activated"
    assert len(body["newConstitutionDigest"]) == 64  # sha256 hex digest


def test_cannot_critique_an_already_rejected_proposal(client) -> None:
    client.post("/api/v1/governance/amendments/propose", json=_propose_body())
    client.post(
        "/api/v1/governance/amendments/amend-1/reject", json={"reason": "no"}
    )

    resp = client.post(
        "/api/v1/governance/amendments/amend-1/critique",
        json={"critique_text": "too late"},
    )

    assert resp.status_code == 409
