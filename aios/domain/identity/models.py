"""Identity and principal value objects for the sovereign control plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class PrincipalType(StrEnum):
    OPERATOR = "operator"
    SYSTEM = "system"
    MODEL = "model"
    QUEEN = "queen"
    WORKER = "worker"
    SCHEDULER = "scheduler"
    RECOVERY = "recovery"


#: Known values for `AuthenticationEvent.strength` / `Principal.credential_strength`.
#: Not an enum (the fields remain free-text for forward compatibility with the
#: infrastructure layer's existing storage), but this is the canonical set
#: `IdentityService` produces today.
CREDENTIAL_STRENGTHS: tuple[str, ...] = ("operator", "strong")


@dataclass(frozen=True)
class Principal:
    """Authenticated identity attached to a request or action."""

    principal_id: str
    principal_type: PrincipalType
    display_name: str
    session_id: str
    authentication_level: str
    authenticated_at: datetime
    device_id: str = ""
    authentication_event_id: str = ""
    request_id: str = ""
    client_address: str = ""
    parent_principal_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    #: Slice 26: monotonic generation stamped at session-issue time. A
    #: principal whose generation no longer matches the operator's current
    #: stored generation is stale and must fail closed (see
    #: `IdentityService.get_authenticated_principal`).
    session_generation: int = 0
    #: Slice 26: digest of the `ConstitutionSnapshotV1` active when this
    #: principal's session was issued. Empty string means "not yet stamped"
    #: (pre-Slice-26 sessions, or callers that construct a Principal outside
    #: `IdentityService`) rather than a false claim of constitutional binding.
    constitution_digest: str = ""


@dataclass(frozen=True)
class DevicePrincipal:
    """Durable local device identity associated with the operator."""

    device_id: str
    operator_id: str
    enrolled_at: datetime
    last_authenticated_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class AuthenticationEvent:
    """Durable proof that a device authenticated for a bounded purpose."""

    authentication_event_id: str
    operator_id: str
    device_id: str
    strength: str
    purpose: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None


@dataclass(frozen=True)
class AuthenticatedRequestContext:
    """Immutable authority context passed from HTTP resolution to application code."""

    operator_id: str
    device_id: str
    session_id: str
    authentication_event_id: str
    authentication_strength: str
    client_address: str
    request_id: str
    #: Slice 26 additions -- see `Principal.session_generation`/`.constitution_digest`.
    session_generation: int = 0
    constitution_digest: str = ""
    issued_at: datetime | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class EnrollmentResult:
    """One-time bootstrap material returned only to the enrolling operator."""

    operator_id: str
    enrollment_credential: str
    recovery_code: str


@dataclass(frozen=True)
class AuthenticationResult:
    """Internal authentication result; the raw cookie is never part of it."""

    principal: Principal
    session_cookie: str
    authentication_event_id: str
