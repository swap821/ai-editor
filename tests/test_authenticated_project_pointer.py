"""Durable owner-binding proof for the active project pointer."""

from __future__ import annotations

from aios.infrastructure.identity.sqlite_store import credential_digest
from aios.infrastructure.memory.human_representation_store import ProjectPassportStore


def test_active_project_pointer_is_owner_bound_and_survives_restart(tmp_path) -> None:
    db_path = tmp_path / "passports.db"
    owner_a = credential_digest("operator-a")
    owner_b = credential_digest("operator-b")

    first_process = ProjectPassportStore(db_path)
    first_process.set_active(
        "project-a",
        {"root": "C:/project-a", "purpose": "owner A"},
        operator_identity_digest=owner_a,
    )

    restarted_process = ProjectPassportStore(db_path)
    assert restarted_process.get_active_for_operator(owner_a) == (
        "project-a",
        {"root": "C:/project-a", "purpose": "owner A"},
    )
    assert restarted_process.get_active_for_operator(owner_b) is None
    assert restarted_process.get_active() == (
        "project-a",
        {"root": "C:/project-a", "purpose": "owner A"},
    )