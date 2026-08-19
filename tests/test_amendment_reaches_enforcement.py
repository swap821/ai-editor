"""The last hop: a ratified amendment must reach the gate a user actually hits.

Every previous test of this mechanism proved a layer in isolation. The domain
applied changes; the store round-tripped them; the routes accepted them; the
enforcer honoured a snapshot it was handed. All true, and the feature still did
nothing, because `aios/api/routes/files.py` built its enforcer once at import
time with no snapshot at all:

    files.py:13   _enforcer = ConstitutionEnforcer()

So activation persisted a new constitution and the gate that decides whether a
file may be edited went on consulting the one from process start.

That is the fifth instance of one mistake in a single day -- the capability was
added, the path was not -- and it is the reason this file exists. It asserts the
whole chain through the real API: propose -> ratify -> activate -> the edit
route refuses a path that was editable a moment earlier. Nothing here inspects
an object it constructed itself.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import get_governance_amendment_store
from aios.api.main import app
from aios.infrastructure.governance.sqlite_store import GovernanceAmendmentStore

PROPOSAL_ID = "reach-enforcement"
#: Inside a scope root so the edit route reaches the constitution gate rather
#: than being turned away earlier by the scope check.
TARGET_PREFIX = "training_ground/frozen_by_amendment/"
TARGET_FILE = "training_ground/frozen_by_amendment/note.txt"


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    store = GovernanceAmendmentStore(tmp_path / "amendments.db")
    app.dependency_overrides[get_governance_amendment_store] = lambda: store
    try:
        with TestClient(app, client=("127.0.0.1", 12346)) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _edit(client: TestClient, path: str):
    return client.post("/api/v1/files/edit", json={"path": path, "content": "hello"})


def test_the_edit_route_builds_its_enforcer_per_request() -> None:
    """The structural half of the fix, asserted directly.

    A module-level enforcer cannot see an amendment ratified after boot, so
    even a correct snapshot lookup would be stale. If this ever regresses to a
    singleton the end-to-end test below could still pass on a freshly imported
    process and hide it.
    """
    import aios.api.routes.files as files_route

    assert not hasattr(files_route, "_enforcer"), (
        "the edit route has gone back to an import-time enforcer; an amendment "
        "activated after start-up would never reach it"
    )
    assert hasattr(files_route, "_enforcer_for")


def test_privileged_fields_cannot_be_smuggled_in_at_propose_time(client) -> None:
    """Run through the real route with a real session.

    An earlier hand-run of this attack reported every field as "accepted"
    because the bare script had no privileged session and every response was a
    403. The finding was in the harness, not the code -- which is why this one
    lives in the suite that gets a real session.
    """
    body = {
        "proposal_id": "smuggle",
        "target_articles": ["frozen_paths"],
        "proposed_diff": "d",
        "motivation": "m",
        "migration_plan": "m",
        "rollback_plan": "r",
    }
    for field, value in [
        ("status", "ratified"),
        ("ratified_by_operator_id", "operator:abc"),
        ("ratification_capability_digest", "d" * 64),
        ("ratified_changes_digest", "a" * 64),
        ("approval_model", "timeout_auto_ratification"),
        ("activated_snapshot_digest", "b" * 64),
    ]:
        resp = client.post(
            "/api/v1/governance/amendments/propose", json={**body, field: value}
        )
        assert resp.status_code == 422, (
            f"{field!r} was accepted at propose time: HTTP {resp.status_code}"
        )


def test_an_activated_amendment_changes_what_the_edit_route_refuses(client) -> None:
    """The whole chain, through the API, with nothing constructed by hand.

    This is the assertion that was impossible for the entire life of this
    organ: an operator ratifies a constitutional amendment and the system's
    behaviour changes as a result.
    """
    before = _edit(client, TARGET_FILE)
    assert before.status_code != 403, (
        "the target must be editable before the amendment, or this test proves "
        f"nothing; got HTTP {before.status_code}: {before.text[:200]}"
    )

    propose = client.post(
        "/api/v1/governance/amendments/propose",
        json={
            "proposal_id": PROPOSAL_ID,
            "target_articles": ["frozen_paths"],
            "proposed_diff": f"freeze {TARGET_PREFIX}",
            "motivation": "reduce the surface a worker can modify",
            "migration_plan": "none",
            "rollback_plan": "revert",
            "changes": [
                {
                    "target": "frozen_paths",
                    "operation": "add",
                    "value": TARGET_PREFIX,
                }
            ],
        },
    )
    assert propose.status_code == 200, propose.text

    ratify = client.post(f"/api/v1/governance/amendments/{PROPOSAL_ID}/ratify", json={})
    assert ratify.status_code == 200, ratify.text

    activate = client.post(
        f"/api/v1/governance/amendments/{PROPOSAL_ID}/activate", json={}
    )
    assert activate.status_code == 200, activate.text

    after = _edit(client, TARGET_FILE)
    assert after.status_code == 403, (
        "the amendment was ratified and activated, and the edit gate did not "
        f"change: HTTP {after.status_code}: {after.text[:200]}"
    )


def test_an_activated_amendment_reaches_the_worker_spawner(client, tmp_path) -> None:
    """The same last hop, for the OTHER gate that builds its own enforcer.

    `WorkerSpawner` was the sixth instance of this one mistake: it constructed
    `ConstitutionEnforcer()` bare, so `amended_frozen_paths` was always empty
    and a ratified amendment reached the spawner's docstring but not its
    decisions. It now resolves the active snapshot -- but that fix was only ever
    proved by HANDING the spawner a snapshot, which tests the capability rather
    than the path, exactly the distinction this file exists to draw.

    So this constructs the spawner the way production does -- no snapshot
    argument -- after ratifying a real amendment through the real routes, and
    asks its own enforcer. Nothing here is handed the answer.
    """
    from aios.runtime.spawner import WorkerSpawner

    # A prefix of its own: the edit-route test above freezes TARGET_PREFIX
    # through a real amendment, and the constitution chain persists across
    # tests in this process -- so sharing it would make the baseline depend
    # on test order (and, ironically, pass for the right reason by accident).
    spawner_prefix = "training_ground/frozen_for_spawner/"
    probe = f"{spawner_prefix}worker_target.txt"

    baseline = WorkerSpawner(runtime_root=tmp_path / "rt-before")
    assert baseline.constitution_enforcer.check_file_edit(probe).allowed is True, (
        "the probe path must be editable BEFORE the amendment, or this proves nothing"
    )

    propose = client.post(
        "/api/v1/governance/amendments/propose",
        json={
            "proposal_id": "reach-spawner",
            "target_articles": ["frozen_paths"],
            "proposed_diff": f"freeze {spawner_prefix}",
            "motivation": "a worker must not edit what an amendment froze",
            "migration_plan": "none",
            "rollback_plan": "revert",
            "changes": [
                {
                    "target": "frozen_paths",
                    "operation": "add",
                    "value": spawner_prefix,
                }
            ],
        },
    )
    assert propose.status_code == 200, propose.text
    ratify = client.post("/api/v1/governance/amendments/reach-spawner/ratify", json={})
    assert ratify.status_code == 200, ratify.text
    activate = client.post(
        "/api/v1/governance/amendments/reach-spawner/activate", json={}
    )
    assert activate.status_code == 200, activate.text

    # Built AFTER activation, the way a real spawn does, with no snapshot passed.
    spawner = WorkerSpawner(runtime_root=tmp_path / "rt-after")
    decision = spawner.constitution_enforcer.check_file_edit(probe)

    assert decision.allowed is False, (
        "a ratified, activated amendment did not reach the worker spawner's "
        "enforcer -- the capability is wired but the path is not"
    )
    assert decision.risk == "RED"

    # And prove the refusal came from the WIRING rather than from global config
    # or a scope rule that would have refused this path anyway. A bare enforcer
    # -- exactly what the spawner used to build -- still permits it, so the only
    # difference is the snapshot the spawner now resolves.
    from aios.policy.constitution_enforcer import ConstitutionEnforcer

    assert ConstitutionEnforcer().check_file_edit(probe).allowed is True, (
        "a bare enforcer already refuses this path, so the assertion above "
        "would pass even with the spawner's snapshot wiring removed -- pick a "
        "probe path that is genuinely only frozen by the amendment"
    )
