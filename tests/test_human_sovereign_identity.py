"""Red acceptance tests for the GAGOS V1 Human Sovereign slice.

These tests describe the durable authority boundary required by the master
convergence directive.  They intentionally exercise the domain/application /
infrastructure seam rather than treating an HTTP field or a local process as
the operator.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aios.application.identity.service import AlreadyEnrolled, IdentityService
from aios.api.main import app
from aios.api.deps import get_identity_service, get_session_manager
from aios.domain.identity.models import PrincipalType


def _service(tmp_path):
    return IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )


def test_bootstrap_enrollment_is_single_use_and_never_persists_credentials(tmp_path):
    service = _service(tmp_path)

    enrollment = service.enroll_operator(display_name="Kumar")

    assert enrollment.operator_id.startswith("operator:")
    assert enrollment.enrollment_credential
    assert enrollment.recovery_code
    assert service.is_enrolled() is True
    stored = (tmp_path / "identity.db").read_bytes()
    assert enrollment.enrollment_credential.encode() not in stored
    assert enrollment.recovery_code.encode() not in stored
    with pytest.raises(AlreadyEnrolled):
        service.enroll_operator(display_name="Second operator")


def test_credential_authentication_returns_an_operator_principal_and_records_event(tmp_path):
    service = _service(tmp_path)
    enrollment = service.enroll_operator(display_name="Kumar")

    authenticated = service.authenticate_credential(enrollment.enrollment_credential)

    assert authenticated.principal.principal_type is PrincipalType.OPERATOR
    assert authenticated.principal.principal_id == enrollment.operator_id
    assert authenticated.principal.display_name == "Kumar"
    assert authenticated.principal.device_id.startswith("device:")
    assert authenticated.principal.authentication_event_id == authenticated.authentication_event_id
    assert authenticated.principal.authentication_level == "operator"
    assert authenticated.session_cookie
    assert authenticated.authentication_event_id
    assert service.authentication_event_count() == 1


def test_privileged_reauthentication_rotates_and_revokes_the_old_session(tmp_path):
    service = _service(tmp_path)
    enrollment = service.enroll_operator(display_name="Kumar")
    authenticated = service.authenticate_credential(enrollment.enrollment_credential)

    reauthenticated = service.reauthenticate(
        authenticated.session_cookie, enrollment.enrollment_credential
    )

    assert reauthenticated.session_cookie != authenticated.session_cookie
    assert service.get_authenticated_principal(authenticated.session_cookie) is None
    principal = service.get_authenticated_principal(reauthenticated.session_cookie)
    assert principal is not None
    assert principal.principal_type is PrincipalType.OPERATOR
    assert principal.device_id.startswith("device:")
    assert principal.authentication_level == "privileged"
    assert principal.authentication_event_id == reauthenticated.authentication_event_id
    assert reauthenticated.authentication_event_id != authenticated.authentication_event_id
    assert service.authentication_event_count() == 2


def test_logout_revokes_the_server_side_session(tmp_path):
    service = _service(tmp_path)
    enrollment = service.enroll_operator(display_name="Kumar")
    authenticated = service.authenticate_credential(enrollment.enrollment_credential)

    service.revoke_session(authenticated.session_cookie)

    assert service.get_authenticated_principal(authenticated.session_cookie) is None


def test_http_auth_never_echoes_session_material_and_rotates_cookie(tmp_path, monkeypatch):
    service = _service(tmp_path)
    import aios.api.deps as api_deps

    monkeypatch.setattr(api_deps, "_SESSION_MANAGER", service.sessions)
    app.dependency_overrides[get_identity_service] = lambda: service
    app.dependency_overrides[get_session_manager] = lambda: service.sessions
    try:
        with TestClient(app, client=("127.0.0.1", 43123)) as client:
            enrollment = client.post(
                "/api/v1/auth/enroll", json={"displayName": "Kumar"}
            )
            assert enrollment.status_code == 201
            enrollment_body = enrollment.json()
            assert "sessionId" not in enrollment_body
            assert "session_id" not in enrollment_body
            credential = enrollment_body["enrollmentCredential"]

            client.cookies.clear()
            login = client.post(
                "/api/v1/auth/login", json={"credential": credential}
            )
            assert login.status_code == 200
            assert "sessionId" not in login.json()
            assert "session_id" not in login.json()
            old_cookie = client.cookies.get("session_id")
            assert old_cookie

            status = client.get("/api/v1/auth/session")
            assert status.json()["operatorId"] == enrollment_body["operatorId"]
            assert "sessionId" not in status.json()

            reauth = client.post(
                "/api/v1/auth/reauth", json={"credential": credential}
            )
            assert reauth.status_code == 200
            assert reauth.json()["reauthenticated"] is True
            assert client.cookies.get("session_id") != old_cookie

            client.cookies.set("session_id", old_cookie)
            revoked = client.get("/api/v1/auth/session")
            assert revoked.json()["operatorId"] is None
    finally:
        app.dependency_overrides.clear()


def test_anonymous_local_session_cannot_execute_as_the_operator(tmp_path, monkeypatch):
    """A valid cookie proves session continuity, not Human Sovereign authority."""
    service = _service(tmp_path)
    import aios.api.deps as api_deps

    monkeypatch.setattr(api_deps, "_SESSION_MANAGER", service.sessions)
    app.dependency_overrides[get_identity_service] = lambda: service
    app.dependency_overrides[get_session_manager] = lambda: service.sessions
    try:
        with TestClient(app, client=("127.0.0.1", 43124)) as client:
            created = client.post("/api/v1/auth/session")
            assert created.status_code == 200
            response = client.post(
                "/api/v1/execute",
                json={"command": "echo must-not-run", "sessionId": "attacker-claimed"},
            )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("path", "payload", "params"),
    [
        ("/api/v1/approval/req", {"approvalToken": "attacker", "approve": True}, None),
        ("/api/v1/rollback", {}, None),
        ("/api/v1/self-analysis/proposals/1/apply", {}, None),
        ("/api/v1/development/autonomy/revoke", None, {"signature": "attacker"}),
        (
            "/api/v1/policy/propose",
            {"constraint": "allow_read_only", "proposedBy": "attacker"},
            None,
        ),
        (
            "/api/v1/council/approve",
            {"missionId": "attacker-mission"},
            None,
        ),
        (
            "/api/v1/council/missions",
            {"goal": "attacker", "allowedFiles": ["README.md"]},
            None,
        ),
    ],
)
def test_anonymous_local_session_cannot_mutate_privileged_routes(
    path, payload, params, tmp_path, monkeypatch
):
    """A generic valid session must not cross any privileged route boundary."""
    service = _service(tmp_path)
    import aios.api.deps as api_deps

    monkeypatch.setattr(api_deps, "_SESSION_MANAGER", service.sessions)
    app.dependency_overrides[get_identity_service] = lambda: service
    app.dependency_overrides[get_session_manager] = lambda: service.sessions
    try:
        with TestClient(app, client=("127.0.0.1", 43125)) as client:
            created = client.post("/api/v1/auth/session")
            assert created.status_code == 200
            response = client.post(path, json=payload, params=params)
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
