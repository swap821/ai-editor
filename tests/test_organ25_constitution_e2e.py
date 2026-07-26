"""Organ 25 acceptance: one constitutional authority, end to end.

This is the test the organ's contract actually asks for -- it starts from the
real HTTP amendment ceremony, simulates a process restart, and then exercises
real governed actions:

    activate amendment
    -> restart application
    -> active snapshot remains the amended version
    -> authenticated Principal contains the amended digest
    -> PolicyKernel reads the amended snapshot
    -> capability issued under the OLD digest is rejected
    -> capability issued under the NEW digest succeeds

Every one of those steps failed before this organ, and none of them failed
loudly. `build_constitution_snapshot()` was rebuilt per call from live config
and always returned version 1, so an activated amendment moved the durable
chain and reached nothing. Worse, `CapabilityAuthority.consume()` compared a
rebuilt digest against a binding stamped by the same rebuild, so the two
always agreed: the stale-constitution rejection was structurally unreachable.

Assertions here are deliberately RELATIVE (before vs after) rather than
pinned to version numbers. `AIOS_DATA_DIR` is session-scoped, so the
constitution chain may already have history from earlier tests -- asserting
"version == 2" would make this pass or fail on test ordering rather than on
the behaviour under test.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import get_governance_amendment_store
from aios.api.main import app
from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest
from aios.infrastructure.governance.sqlite_store import GovernanceAmendmentStore


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    # Only the amendment PROPOSAL store is isolated. The constitution chain
    # deliberately uses the real process authority, because the whole point is
    # to prove the ceremony reaches the same authority every other consumer
    # reads -- swapping in a test-only one would prove the opposite.
    store = GovernanceAmendmentStore(tmp_path / "amendments.db")
    app.dependency_overrides[get_governance_amendment_store] = lambda: store
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _restart_application() -> None:
    """Drop every process-wide singleton that caches constitutional state.

    This is the closest in-process stand-in for a restart: nothing survives
    except what is on disk, which is exactly what the durability claim is
    about. If any of these kept serving a cached snapshot, the assertions
    after this call would pass without the database having persisted anything.
    """
    import aios.api.deps as deps
    from aios.application.governance.constitution_authority import (
        reset_constitution_authority,
    )

    reset_constitution_authority()
    deps._identity_service = None
    deps._CAPABILITIES.constitution_authority = None
    # NOTE: deliberately NOT reset_policy_kernel(). aios/api/main.py binds
    # `_RATE_LIMIT_HITS = _POLICY_KERNEL.endpoint_hits` at import time -- a
    # reference to that kernel's internal dict. Rebuilding the kernel gives the
    # live one a NEW dict, so conftest's per-client `_RATE_LIMIT_HITS.clear()`
    # would go on clearing an orphaned dict while the real bucket filled up
    # forever, and unrelated later tests would start seeing 429s.
    # The kernel's durability is proven below by constructing a fresh
    # PolicyKernel directly, which is the same claim without the side effect.


def _active_digest() -> str:
    from aios.application.governance.constitution_authority import (
        get_constitution_authority,
    )

    return get_constitution_authority().get_active_snapshot().snapshot_digest


def _binding(operator_id: str, constitution_digest: str) -> CapabilityBinding:
    return CapabilityBinding(
        operator_id=operator_id,
        device_id="device:e2e",
        authentication_event_id="event:e2e",
        session_id="session:e2e",
        action_type="command",
        route="/api/v1/execute",
        http_method="POST",
        payload_digest=payload_digest({"command": "echo safe"}),
        resource_digest=payload_digest({"workspace": "training_ground"}),
        mission_id=None,
        contract_digest=None,
        policy_version="policy:v1",
        scope="training_ground/",
        verification_requirement="command_exit_zero",
        constitution_digest=constitution_digest,
    )


def _activate_an_amendment(client: TestClient, proposal_id: str) -> str:
    """Drive the REAL HTTP ceremony and return the new constitution digest.

    `ratify` consumes a genuine server-issued exact capability bound to
    CONSTITUTIONAL_AMENDMENT_RATIFY -- conftest's TestClient patch answers the
    428 challenge with the real token, so this is the two-phase YELLOW
    protocol, not a shortcut around it.
    """
    body = {
        "proposal_id": proposal_id,
        "target_articles": ["article-3-provider-routing"],
        "proposed_diff": "prefer local providers under budget pressure",
        "motivation": "reduce cloud spend",
        "migration_plan": "roll out behind a flag",
        "rollback_plan": "flip the flag back",
    }
    assert client.post(
        "/api/v1/governance/amendments/propose", json=body
    ).status_code == 200
    ratified = client.post(
        f"/api/v1/governance/amendments/{proposal_id}/ratify", json={}
    )
    assert ratified.status_code == 200, ratified.text
    activated = client.post(
        f"/api/v1/governance/amendments/{proposal_id}/activate", json={}
    )
    assert activated.status_code == 200, activated.text
    return activated.json()["newConstitutionDigest"]


def test_an_activated_amendment_reaches_every_authority_and_survives_restart(
    client, tmp_path
) -> None:
    from aios.api.deps import get_identity_service

    operator_id = get_identity_service().store.operator()["operator_id"]
    before = _active_digest()

    # A capability minted under the pre-amendment constitution.
    capabilities = CapabilityAuthority(
        db_path=tmp_path / "capabilities.db",
        constitution_authority=None,
    )
    old_binding = _binding(operator_id, before)
    stale_token = capabilities.issue(old_binding)

    # --- the real HTTP ceremony ------------------------------------------
    after = _activate_an_amendment(client, "amend-e2e-1")
    assert after != before, "activation must produce a genuinely new digest"

    # --- restart ----------------------------------------------------------
    _restart_application()

    # 1. the active snapshot is still the amended one, read off disk
    assert _active_digest() == after

    # 2. a freshly authenticated Principal carries the amended digest
    identity = get_identity_service()
    principal = identity._principal_from_session(
        "session:e2e",
        type(
            "S",
            (),
            {
                "created_at": 0,
                "data": {
                    "operator_id": operator_id,
                    "display_name": "Test Human Sovereign",
                    "session_generation": 0,
                },
            },
        )(),
    )
    assert principal.constitution_digest == after

    # 3. a policy kernel built fresh after the restart reads the amended
    #    snapshot off disk -- not a value it cached before the amendment
    from aios.application.governance.constitution_authority import (
        get_constitution_authority,
    )
    from aios.policy.kernel import PolicyKernel

    rebuilt_kernel = PolicyKernel(
        constitution_authority=get_constitution_authority()
    )
    assert rebuilt_kernel.constitution_snapshot().snapshot_digest == after

    # 4. a capability issued under the OLD constitution is refused

    capabilities.constitution_authority = get_constitution_authority()
    with pytest.raises(CapabilityError, match="stale constitution"):
        capabilities.consume(stale_token, old_binding)

    # 5. a capability issued under the NEW constitution succeeds
    fresh_binding = _binding(operator_id, after)
    fresh_token = capabilities.issue(fresh_binding)
    proof = capabilities.consume(fresh_token, fresh_binding)
    assert proof.constitution_digest == after


def test_rollback_restores_the_exact_predecessor_and_survives_restart(
    client,
) -> None:
    before = _active_digest()
    after = _activate_an_amendment(client, "amend-e2e-rollback")
    assert after != before

    reverted = client.post(
        "/api/v1/governance/amendments/amend-e2e-rollback/rollback", json={}
    )
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["revertedConstitutionDigest"] == before

    _restart_application()
    assert _active_digest() == before, "rollback must survive a restart"


def test_the_mirror_reports_the_amended_constitution(client) -> None:
    """Organ 48's surface must not keep showing the pre-amendment version.

    Before organ 25 this panel rebuilt its own snapshot per request, so it
    displayed version 1 forever no matter how many amendments were ratified.
    """
    def _reported_digest(response) -> str | None:
        # Every field is a MetricEnvelope: a missing constitution must render
        # as `unavailable`, never as a silently absent or guessed value.
        envelope = response.json()["constitution"]["snapshot_digest"]
        return envelope.get("value")

    before = client.get("/api/v1/mirror/governance")
    assert before.status_code == 200, before.text
    before_digest = _reported_digest(before)

    after = _activate_an_amendment(client, "amend-e2e-mirror")

    resp = client.get("/api/v1/mirror/governance")
    assert resp.status_code == 200, resp.text
    assert _reported_digest(resp) == after
    assert _reported_digest(resp) != before_digest
