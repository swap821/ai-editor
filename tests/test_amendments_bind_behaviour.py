"""The fourth campaign's findings: amendments that reach production and bind.

The third campaign left organ 46 with a typed, applicable change vocabulary and
a proven authorisation invariant. The fourth campaign found that none of it
reached production:

* No HTTP route could set `changes` -- `ProposeAmendmentRequest` had no such
  field and `extra="forbid"`, so every amendment created through the real API
  still activated as a content no-op. Four separate lenses reported it.
* `constitution_enforcer` never read the snapshot, despite its own docstring
  claiming it "turns the constitution snapshot into enforcement decisions".
  Every check consulted the live config object, so even a correctly activated
  amendment changed nothing that was enforced. The snapshot was a record, not
  a control.
* Migration 0024 made every pre-existing amendment row unreadable with a false
  `RecordTamperedError` -- the tamper alarm firing on the store's own schema
  change, because `_verify` recomputes from `model_dump()` and two new keys had
  appeared in the payload.

The shape of the first two is the same one that recurred all day: the object
was tested, the path was not. In-memory tests proved the domain applied
changes; a live-route test proved the routes worked; neither could see that the
routes could not carry a change to the domain.
"""

from __future__ import annotations

import sqlite3
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
from aios.domain.governance.constitution import (
    ConstitutionChangeV1,
    build_constitution_snapshot,
)
from aios.infrastructure.governance.sqlite_store import (
    GovernanceAmendmentStore,
    _digest,
)
from aios.policy.constitution_enforcer import ConstitutionEnforcer

OPERATOR = "operator:abc"


@pytest.fixture()
def store(tmp_path) -> GovernanceAmendmentStore:
    return GovernanceAmendmentStore(tmp_path / "amendments.db")


@pytest.fixture()
def client(store) -> Iterator[TestClient]:
    app.dependency_overrides[get_governance_amendment_store] = lambda: store
    try:
        with TestClient(app, client=("127.0.0.1", 12346)) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# 1. The change set reaches the domain through the real route.
# --------------------------------------------------------------------------- #


