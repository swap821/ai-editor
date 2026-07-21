"""Single-operator enrollment and server-side authentication service."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aios.core.session_manager import SessionManager
from aios.domain.identity.models import (
    AuthenticationResult,
    EnrollmentResult,
    Principal,
    PrincipalType,
)
from aios.infrastructure.identity.sqlite_store import IdentityStore, credential_digest


class IdentityError(RuntimeError):
    """Base error for identity lifecycle failures."""


class AlreadyEnrolled(IdentityError):
    """Raised when bootstrap enrollment would create a second operator."""


class InvalidCredential(IdentityError):
    """Raised for invalid enrollment/re-authentication material."""


class IdentityService:
    """Authoritative single-operator identity service."""

    def __init__(
        self,
        *,
        identity_db_path: str | Path,
        session_db_path: str | Path,
    ) -> None:
        self.store = IdentityStore(identity_db_path)
        self.sessions = SessionManager(store_path=session_db_path)

    def is_enrolled(self) -> bool:
        return self.store.operator() is not None

    def enroll_operator(self, *, display_name: str) -> EnrollmentResult:
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("display_name is required")
        if self.is_enrolled():
            raise AlreadyEnrolled("the single Human Sovereign is already enrolled")
        operator_id = f"operator:{uuid.uuid4().hex}"
        credential = secrets.token_urlsafe(32)
        recovery_code = secrets.token_urlsafe(24)
        try:
            self.store.create_operator(
                operator_id=operator_id,
                display_name=display_name,
                credential_digest_value=credential_digest(credential),
                recovery_digest_value=credential_digest(recovery_code),
            )
        except sqlite3.IntegrityError as exc:
            # The singleton constraint is the authority under concurrent
            # first-run requests; surface it as the same domain error as the
            # preflight check rather than leaking SQLite details.
            raise AlreadyEnrolled(
                "the single Human Sovereign is already enrolled"
            ) from exc
        self.store.create_device(
            device_id=f"device:{uuid.uuid4().hex}",
            operator_id=operator_id,
        )
        return EnrollmentResult(operator_id, credential, recovery_code)

    def authenticate_credential(self, credential: str) -> AuthenticationResult:
        operator = self._operator_for_credential(credential)
        return self._open_authenticated_session(operator, event_type="login")

    def reauthenticate(
        self, session_cookie: str, credential: str
    ) -> AuthenticationResult:
        current = self.get_authenticated_principal(session_cookie)
        if current is None:
            raise InvalidCredential("a valid authenticated session is required")
        operator = self._operator_for_credential(credential)
        if operator["operator_id"] != current.principal_id:
            raise InvalidCredential(
                "credential does not match the authenticated operator"
            )
        device = self.store.device_for_operator(str(operator["operator_id"]))
        if device is None or device["device_id"] != current.device_id:
            raise InvalidCredential("operator device is unavailable or revoked")
        event_id = uuid.uuid4().hex
        raw_session = self.sessions.upgrade_session(session_cookie)
        new_cookie = hashlib.sha256(raw_session.encode("utf-8")).hexdigest()
        session = self.sessions.validate_session(new_cookie)
        if session is None:  # pragma: no cover - upgrade_session creates it
            raise IdentityError("session rotation failed closed")
        session.data.update(
            operator_id=operator["operator_id"],
            display_name=operator["display_name"],
            authentication_level="privileged",
            authentication_event_id=event_id,
            device_id=device["device_id"],
        )
        self.sessions.persist_session(session)
        self.store.record_authentication_event(
            event_id=event_id,
            operator_id=operator["operator_id"],
            event_type="reauthentication",
            session_hash=new_cookie,
            device_id=str(device["device_id"]),
            strength="strong",
            purpose="privileged",
            expires_at=time.time() + 900,
        )
        self.store.touch_device(str(device["device_id"]))
        return AuthenticationResult(
            principal=self._principal_from_session(new_cookie, session),
            session_cookie=new_cookie,
            authentication_event_id=event_id,
        )

    def get_authenticated_principal(
        self, session_cookie: str | None
    ) -> Principal | None:
        if not session_cookie:
            return None
        session = self.sessions.validate_session(session_cookie)
        if session is None:
            return None
        operator = self.store.operator()
        if (
            operator is None
            or session.data.get("operator_id") != operator["operator_id"]
        ):
            return None
        event_id = str(session.data.get("authentication_event_id") or "")
        event = self.store.authentication_event(event_id)
        if event is None or event.get("session_hash") != session_cookie:
            return None
        if float(event.get("expires_at") or 0) <= time.time():
            return None
        if event.get("device_id") != session.data.get("device_id"):
            return None
        return self._principal_from_session(session_cookie, session)

    def revoke_session(self, session_cookie: str | None) -> None:
        self.sessions.invalidate_session(session_cookie)

    def authentication_event_count(self) -> int:
        return self.store.authentication_event_count()

    def _operator_for_credential(self, credential: str) -> dict[str, object]:
        operator = self.store.operator()
        if operator is None or not isinstance(credential, str) or not credential:
            raise InvalidCredential("invalid operator credential")
        supplied = credential_digest(credential)
        if not hmac.compare_digest(supplied, str(operator["credential_digest"])):
            raise InvalidCredential("invalid operator credential")
        return operator

    def _open_authenticated_session(
        self, operator: dict[str, object], *, event_type: str
    ) -> AuthenticationResult:
        event_id = uuid.uuid4().hex
        device = self.store.device_for_operator(str(operator["operator_id"]))
        if device is None:
            raise IdentityError(
                "operator has no active device; identity resolution failed closed"
            )
        raw_session = self.sessions.create_session(
            {
                "operator_id": operator["operator_id"],
                "display_name": operator["display_name"],
                "authentication_level": "operator",
                "authentication_event_id": event_id,
                "device_id": device["device_id"],
            }
        )
        session_cookie = hashlib.sha256(raw_session.encode("utf-8")).hexdigest()
        self.store.record_authentication_event(
            event_id=event_id,
            operator_id=str(operator["operator_id"]),
            event_type=event_type,
            session_hash=session_cookie,
            device_id=str(device["device_id"]),
            strength="operator",
            purpose="login",
        )
        self.store.touch_device(str(device["device_id"]))
        session = self.sessions.validate_session(session_cookie)
        if session is None:  # pragma: no cover - create_session just succeeded
            raise IdentityError("authentication session creation failed closed")
        return AuthenticationResult(
            principal=self._principal_from_session(session_cookie, session),
            session_cookie=session_cookie,
            authentication_event_id=event_id,
        )

    @staticmethod
    def _principal_from_session(session_cookie: str, session) -> Principal:
        authenticated_at = datetime.fromtimestamp(session.created_at, tz=timezone.utc)
        return Principal(
            principal_id=str(session.data["operator_id"]),
            principal_type=PrincipalType.OPERATOR,
            display_name=str(session.data["display_name"]),
            session_id=session_cookie,
            authentication_level=str(
                session.data.get("authentication_level", "operator")
            ),
            authenticated_at=authenticated_at,
            device_id=str(session.data.get("device_id", "")),
            authentication_event_id=str(
                session.data.get("authentication_event_id", "")
            ),
            metadata={
                "authentication_event_id": session.data.get("authentication_event_id")
            },
        )
