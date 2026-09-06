"""Red acceptance tests for the R3 exact-capability authority."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.application.capabilities.verifier import CapabilityVerifier
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest
from aios.domain.governance.constitution import build_constitution_snapshot


def _constitution_authority(tmp_path, operator_id: str = "operator:one"):
    """A real ConstitutionAuthority over a real durable chain.

    These tests previously compared fabricated literal digests
    ("sha256:old-digest") that no snapshot ever produced, against a "current"
    digest rebuilt from live config. That could never reproduce the real
    failure mode, because in production BOTH sides were rebuilt the same way
    and therefore always matched -- the rejection under test was structurally
    unreachable. Driving a genuine v1 -> v2 activation is what makes these
    assertions mean something.
    """
    from aios.application.governance.constitution_authority import (
        ConstitutionAuthority,
    )
    from aios.infrastructure.governance.constitution_snapshot_store import (
        ConstitutionSnapshotStore,
    )

    class _Enrolled:
        def operator(self):
            return {"operator_id": operator_id}

    return ConstitutionAuthority(
        ConstitutionSnapshotStore(tmp_path / "constitution.db"),
        identity_store=_Enrolled(),
    )


def _binding(**overrides) -> CapabilityBinding:
    values = {
        "operator_id": "operator:one",
        "device_id": "device:one",
        "authentication_event_id": "event:strong",
        "session_id": "session:one",
        "action_type": "command",
        "route": "/api/v1/execute",
        "http_method": "POST",
        "payload_digest": payload_digest({"command": "echo safe"}),
        "resource_digest": payload_digest({"workspace": "training_ground"}),
        "mission_id": None,
        "contract_digest": None,
        "policy_version": "policy:v1",
        "scope": "training_ground/",
        "verification_requirement": "command_exit_zero",
    }
    values.update(overrides)
    return CapabilityBinding(**values)


def test_capability_is_opaque_exact_and_single_use(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "capabilities.db")
    binding = _binding()

    token = authority.issue(binding)
    assert token
    consumed = authority.consume(token, binding)
    assert consumed.capability_id
    with pytest.raises(CapabilityError):
        authority.consume(token, binding)
    assert token.encode() not in (tmp_path / "capabilities.db").read_bytes()


def test_list_pending_excludes_consumed_revoked_and_expired(tmp_path):
    """Organ 47/49: a real, non-consuming enumeration for the read-only
    approval-decision surface."""
    now = [1000.0]
    authority = CapabilityAuthority(
        db_path=tmp_path / "capabilities.db", ttl_seconds=50, clock=lambda: now[0]
    )
    still_pending = _binding(action_type="command", route="/api/v1/execute")
    to_consume = _binding(
        action_type="edit",
        route="/api/edit",
        payload_digest=payload_digest({"filepath": "a.py"}),
        resource_digest=payload_digest({"workspace": "training_ground/a.py"}),
    )
    to_revoke = _binding(
        action_type="create",
        route="/api/create",
        payload_digest=payload_digest({"filepath": "b.py"}),
        resource_digest=payload_digest({"workspace": "training_ground/b.py"}),
    )
    to_expire = _binding(
        action_type="rollback",
        route="/api/v1/rollback",
        payload_digest=payload_digest({"snapshot_id": "abc"}),
        resource_digest=payload_digest({"snapshot_id": "abc"}),
    )

    authority.issue(still_pending)
    consume_token = authority.issue(to_consume)
    revoke_token = authority.issue(to_revoke)
    authority.issue(to_expire)

    authority.consume(consume_token, to_consume)
    revoked = authority.inspect(revoke_token)
    authority.revoke(revoked.capability_id)

    pending_now = authority.list_pending()
    assert {c.binding.action_type for c in pending_now} == {"command", "rollback"}

    now[0] = 1051.0  # past to_expire's 50s ttl too
    assert authority.list_pending() == []


def test_list_pending_never_exposes_a_usable_bearer_token(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "capabilities.db")
    token = authority.issue(_binding())

    pending = authority.list_pending()

    assert len(pending) == 1
    assert token not in repr(pending[0])
    assert token.encode() not in (tmp_path / "capabilities.db").read_bytes()


@pytest.mark.parametrize(
    "field",
    [
        "payload_digest",
        "resource_digest",
        "route",
        "http_method",
        "mission_id",
        "contract_digest",
        "policy_version",
        "scope",
        "verification_requirement",
    ],
)
def test_same_token_rejects_every_changed_binding_field(tmp_path, field):
    authority = CapabilityAuthority(db_path=tmp_path / f"{field}.db")
    binding = _binding(mission_id="mission:one", contract_digest="contract:one")
    token = authority.issue(binding)
    changed = replace(binding, **{field: "changed-value"})

    with pytest.raises(CapabilityError):
        authority.consume(token, changed)


def test_same_token_cannot_cross_operator_or_session(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "identity.db")
    binding = _binding()
    token = authority.issue(binding)

    with pytest.raises(CapabilityError):
        authority.consume(token, replace(binding, operator_id="operator:two"))
    with pytest.raises(CapabilityError):
        authority.consume(token, replace(binding, session_id="session:two"))


def test_expired_and_revoked_capabilities_fail_closed(tmp_path):
    now = {"value": 100.0}
    authority = CapabilityAuthority(
        db_path=tmp_path / "lifecycle.db", clock=lambda: now["value"], ttl_seconds=10
    )
    expired = authority.issue(_binding())
    now["value"] = 111.0
    with pytest.raises(CapabilityError):
        authority.consume(expired, _binding())

    now["value"] = 200.0
    binding = _binding(route="/api/v1/rollback")
    token = authority.issue(binding)
    capability = authority.inspect(token)
    authority.revoke(capability.capability_id)
    with pytest.raises(CapabilityError):
        authority.consume(token, binding)


def test_policy_version_and_wildcard_scope_fail_closed(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "policy.db")
    binding = _binding()
    token = authority.issue(binding)
    with pytest.raises(CapabilityError):
        authority.consume(token, replace(binding, policy_version="policy:v0"))
    with pytest.raises(CapabilityError):
        authority.issue(replace(binding, scope="*"))


def test_two_consumers_race_for_one_capability(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "race.db")
    binding = _binding()
    token = authority.issue(binding)

    def consume():
        try:
            authority.consume(token, binding)
            return "consumed"
        except CapabilityError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(results) == ["consumed", "rejected"]


def test_verifier_is_non_consuming_until_explicit_consume(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "verifier.db")
    verifier = CapabilityVerifier(authority)
    binding = _binding()
    token = authority.issue(binding)

    inspected = verifier.verify(token, binding)
    assert inspected.consumed_at is None
    verifier.consume(token, binding)
    with pytest.raises(CapabilityError):
        verifier.verify(token, binding)


def test_resource_metadata_entropy_does_not_block_exact_capability(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "resource-path.db")
    payload = {
        "path": (
            "/home/runner/work/ai-editor/ai-editor/.aios/tmp/"
            "pytest-session-09c93a69/pytest-of-runner/pytest-0/editable.txt"
        ),
        "content": "safe replacement",
    }
    binding = _binding(
        route="/api/v1/files/edit",
        action_type="edit",
        payload_digest=payload_digest(payload),
    )

    token = authority.issue(binding, action_payload=payload)
    assert authority.inspect(token).action_payload == payload
    proof = authority.consume(token, binding)
    assert proof.consumed_at is not None
    assert proof.payload_digest == payload_digest(payload)


def test_constitution_digest_none_is_unaffected(tmp_path):
    """Organ 24/25: bindings that never opted into digest-tracking keep working."""
    authority = CapabilityAuthority(db_path=tmp_path / "digest-none.db")
    binding = _binding()
    assert binding.constitution_digest is None

    token = authority.issue(binding)
    proof = authority.consume(token, binding)
    assert proof.constitution_digest is None


def test_constitution_digest_match_is_accepted(tmp_path):
    constitution = _constitution_authority(tmp_path)
    authority = CapabilityAuthority(
        db_path=tmp_path / "digest-match.db", constitution_authority=constitution
    )
    current_digest = constitution.get_active_snapshot().snapshot_digest
    binding = _binding(constitution_digest=current_digest)

    token = authority.issue(binding)
    proof = authority.consume(token, binding)
    assert proof.constitution_digest == current_digest


def test_a_real_activated_amendment_invalidates_an_outstanding_capability(tmp_path):
    """Organ 25, the regression that matters.

    A capability is issued under v1, a real amendment is activated, and the
    capability is then consumed within its TTL. Before this organ, the
    "current" digest was rebuilt from live config on both sides, so the two
    always matched and this rejection could never fire -- an activated
    amendment had no effect on any outstanding capability.
    """
    constitution = _constitution_authority(tmp_path)
    authority = CapabilityAuthority(
        db_path=tmp_path / "digest-amended.db", constitution_authority=constitution
    )
    v1 = constitution.get_active_snapshot()
    binding = _binding(constitution_digest=v1.snapshot_digest)
    token = authority.issue(binding)

    v2 = build_constitution_snapshot(
        ratified_by_operator_id="operator:one", previous_snapshot=v1
    )
    constitution.activate_snapshot(v2, expected_previous_digest=v1.snapshot_digest)

    with pytest.raises(CapabilityError, match="stale constitution"):
        authority.consume(token, binding)


def test_constitution_digest_mismatch_is_rejected_outright(tmp_path):
    """Organ 24/25: a capability issued under a stale constitution is
    refused at consume time even though nothing else about it has expired,
    been revoked, or been tampered with."""
    constitution = _constitution_authority(tmp_path)
    authority = CapabilityAuthority(
        db_path=tmp_path / "digest-mismatch.db", constitution_authority=constitution
    )
    binding = _binding(constitution_digest="f" * 64)

    token = authority.issue(binding)
    with pytest.raises(CapabilityError, match="stale constitution"):
        authority.consume(token, binding)


def test_a_constitution_bound_capability_needs_a_wired_authority(tmp_path):
    """Fail closed: without an authority there is nothing to verify against,
    so the capability must be refused rather than waved through."""
    authority = CapabilityAuthority(db_path=tmp_path / "digest-unwired.db")
    binding = _binding(constitution_digest="f" * 64)

    token = authority.issue(binding)
    with pytest.raises(CapabilityError, match="no constitution authority"):
        authority.consume(token, binding)


def test_constitution_digest_is_excluded_from_the_replay_equality_check(tmp_path):
    """Every real production caller reconstructs its 'expected' binding fresh
    from the current request's live Principal -- its constitution_digest
    reflects *now*, not issue time. If that raw field were folded into the
    generic binding-equality check, a legitimate constitutional amendment
    during the TTL window would surface as an opaque "binding mismatch"
    and this test's own stale-constitution check would be unreachable."""
    constitution = _constitution_authority(tmp_path)
    authority = CapabilityAuthority(
        db_path=tmp_path / "digest-replay.db", constitution_authority=constitution
    )
    issued_binding = _binding(constitution_digest="a" * 64)
    token = authority.issue(issued_binding)

    freshly_reconstructed = replace(issued_binding, constitution_digest="b" * 64)

    with pytest.raises(CapabilityError, match="stale constitution"):
        authority.consume(token, freshly_reconstructed)


