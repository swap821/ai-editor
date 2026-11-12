"""His doors to GAGOS's daily envelope: read, sign, end (2026-11-12).

The authority is a tmp_path one with its own stop, injected through the
dependency; the real capability store under data/ is never touched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app
from aios.api.routes.gagos_tasks import get_gagos_envelope_authority
from aios.application.capabilities.envelope import EnvelopeAuthority
from tests.test_gagos_envelope import _stop

_SIGN = {
    "folders": ["frontend/src/superbrain/"],
    "kinds": ["tests"],
    "maxMissions": 3,
    "hours": 8,
}


@pytest.fixture()
def env(tmp_path):
    authority = EnvelopeAuthority(
        db_path=tmp_path / "caps.db", emergency_stop=_stop(tmp_path)
    )
    app.dependency_overrides[get_gagos_envelope_authority] = lambda: authority
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            yield client, authority
    finally:
        app.dependency_overrides.clear()


def test_no_operator_is_refused(env) -> None:
    client, authority = env
    client.cookies.clear()
    for method, path in (
        ("GET", "/api/gagos/envelope"),
        ("POST", "/api/gagos/envelope"),
        ("POST", "/api/gagos/envelope/revoke"),
    ):
        response = client.request(method, path, json=_SIGN)
        assert response.status_code in (401, 403), (path, response.status_code)
    assert authority.status()["live"] is False


def test_sign_read_and_end(env) -> None:
    client, authority = env
    assert client.get("/api/gagos/envelope").json()["envelope"]["live"] is False

    signed = client.post("/api/gagos/envelope", json=_SIGN)
    assert signed.status_code == 201, signed.text
    envelope = signed.json()["envelope"]
    assert envelope["live"] is True
    assert envelope["terms"]["folders"] == ["frontend/src/superbrain/"]
    assert envelope["missionsLeft"] == 3
    assert authority.live().envelope_id == envelope["envelopeId"]

    read = client.get("/api/gagos/envelope").json()["envelope"]
    assert read["envelopeId"] == envelope["envelopeId"]

    ended = client.post("/api/gagos/envelope/revoke")
    assert ended.status_code == 200, ended.text
    assert ended.json()["ended"] is True
    assert ended.json()["envelope"] == {
        "live": False,
        "reason": "the envelope was ended: revoked by the operator",
    }


@pytest.mark.parametrize(
    "body,status",
    [
        ({**_SIGN, "folders": ["aios/security/"]}, 422),
        ({**_SIGN, "folders": ["../elsewhere/"]}, 422),
        ({**_SIGN, "kinds": ["everything"]}, 422),
        ({**_SIGN, "maxMissions": 0}, 422),
        ({**_SIGN, "hours": 48}, 422),
        ({**_SIGN, "delivery": "push"}, 422),
    ],
)
def test_terms_outside_the_rules_are_refused(env, body, status) -> None:
    client, authority = env
    response = client.post("/api/gagos/envelope", json=body)
    assert response.status_code == status, response.text
    assert authority.status()["live"] is False


def test_the_operator_id_is_never_echoed(env) -> None:
    client, authority = env
    signed = client.post("/api/gagos/envelope", json=_SIGN)
    assert signed.status_code == 201, signed.text
    operator_id = authority.store.latest()["operator_id"]
    for response in (signed, client.get("/api/gagos/envelope")):
        assert operator_id not in response.text
