"""Slice 26: Canonical Constitution and Sovereign Identity."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from aios.application.identity.service import IdentityService
from aios.domain.actions.envelope import ActionEnvelope, ActionType
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.governance.constitution import (
    FOUNDATION_LAWS,
    ConstitutionSnapshotV1,
    build_constitution_snapshot,
)
from aios.domain.missions.mission_contract import MissionContract


def _service(tmp_path: Path) -> IdentityService:
    return IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )


# --- ConstitutionSnapshotV1 -----------------------------------------------


def test_foundation_laws_are_fixed_and_cannot_be_altered() -> None:
    with pytest.raises(ValidationError, match="cannot be changed"):
        ConstitutionSnapshotV1(
            constitution_id="constitution:test",
            version=1,
            foundation_laws=("a made up law",),
            policy_references=(),
            scope_roots=(),
            frozen_paths=(),
            provider_policy_digest="0" * 64,
            autonomy_policy_digest="0" * 64,
            created_at="now",
            ratified_by_operator_id="operator:test",
            snapshot_digest="0" * 64,
        )


def test_snapshot_carries_the_canonical_six_foundation_laws() -> None:
    snapshot = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    assert snapshot.foundation_laws == FOUNDATION_LAWS
    assert len(snapshot.foundation_laws) == 6


def test_ratified_by_operator_id_is_required() -> None:
    with pytest.raises(ValueError, match="ratified_by_operator_id is required"):
        build_constitution_snapshot(ratified_by_operator_id="")


def test_snapshot_digest_is_deterministic_for_the_same_operator_and_policy() -> None:
    first = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    second = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    assert first.snapshot_digest == second.snapshot_digest
    assert first.constitution_id == second.constitution_id
    assert first.version == second.version == 1


def test_snapshot_digest_differs_for_different_operators() -> None:
    first = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    second = build_constitution_snapshot(ratified_by_operator_id="operator:xyz")
    assert first.snapshot_digest != second.snapshot_digest
    assert first.constitution_id != second.constitution_id


def test_amendment_chain_bumps_version_and_pins_previous_digest() -> None:
    v1 = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    v2 = build_constitution_snapshot(
        ratified_by_operator_id="operator:abc", previous_snapshot=v1
    )
    assert v2.version == v1.version + 1
    assert v2.constitution_id == v1.constitution_id
    assert v2.previous_snapshot_digest == v1.snapshot_digest
    assert v2.snapshot_digest != v1.snapshot_digest


def test_repeated_chained_builds_are_deterministic() -> None:
    v1 = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    v2a = build_constitution_snapshot(
        ratified_by_operator_id="operator:abc", previous_snapshot=v1
    )
    v2b = build_constitution_snapshot(
        ratified_by_operator_id="operator:abc", previous_snapshot=v1
    )
    assert v2a.snapshot_digest == v2b.snapshot_digest


# --- Identity: session generation ------------------------------------------


def test_second_login_stamps_a_new_generation_and_stales_the_first_session(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    enrollment = service.enroll_operator(display_name="Kumar")

    first = service.authenticate_credential(enrollment.enrollment_credential)
    assert service.get_authenticated_principal(first.session_cookie) is not None

    second = service.authenticate_credential(enrollment.enrollment_credential)

    assert second.principal.session_generation > first.principal.session_generation
    # Slice 26: the first session is now stale relative to the operator's
    # current generation and must fail closed, not silently keep working.
    assert service.get_authenticated_principal(first.session_cookie) is None
    assert service.get_authenticated_principal(second.session_cookie) is not None


def test_authenticated_principal_carries_a_constitution_digest(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    enrollment = service.enroll_operator(display_name="Kumar")
    authenticated = service.authenticate_credential(enrollment.enrollment_credential)

    assert len(authenticated.principal.constitution_digest) == 64
    expected = build_constitution_snapshot(
        ratified_by_operator_id=enrollment.operator_id
    ).snapshot_digest
    assert authenticated.principal.constitution_digest == expected


def test_anonymous_session_cookie_yields_no_principal(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.enroll_operator(display_name="Kumar")
    assert service.get_authenticated_principal("not-a-real-cookie") is None
    assert service.get_authenticated_principal(None) is None


# --- Threading constitution_digest through authoritative contracts --------


def test_mission_contract_pins_its_constitution_digest_in_its_own_digest() -> None:
    base = dict(
        mission_id="mission:1",
        operator_id="operator:abc",
        goal="do the thing",
        worker_type="deterministic",
        created_by="operator:abc",
    )
    pinned_to_n = MissionContract(**base, constitution_digest="n" * 64)
    pinned_to_n_plus_1 = MissionContract(**base, constitution_digest="p" * 64)

    # A mission created under constitution N cannot silently become a mission
    # under N+1: it is a structurally different, differently-digested object.
    assert pinned_to_n.digest() != pinned_to_n_plus_1.digest()
    assert pinned_to_n.constitution_digest == "n" * 64


def test_capability_binding_carries_constitution_digest() -> None:
    binding = CapabilityBinding(
        operator_id="operator:abc",
        device_id="device:1",
        authentication_event_id="event:1",
        session_id="session:1",
        action_type="command",
        route="/api/v1/execute",
        http_method="post",
        payload_digest="a" * 64,
        resource_digest="b" * 64,
        mission_id="mission:1",
        contract_digest="c" * 64,
        policy_version="v1",
        scope="mission",
        verification_requirement="strong",
        constitution_digest="d" * 64,
    )
    assert binding.constitution_digest == "d" * 64


def test_capability_binding_rejects_blank_constitution_digest_when_provided() -> None:
    with pytest.raises(ValueError, match="constitution_digest"):
        CapabilityBinding(
            operator_id="operator:abc",
            device_id="device:1",
            authentication_event_id="event:1",
            session_id="session:1",
            action_type="command",
            route="/api/v1/execute",
            http_method="post",
            payload_digest="a" * 64,
            resource_digest="b" * 64,
            mission_id="mission:1",
            contract_digest="c" * 64,
            policy_version="v1",
            scope="mission",
            verification_requirement="strong",
            constitution_digest="   ",
        )


def test_action_envelope_carries_constitution_digest() -> None:
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        operator_id="operator:abc",
        device_id="device:1",
        authentication_event_id="event:1",
        constitution_digest="e" * 64,
    )
    assert envelope.constitution_digest == "e" * 64


def test_action_envelope_rejects_blank_constitution_digest_when_provided() -> None:
    with pytest.raises(ValueError, match="constitution_digest"):
        ActionEnvelope(
            route="/api/v1/execute",
            action_type=ActionType.COMMAND,
            constitution_digest="   ",
        )