def test_constitution_digest_survives_the_real_store_round_trip(tmp_path):
    """A digest stamped at issue time must not be silently dropped by the
    durable store before consume() ever gets to compare it -- issue and
    consume here go through two separate CapabilityAuthority instances
    (like two separate requests) so nothing but the real SQLite row can
    carry the value across."""
    db_path = tmp_path / "digest-roundtrip.db"
    constitution = _constitution_authority(tmp_path)
    current_digest = constitution.get_active_snapshot().snapshot_digest
    binding = _binding(constitution_digest=current_digest)

    issuing_authority = CapabilityAuthority(
        db_path=db_path, constitution_authority=constitution
    )
    token = issuing_authority.issue(binding)

    consuming_authority = CapabilityAuthority(
        db_path=db_path, constitution_authority=constitution
    )
    proof = consuming_authority.consume(token, binding)
    assert proof.constitution_digest == current_digest


def test_resource_metadata_named_secret_is_still_rejected(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "resource-secret.db")
    payload = {"path": "/tmp/api_key=sk-12345678901234567890123456789012"}
    binding = _binding(
        route="/api/v1/files/edit",
        action_type="edit",
        payload_digest=payload_digest(payload),
    )

    with pytest.raises(CapabilityError, match="credential-like"):
        authority.issue(binding, action_payload=payload)