def test_the_propose_route_accepts_a_typed_change_set(client, store) -> None:
    """Without this the whole mechanism is unreachable and every amendment
    activated through the API is still the no-op it was built to fix."""
    resp = client.post(
        "/api/v1/governance/amendments/propose",
        json={
            "proposal_id": "wired-1",
            "target_articles": ["frozen_paths"],
            "proposed_diff": "freeze the api layer as well",
            "motivation": "reduce the surface a worker can modify",
            "migration_plan": "none",
            "rollback_plan": "revert",
            "changes": [
                {"target": "frozen_paths", "operation": "add", "value": "aios/api/"}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["changes"] == [
        {"target": "frozen_paths", "operation": "add", "value": "aios/api/"}
    ]

    # And it survives to the store, not just the response body.
    stored = store.get_current_proposal("wired-1")
    assert stored.changes[0].value == "aios/api/"


def test_the_route_still_refuses_an_unknown_change_shape(client) -> None:
    """`extra="forbid"` and the closed vocabulary must survive being wired to
    the outside. A route that accepts arbitrary change dicts would hand the
    typed guarantee straight back."""
    resp = client.post(
        "/api/v1/governance/amendments/propose",
        json={
            "proposal_id": "wired-bad",
            "target_articles": ["x"],
            "proposed_diff": "d",
            "motivation": "m",
            "migration_plan": "m",
            "rollback_plan": "r",
            "changes": [
                {"target": "foundation_laws", "operation": "remove", "value": "x"}
            ],
        },
    )
    assert resp.status_code == 422, resp.text


# --------------------------------------------------------------------------- #
# 2. An activated amendment binds enforcement.
# --------------------------------------------------------------------------- #


def _activated_snapshot_adding(frozen_prefix: str):
    proposal = ratify_amendment(
        propose_amendment(
            proposal_id="bind-1",
            target_articles=("frozen_paths",),
            proposed_diff="freeze it",
            motivation="m",
            migration_plan="m",
            rollback_plan="r",
            proposed_by=OPERATOR,
            proposer_type="human",
            changes=(
                ConstitutionChangeV1(
                    target="frozen_paths", operation="add", value=frozen_prefix
                ),
            ),
        ),
        capability_proof=SimpleNamespace(
            action_type=CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
            operator_id=OPERATOR,
            consumed_at=1234567890.0,
            token_digest="d" * 64,
        ),
        operator_id=OPERATOR,
    )
    base = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    _, amended = activate_amendment(proposal, previous_snapshot=base)
    return amended


def test_a_ratified_amendment_changes_what_is_actually_enforced() -> None:
    """The deepest of the fourth campaign's findings.

    `constitution_enforcer`'s docstring claimed it turned the snapshot into
    enforcement decisions; it read live config instead. So the constitution
    could be amended, correctly and with a real capability, and nothing about
    the system's behaviour would change.
    """
    amended = _activated_snapshot_adding("aios/api/")

    assert ConstitutionEnforcer().check_file_edit("aios/api/main.py").allowed is True
    decision = ConstitutionEnforcer(snapshot=amended).check_file_edit(
        "aios/api/main.py"
    )
    assert decision.allowed is False
    assert decision.risk == "RED"


def test_the_snapshot_can_only_add_frozen_paths_never_remove_them() -> None:
    """Strengthen-only, as this module's docstring has always promised.

    The union is what enforces it. Even if the amendment vocabulary is later
    widened to express removals, two independent layers would have to fail
    before a frozen path could be dropped from enforcement.
    """
    amended = _activated_snapshot_adding("aios/api/")
    enforcer = ConstitutionEnforcer(snapshot=amended)

    # The spine stays frozen no matter what the snapshot says.
    assert enforcer.check_file_edit("aios/security/gateway.py").allowed is False

    # A snapshot that somehow omitted the spine still cannot unfreeze it,
    # because live config contributes independently.
    hollow = amended.model_copy(update={"frozen_paths": ()})
    assert (
        ConstitutionEnforcer(snapshot=hollow)
        .check_file_edit("aios/security/gateway.py")
        .allowed
        is False
    )


def test_unrelated_paths_are_untouched_by_an_amendment() -> None:
    """A tightening must tighten only what it names."""
    amended = _activated_snapshot_adding("aios/api/")
    assert (
        ConstitutionEnforcer(snapshot=amended).check_file_edit("README.md").allowed
        is True
    )


# --------------------------------------------------------------------------- #
# 3. Adding a field must not brick rows already on disk.
# --------------------------------------------------------------------------- #


def test_rows_written_before_the_new_fields_still_read(store, tmp_path) -> None:
    """Migration 0024 shipped this regression to master.

    `_verify` recomputes the digest from `model_dump()`. Two new keys appeared
    in the payload, the hash moved, and every correct pre-existing row was
    reported as tampered -- the tamper alarm firing on the store's own schema
    change, which is both a false alarm and a real denial of service against
    organ-45-era data.
    """
    proposal = propose_amendment(
        proposal_id="legacy",
        target_articles=("a",),
        proposed_diff="d",
        motivation="m",
        migration_plan="m",
        rollback_plan="r",
        proposed_by="op",
        proposer_type="human",
    )
    store.save_proposal(proposal)

    # Rewrite the row exactly as the pre-0024 code left it: digest taken over a
    # payload with neither new key, and both columns NULL.
    payload = proposal.model_dump(mode="json")
    payload.pop("changes", None)
    payload.pop("ratified_changes_digest", None)
    with sqlite3.connect(store.db_path) as conn:  # noqa: SLF001 - fixture setup
        conn.execute(
            "UPDATE governance_amendment_proposals "
            "SET record_digest=?, changes_json=NULL, ratified_changes_digest=NULL "
            "WHERE proposal_id=?",
            (_digest(payload), "legacy"),
        )

    recovered = store.get_current_proposal("legacy")
    assert recovered.proposal_id == "legacy"
    assert recovered.changes == ()
    assert recovered.ratified_changes_digest is None


def test_tampering_with_a_real_change_set_is_still_detected(store) -> None:
    """The unbricking must not have blunted the alarm.

    Only DEFAULT values are omitted from the digest, so a row that carries a
    real change set hashes with it -- and blanking that column on disk moves
    the recomputed hash away from the stored one.
    """
    from aios.infrastructure.governance.sqlite_store import RecordTamperedError

    proposal = propose_amendment(
        proposal_id="tampered",
        target_articles=("frozen_paths",),
        proposed_diff="d",
        motivation="m",
        migration_plan="m",
        rollback_plan="r",
        proposed_by="op",
        proposer_type="human",
        changes=(
            ConstitutionChangeV1(
                target="frozen_paths", operation="add", value="aios/api/"
            ),
        ),
    )
    store.save_proposal(proposal)

    with sqlite3.connect(store.db_path) as conn:  # noqa: SLF001 - fixture setup
        conn.execute(
            "UPDATE governance_amendment_proposals SET changes_json='[]' "
            "WHERE proposal_id=?",
            ("tampered",),
        )

    with pytest.raises(RecordTamperedError):
        store.get_current_proposal("tampered")
