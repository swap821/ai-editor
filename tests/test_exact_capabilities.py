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
    authority = CapabilityAuthority(db_path=tmp_path / "digest-match.db")
    current_digest = build_constitution_snapshot(
        ratified_by_operator_id="operator:one"
    ).snapshot_digest
    binding = _binding(constitution_digest=current_digest)

    token = authority.issue(binding)
    proof = authority.consume(token, binding)
    assert proof.constitution_digest == current_digest


def test_constitution_digest_mismatch_is_rejected_outright(tmp_path):
    """Organ 24/25: a capability issued under a stale constitution is
    refused at consume time even though nothing else about it has expired,
    been revoked, or been tampered with."""
    authority = CapabilityAuthority(db_path=tmp_path / "digest-mismatch.db")
    binding = _binding(constitution_digest="sha256:stale-constitution-digest")

    token = authority.issue(binding)
    with pytest.raises(CapabilityError, match="stale constitution"):
        authority.consume(token, binding)


def test_constitution_digest_is_excluded_from_the_replay_equality_check(tmp_path):
    """Every real production caller reconstructs its 'expected' binding fresh
    from the current request's live Principal -- its constitution_digest
    reflects *now*, not issue time. If that raw field were folded into the
    generic binding-equality check, a legitimate constitutional amendment
    during the TTL window would surface as an opaque "binding mismatch"
    and this test's own stale-constitution check would be unreachable."""
    authority = CapabilityAuthority(db_path=tmp_path / "digest-replay.db")
    issued_binding = _binding(constitution_digest="sha256:old-digest")
    token = authority.issue(issued_binding)

    freshly_reconstructed = replace(
        issued_binding, constitution_digest="sha256:new-digest"
    )

    with pytest.raises(CapabilityError, match="stale constitution"):
        authority.consume(token, freshly_reconstructed)


def test_constitution_digest_survives_the_real_store_round_trip(tmp_path):
    """A digest stamped at issue time must not be silently dropped by the
    durable store before consume() ever gets to compare it -- issue and
    consume here go through two separate CapabilityAuthority instances
    (like two separate requests) so nothing but the real SQLite row can
    carry the value across."""
    db_path = tmp_path / "digest-roundtrip.db"
    current_digest = build_constitution_snapshot(
        ratified_by_operator_id="operator:one"
    ).snapshot_digest
    binding = _binding(constitution_digest=current_digest)

    issuing_authority = CapabilityAuthority(db_path=db_path)
    token = issuing_authority.issue(binding)

    consuming_authority = CapabilityAuthority(db_path=db_path)
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