# --------------------------------------------------------------------------- #
# INVARIANT III -- approval must follow a fresh human act
# --------------------------------------------------------------------------- #
#
# Measured 2026-09-06: `action_guard` returns the approval token to the
# principal that just requested the action, so one principal could request AND
# approve with no human anywhere. The damning part was never that the action
# ran -- it is that the resulting audit row was indistinguishable from one
# where an operator genuinely consented. Both wrote "approved".
#
# The rule that LOOKED like strictness was what forced this: the binding pinned
# the exact authentication_event_id, so a human who re-authenticated had their
# approval rejected as a mismatch. The only way to approve was to still hold the
# event that made the request. These tests pin the inversion.

#: Authentication events, oldest first. `created_at` is what the fix compares.
_AUTH_EVENTS = {
    "event:older": {"created_at": 500.0},
    "event:strong": {"created_at": 1000.0},
    "event:reauthenticated": {"created_at": 2000.0},
}

_FETCH = {"command": "pip install evil-package"}
_ORDINARY = {"command": "mkdir training_ground/build"}


def _fresh_auth_authority(tmp_path, **kwargs) -> CapabilityAuthority:
    return CapabilityAuthority(
        db_path=tmp_path / "capabilities.db",
        authentication_event_lookup=_AUTH_EVENTS.get,
        **kwargs,
    )


