"""Admission-check helpers over `ModelPassportV1` (Slice 31).

These are pure, deterministic checks over an already-built passport -- they
never run a qualification suite themselves (that is a real, separate probe
against a real model, and remains Slice 32's job for the local clerk).
"""

from __future__ import annotations

from aios.domain.models.contracts import ModelPassportV1


def is_admitted_for_role(passport: ModelPassportV1, role: str) -> bool:
    """A model may serve a role only if it is admitted, the role was
    actually qualified, and the role isn't explicitly disallowed."""
    if passport.admission_status != "admitted":
        return False
    if role in passport.disallowed_roles:
        return False
    return role in passport.qualified_roles


def can_drive_tools(passport: ModelPassportV1) -> bool:
    """A model with failed or unverified tool-protocol qualification must
    never be trusted to drive tool calls."""
    return passport.tool_protocol_status == "verified"


def is_stale_for_version(
    passport: ModelPassportV1, *, current_model_version: str | None
) -> bool:
    """A qualification recorded against one model version does not carry
    over silently when the provider ships a new version under the same
    model id. `None` on either side is conservatively treated as stale --
    an unversioned qualification proves nothing about a versioned model and
    vice versa."""
    if passport.model_version is None or current_model_version is None:
        return True
    return passport.model_version != current_model_version


__all__ = ["can_drive_tools", "is_admitted_for_role", "is_stale_for_version"]
