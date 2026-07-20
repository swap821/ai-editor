"""Red acceptance tests for the R3 exact-capability authority."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.application.capabilities.verifier import CapabilityVerifier
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest


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