def _fetch_binding(**overrides) -> CapabilityBinding:
    return _binding(payload_digest=payload_digest(_FETCH), **overrides)


def test_the_requester_cannot_approve_its_own_supply_chain_fetch(tmp_path):
    """The exact replay organ 55's M7 measures, refused.

    An agent handed the token in the REQUIRE_APPROVAL body still holds the
    authentication event that made the request, so it cannot satisfy this. No
    payload, no timing trick: it simply has nothing newer to present.
    """
    authority = _fresh_auth_authority(tmp_path)
    token = authority.issue(_fetch_binding(), action_payload=_FETCH)

    with pytest.raises(CapabilityError) as refusal:
        authority.consume(token, _fetch_binding())

    assert "NEW privileged authentication event" in str(refusal.value)


def test_a_human_who_reauthenticates_can_approve_the_fetch(tmp_path):
    """The control must not be a denial of service against the operator.

    Before the fix a re-authentication INVALIDATED the approval (binding
    mismatch on authentication_event_id). This asserts the inversion actually
    landed -- that the newer event is now the thing that works.
    """
    authority = _fresh_auth_authority(tmp_path)
    token = authority.issue(_fetch_binding(), action_payload=_FETCH)

    proof = authority.consume(
        token, _fetch_binding(authentication_event_id="event:reauthenticated")
    )

    assert proof.capability_id


def test_an_older_authentication_event_does_not_count_as_fresh(tmp_path):
    """ "Newer", not merely "different" -- the difference is the whole control.

    A difference test would be satisfied by ANY other event: an older one, or
    one lifted from an unrelated session. Only a strictly newer event proves a
    human authenticated AFTER this action was requested.
    """
    authority = _fresh_auth_authority(tmp_path)
    token = authority.issue(_fetch_binding(), action_payload=_FETCH)

    with pytest.raises(CapabilityError) as refusal:
        authority.consume(token, _fetch_binding(authentication_event_id="event:older"))

    assert "not newer" in str(refusal.value)


def test_ordinary_yellow_work_still_approves_in_one_click(tmp_path):
    """The operator's explicit scope decision, pinned.

    YELLOW covers `mkdir`, `touch` and `pytest`. Requiring a re-authentication
    per `mkdir` would be unusable, and an unusable control gets switched off.
    So the fresh-auth requirement is scoped to actions that fetch and execute
    REMOTE CODE. This is a deliberate residual, not an oversight: an agent
    inside a privileged window can still self-approve ordinary YELLOW work.
    """
    authority = _fresh_auth_authority(tmp_path)
    binding = _binding(payload_digest=payload_digest(_ORDINARY))
    token = authority.issue(binding, action_payload=_ORDINARY)

    proof = authority.consume(token, binding)

    assert proof.capability_id


def test_freshness_that_cannot_be_verified_is_refused(tmp_path):
    """Fail closed. Unable to compare is not permission to proceed.

    This is exactly where a mis-wired singleton would otherwise restore the
    behaviour being fixed -- silently, and only for the high-risk class.
    """
    authority = CapabilityAuthority(db_path=tmp_path / "capabilities.db")
    token = authority.issue(_fetch_binding(), action_payload=_FETCH)

    with pytest.raises(CapabilityError) as refusal:
        authority.consume(
            token, _fetch_binding(authentication_event_id="event:reauthenticated")
        )

    assert "cannot be verified" in str(refusal.value)


def test_an_unknown_authentication_event_is_refused(tmp_path):
    """A forged event id must not pass by being unresolvable."""
    authority = _fresh_auth_authority(tmp_path)
    token = authority.issue(_fetch_binding(), action_payload=_FETCH)

    with pytest.raises(CapabilityError) as refusal:
        authority.consume(token, _fetch_binding(authentication_event_id="event:forged"))

    assert "unknown" in str(refusal.value)


def test_the_fetch_binding_is_still_exact_apart_from_the_auth_event(tmp_path):
    """Relaxing one field must not relax the rest.

    `authentication_event_id` is excluded from the equality check for high-risk
    actions so a re-authentication can approve. Every other field must still
    pin exactly -- otherwise the fix for Invariant III would have opened a
    capability-substitution hole.
    """
    authority = _fresh_auth_authority(tmp_path)
    token = authority.issue(_fetch_binding(), action_payload=_FETCH)

    with pytest.raises(CapabilityError) as refusal:
        authority.consume(
            token,
            _fetch_binding(
                authentication_event_id="event:reauthenticated",
                route="/api/v1/something-else",
            ),
        )

    assert "binding mismatch" in str(refusal.value)
