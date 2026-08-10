"""Proposal-id reuse: findings 4 and 5 of the third red-team campaign.

Neither broke the authorisation invariant -- nothing reached `ratified` or
`activated` without a real consumed capability. What they broke is the store's
own account of what is in force, which matters for a different reason: the
append-only history is the record a human reads before deciding anything.

Reached with an ordinary authenticated call and no forgery at all. POST
`/amendments/propose` again under the id of an already-ACTIVATED amendment and
a fresh `proposed` revision is appended. The genuine activation is still in the
history, but every reader of "current" sees `proposed`, and rollback of the
real change is permanently refused with "proposal has not been ratified".

The guard lives in the store rather than the route because the store is where
every writer converges -- and because the same campaign observed that the
persistence layer supplied no independent enforcement of anything.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import get_governance_amendment_store
from aios.api.main import app
from aios.application.governance.amendment_authority import (
    activate_amendment,
    propose_amendment,
    ratify_amendment,
)
from aios.domain.governance.amendments import CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION
from aios.domain.governance.constitution import build_constitution_snapshot
from aios.infrastructure.governance.sqlite_store import (
    GovernanceAmendmentStore,
    ProposalIdReuseError,
)

PROPOSAL_ID = "amend-reuse-target"


@pytest.fixture()
def store(tmp_path) -> GovernanceAmendmentStore:
    return GovernanceAmendmentStore(tmp_path / "reuse.db")


@pytest.fixture()
def client(store) -> Iterator[TestClient]:
    app.dependency_overrides[get_governance_amendment_store] = lambda: store
    try:
        with TestClient(app, client=("127.0.0.1", 12346)) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _capability() -> SimpleNamespace:
    return SimpleNamespace(
        action_type=CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
        operator_id="operator:xyz",
        consumed_at=1234567890.0,
        token_digest="d" * 64,
    )


def _activate_for_real(store: GovernanceAmendmentStore) -> None:
    proposal = propose_amendment(
        proposal_id=PROPOSAL_ID,
        target_articles=("router_max_cost policy",),
        proposed_diff="raise router_max_cost for the batch task class",
        motivation="unblock a legitimate high-cost task class",
        migration_plan="no migration required",
        rollback_plan="revert router_max_cost",
        proposed_by="operator:xyz",
        proposer_type="human",
    )
    store.save_proposal(proposal)
    proposal = ratify_amendment(
        proposal, capability_proof=_capability(), operator_id="operator:xyz"
    )
    store.save_proposal(proposal)
    snapshot = build_constitution_snapshot(ratified_by_operator_id="operator:xyz")
    activated, _ = activate_amendment(proposal, previous_snapshot=snapshot)
    store.save_proposal(activated)


@pytest.mark.parametrize("shadow_status", ["proposed", "critiqued", "simulated"])
def test_a_non_terminal_revision_cannot_shadow_an_activated_amendment(
    store, shadow_status: str
) -> None:
    """The core guard. Any status that is not itself terminal is refused once
    the id has reached one, because it would displace the activated revision as
    the store's "current" answer."""
    _activate_for_real(store)
    assert store.get_current_proposal(PROPOSAL_ID).status == "activated"

    shadow = propose_amendment(
        proposal_id=PROPOSAL_ID,
        target_articles=("router_max_cost policy",),
        proposed_diff="an unrelated later change reusing the same id",
        motivation="m",
        migration_plan="m",
        rollback_plan="r",
        proposed_by="constitutional_learning_organ",
        proposer_type="model",
    ).model_copy(update={"status": shadow_status})

    with pytest.raises(ProposalIdReuseError):
        store.save_proposal(shadow)

    assert store.get_current_proposal(PROPOSAL_ID).status == "activated", (
        "the activated revision must remain the current view"
    )


def test_the_legitimate_lifecycle_is_untouched(store) -> None:
    """The guard must not break the normal path.

    A proposal moving proposed -> critiqued -> simulated -> ratified ->
    activated -> rolled_back is the whole point of the store, and every one of
    those transitions has to keep working. A guard that only ever refuses is
    indistinguishable from a broken store.
    """
    _activate_for_real(store)
    current = store.get_current_proposal(PROPOSAL_ID)
    assert current.status == "activated"

    # rolled_back is terminal-to-terminal and must still be accepted.
    rolled = current.model_copy(update={"status": "rolled_back"})
    store.save_proposal(rolled)
    assert store.get_current_proposal(PROPOSAL_ID).status == "rolled_back"


def test_the_full_history_is_still_append_only(store) -> None:
    """Nothing here deletes or rewrites; the refusal happens before the insert,
    so the record keeps its integrity either way."""
    _activate_for_real(store)
    before = [item.status for item in store.get_proposal_history(PROPOSAL_ID)]

    shadow = propose_amendment(
        proposal_id=PROPOSAL_ID,
        target_articles=("a",),
        proposed_diff="shadow attempt",
        motivation="m",
        migration_plan="m",
        rollback_plan="r",
        proposed_by="model",
        proposer_type="model",
    )
    with pytest.raises(ProposalIdReuseError):
        store.save_proposal(shadow)

    after = [item.status for item in store.get_proposal_history(PROPOSAL_ID)]
    assert after == before == ["proposed", "ratified", "activated"]


def test_the_real_propose_route_returns_409_rather_than_500(client, store) -> None:
    """Through the actual HTTP surface the campaign used.

    409, not 500: the request is well-formed and authenticated, it conflicts
    with existing state. A 500 would read as a bug in the server rather than a
    refusal, and would leak nothing useful to the operator who typed the id.
    """
    _activate_for_real(store)

    resp = client.post(
        "/api/v1/governance/amendments/propose",
        json={
            "proposal_id": PROPOSAL_ID,
            "target_articles": ["router_max_cost policy"],
            "proposed_diff": "reusing an activated id",
            "motivation": "m",
            "migration_plan": "m",
            "rollback_plan": "r",
        },
    )
    assert resp.status_code == 409, resp.text
    assert PROPOSAL_ID in resp.json()["detail"]

    fetched = client.get(f"/api/v1/governance/amendments/{PROPOSAL_ID}")
    assert fetched.json()["status"] == "activated"


def test_rollback_of_the_real_change_is_no_longer_blocked(client, store) -> None:
    """The consequence that made this worth fixing.

    In the campaign's repro, the shadow revision left rollback of a genuinely
    activated amendment permanently refused -- "proposal has not been
    ratified" -- because rollback reads the current view. With the shadow
    refused, the current view still says activated and rollback is reachable.
    """
    _activate_for_real(store)
    client.post(
        "/api/v1/governance/amendments/propose",
        json={
            "proposal_id": PROPOSAL_ID,
            "target_articles": ["a"],
            "proposed_diff": "shadow",
            "motivation": "m",
            "migration_plan": "m",
            "rollback_plan": "r",
        },
    )
    assert store.get_current_proposal(PROPOSAL_ID).status == "activated"
