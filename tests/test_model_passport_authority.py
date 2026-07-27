"""Organ 33: one authority over model admission.

`ModelPassportV1` and `LocalWorkerModel` were two disconnected classes with
complementary fields and no converter -- each had exactly what the other
lacked, which is why they could drift. No durable store held a passport at
all: every instance was built in memory and discarded, so nothing survived a
restart and nothing could be audited.

The registry row is now the single source of truth and the passport is a
projection of it. These tests pin the properties that makes that safe.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aios.application.models.passport import (
    can_drive_tools,
    is_admitted_for_role,
)
from aios.application.models.passport_authority import (
    ModelPassportAuthority,
    passport_from_registry_row,
)
from aios.domain.local_workforce.contracts import LocalJobProfile, LocalWorkerModel


def _row(**overrides) -> LocalWorkerModel:
    fields = dict(
        model_id="qwen2.5:3b",
        provider="ollama",
        family="qwen",
        parameter_size="3B",
        quantization="q4",
        installed=True,
        operator_approved=True,
        health="healthy",
        admission_status="approved",
        max_context=8192,
        max_output=2048,
        max_parallelism=1,
        allowed_job_profiles=frozenset({LocalJobProfile.EXTRACT}),
        metadata_confidence="verified",
        model_version="v1",
        artifact_digest="abc123",
        qualification_suite_version="r15-v2",
        qualification_evidence_digest="d" * 64,
        limitations=("cannot summarise",),
        qualified_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        expires_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return LocalWorkerModel(**fields)


class _FakeRegistry:
    def __init__(self, *models: LocalWorkerModel) -> None:
        self._models = {m.model_id: m for m in models}

    def get_model(self, model_id: str) -> LocalWorkerModel | None:
        return self._models.get(model_id)

    def list_models(self) -> list[LocalWorkerModel]:
        return list(self._models.values())


# --------------------------------------------------------------------------- #
# The passport cannot claim more than the registry holds
# --------------------------------------------------------------------------- #


def test_roles_come_from_evidence_backed_profiles_only() -> None:
    passport = passport_from_registry_row(
        _row(allowed_job_profiles=frozenset({LocalJobProfile.EXTRACT}))
    )

    assert passport.qualified_roles == ("extract",)
    assert is_admitted_for_role(passport, "extract") is True
    # A profile the registry never granted is not admitted, whatever the
    # caller asks for.
    assert is_admitted_for_role(passport, "summarise") is False


@pytest.mark.parametrize(
    ("registry_state", "expected"),
    [
        ("pending", "proposed"),
        ("approved", "admitted"),
        ("suspended", "suspended"),
        ("rejected", "revoked"),
    ],
)
def test_admission_is_mapped_never_assumed(registry_state: str, expected: str) -> None:
    passport = passport_from_registry_row(_row(admission_status=registry_state))
    assert passport.admission_status == expected


def test_a_suspended_row_cannot_serve_any_role() -> None:
    """The auto-suspend triggers (digest change, evidence expiry, health drop,
    runtime gone, suite bump) all write `suspended` on the registry row. That
    must reach role admission automatically, or suspension would be cosmetic."""
    passport = passport_from_registry_row(_row(admission_status="suspended"))

    assert is_admitted_for_role(passport, "extract") is False


def test_tool_authority_is_never_granted_by_projection() -> None:
    """`can_drive_tools()` gates real tool authority on tool_protocol_status
    == "verified". Projecting that from a registry row that carries no
    tool-protocol evidence would hand a model tool access on no evidence --
    the exact class of fabrication this organ exists to remove."""
    passport = passport_from_registry_row(_row())

    assert passport.tool_protocol_status == "unknown"
    assert can_drive_tools(passport) is False


def test_limitations_survive_into_the_passport() -> None:
    passport = passport_from_registry_row(_row(limitations=("cannot summarise",)))
    assert "cannot summarise" in passport.known_failure_modes


# --------------------------------------------------------------------------- #
# The digest reflects the admission it describes
# --------------------------------------------------------------------------- #


def test_the_digest_changes_when_admission_changes() -> None:
    admitted = passport_from_registry_row(_row(admission_status="approved"))
    suspended = passport_from_registry_row(_row(admission_status="suspended"))

    assert admitted.passport_digest != suspended.passport_digest


def test_the_digest_changes_when_evidence_changes() -> None:
    before = passport_from_registry_row(_row(qualification_evidence_digest="a" * 64))
    after = passport_from_registry_row(_row(qualification_evidence_digest="b" * 64))

    assert before.passport_digest != after.passport_digest


def test_the_projection_is_deterministic() -> None:
    """Two projections of the same row must agree, or the digest could not be
    compared across restarts."""
    row = _row()
    assert (
        passport_from_registry_row(row).passport_digest
        == passport_from_registry_row(row).passport_digest
    )


# --------------------------------------------------------------------------- #
# The authority reads durable state
# --------------------------------------------------------------------------- #


def test_an_unregistered_model_has_no_passport() -> None:
    """None means "no record", which callers must treat as not-admitted. A
    proposed-but-empty passport would read as merely awaiting qualification."""
    authority = ModelPassportAuthority(_FakeRegistry())

    assert authority.passport_for("never-seen") is None


def test_a_passport_survives_a_restart_because_the_row_does() -> None:
    """The property that did not exist before: nothing durable held a
    passport, so none survived a process restart."""
    row = _row()
    first = ModelPassportAuthority(_FakeRegistry(row)).passport_for("qwen2.5:3b")
    # A brand-new authority over the same durable row stands in for a restart.
    second = ModelPassportAuthority(_FakeRegistry(row)).passport_for("qwen2.5:3b")

    assert first is not None and second is not None
    assert first.passport_digest == second.passport_digest


def test_admitted_passports_excludes_suspended_and_rejected_rows() -> None:
    authority = ModelPassportAuthority(
        _FakeRegistry(
            _row(model_id="ok", admission_status="approved"),
            _row(model_id="stale", admission_status="suspended"),
            _row(model_id="refused", admission_status="rejected"),
            _row(model_id="new", admission_status="pending"),
        )
    )

    admitted = {p.exact_model_id for p in authority.admitted_passports()}

    assert admitted == {"ok"}


def test_an_expired_qualification_still_projects_its_expiry() -> None:
    """Expiry is recorded so a reader can see WHY a suspension is coming, even
    before reconcile() next runs and flips the row."""
    expired = datetime.now(timezone.utc) - timedelta(days=1)
    passport = passport_from_registry_row(_row(expires_at=expired))

    # The row is still 'approved' until reconcile() suspends it; the passport
    # reports what the registry currently holds rather than guessing.
    assert passport.admission_status == "admitted"
    assert passport.qualification_suite_version == "r15-v2"
